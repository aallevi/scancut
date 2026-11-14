# il sito-archivio (Directus), solo in lettura: l'indirizzo sta nelle impostazioni, la chiave nel
# Portachiavi del Mac (mai in un file). Scan Studio non scrive mai nell'archivio: se la chiave puo'
# scrivere lo dice, perche' se ne faccia una che legge soltanto.

import json, subprocess, urllib.request, urllib.parse, urllib.error

from . import core

SERVICE = 'Scan Studio archive'


def url():
    return (core.settings().get('archive_url') or '').rstrip('/')


def token():
    u = url()
    if not u:
        return None
    r = subprocess.run(['security', 'find-generic-password', '-s', SERVICE, '-a', u, '-w'], capture_output=True, text=True)
    return r.stdout.strip() or None if r.returncode == 0 else None


def _get(path, params=None, base=None, key=None):
    base, key = base or url(), key or token()
    if not base or not key:
        raise ValueError('no archive connected')
    q = ('?' + urllib.parse.urlencode(params)) if params else ''
    req = urllib.request.Request(base + path + q, headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r).get('data')
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e)['errors'][0]['message']
        except Exception:
            msg = e.reason
        raise ValueError(f'{e.code}: {msg}')
    except urllib.error.URLError as e:
        raise ValueError(f'cannot reach {base}: {e.reason}')


def _rights(base, key):
    # cosa puo' fare questa chiave: le collezioni che legge e quelle in cui potrebbe scrivere
    me = _get('/users/me', {'fields': 'first_name,last_name,email'}, base, key) or {}
    perms = _get('/permissions/me', None, base, key) or {}
    read, write = [], []
    for col, acts in perms.items():
        if col.startswith('directus_'):
            if any((acts.get(a) or {}).get('access') not in (None, 'none') for a in ('create', 'update', 'delete')) and col in ('directus_files', 'directus_users', 'directus_settings'):
                write.append(col)
            continue
        if (acts.get('read') or {}).get('access') not in (None, 'none'):
            read.append(col)
        if any((acts.get(a) or {}).get('access') not in (None, 'none') for a in ('create', 'update', 'delete')):
            write.append(col)
    name = ' '.join(x for x in (me.get('first_name'), me.get('last_name')) if x) or me.get('email') or '?'
    return {'user': name, 'reads': sorted(read), 'writes': sorted(write)}


def connect(base, key):
    base = (base or '').strip().rstrip('/')
    key = (key or '').strip()
    if base.endswith('/admin'):
        base = base[:-6]
    if not base.startswith(('http://', 'https://')) or not key:
        raise ValueError('give the archive address (https://…) and its token')
    r = _rights(base, key)                       # prima la prova: una chiave che non va non si salva
    subprocess.run(['security', 'add-generic-password', '-U', '-s', SERVICE, '-a', base, '-w', key,
                    '-l', f'{SERVICE} ({base})', '-j', 'read-only token for the Directus archive'], check=True, capture_output=True)
    core.save_settings({'archive_url': base})
    return status()


def forget():
    u = url()
    if u:
        subprocess.run(['security', 'delete-generic-password', '-s', SERVICE, '-a', u], capture_output=True)
    core.save_settings({'archive_url': ''})
    return status()


def status():
    u = url()
    if not u:
        return {'connected': False}
    if not token():
        return {'connected': False, 'url': u, 'error': 'no token in the Keychain'}
    try:
        r = _rights(u, token())
    except ValueError as e:
        return {'connected': False, 'url': u, 'error': str(e)}
    out = {'connected': True, 'url': u, **r}
    if 'records' in r['reads']:
        try:
            out['records'] = (_get('/items/records', {'aggregate[count]': '*'}) or [{}])[0].get('count')
            out['from_studio'] = (_get('/items/records', {'aggregate[count]': '*', 'filter[source][_eq]': 'scanstudio'}) or [{}])[0].get('count')
        except ValueError:
            pass
    return out


def lookup(kind, q=''):
    # le liste dell'archivio, in sola lettura: per scegliere a cosa legare un taglio (record, evento, posto)
    cols = {'records': ('records', 'id,title,category,status,source,source_id', 'title'),
            'events': ('events', 'id,title,start', '-start'),
            'places': ('records', 'id,title,address', 'address_sort')}
    if kind not in cols:
        raise ValueError('unknown list')
    col, fields, sort = cols[kind]
    p = {'fields': fields, 'sort': sort, 'limit': 200}
    if kind == 'places':
        p['filter[category][_eq]'] = 'storage'
    if q:
        p['search'] = q
    return _get(f'/items/{col}', p) or []


def in_archive(cut_uuids):
    # quali tagli l'archivio conosce gia' (record con source = scanstudio, source_id = uuid del taglio)
    if not cut_uuids or 'records' not in (status().get('reads') or []):
        return {}
    rows = _get('/items/records', {'fields': 'id,title,source_id', 'filter[source][_eq]': 'scanstudio',
                                   'filter[source_id][_in]': ','.join(cut_uuids), 'limit': -1}) or []
    return {r['source_id']: {'id': r['id'], 'title': r['title']} for r in rows}
