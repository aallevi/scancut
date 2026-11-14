# i record per l'archivio (il sito, Directus): cosa Scan Studio gli manda e come (studio/archive.py e' il collegamento
# in sola lettura: stato, liste; qui si preparano pacchetti e, se il gettone puo' scrivere, si mandano). Una via sola, dalla libreria all'archivio,
# per id stabili: ogni record la' ha source = 'scanstudio' e source_id = l'uuid della cosa qui (oggetto, parte,
# testo). Mandare due volte non fa doppioni: aggiorna solo i campi che sono dello studio (testo trascritto,
# misure, il file del taglio); titolo, date, note, posto sono dell'archivio dopo la prima volta.
#
# Cosa diventa un record:
#   - una fonte (scansione)       -> categoria "scan", senza file (gli originali restano qui), i suoi fogli "Part of" lei
#   - una parte (foglio tagliato) -> categoria sua o della fonte (di base "drawing"), il file del taglio, il testo in Inscriptions
#   - un testo                    -> (a scelta) un record "document" suo, Part of la parte: cosi' un testo vive anche da solo
# Il pacchetto (cartella con records.json e i file) e' la stessa cosa dell'invio diretto: lo legge chi vuole.

import os, re, json, time, shutil, subprocess, mimetypes, uuid as _uuid
import urllib.request, urllib.parse, urllib.error

from .. import core
from .db import now, sha256

SOURCE = 'scanstudio'
KEYCHAIN_SERVICE = 'Scan Studio archive'
DEFAULT_CATEGORY = 'drawing'
ITEM_KIND = 'Flatbed scan'          # la voce "Item" dell'archivio: come e' stato preso
LETTERS = 'abcdefghijklmnopqrstuvwxyz'
LIVE = "a.path NOT LIKE '%/studio-data/trash/%' AND a.path NOT LIKE '%/studio-data/replaced/%'"


# ---------------------------------------------------------------- il gettone, nel portachiavi del Mac
def token_set(url, token):
    # mai in un file di impostazioni, mai alla pagina: solo nel portachiavi, letto quando serve
    if not token:
        return token_clear(url)
    subprocess.run(['security', 'add-generic-password', '-U', '-s', KEYCHAIN_SERVICE, '-a', url, '-w', token], check=True, capture_output=True)
    return True


def token_clear(url):
    subprocess.run(['security', 'delete-generic-password', '-s', KEYCHAIN_SERVICE, '-a', url], capture_output=True)
    return False


def token_get(url):
    r = subprocess.run(['security', 'find-generic-password', '-s', KEYCHAIN_SERVICE, '-a', url, '-w'], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def archive_url():
    return (core.settings().get('archive_url') or '').strip().rstrip('/')


# ---------------------------------------------------------------- i record, dalla libreria
def _dims(geometry, dpi, rotation):
    # misura vera del foglio in cm (h × w, come l'archivio): dal rettangolo della zona, alla risoluzione della scansione
    try:
        g = json.loads(geometry) if isinstance(geometry, str) else geometry
        pts = g.get('poly') or [[g['box'][0], g['box'][1]], [g['box'][2], g['box'][3]]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        w, h = (max(xs) - min(xs)) / float(dpi) * 2.54, (max(ys) - min(ys)) / float(dpi) * 2.54
    except (TypeError, ValueError, KeyError, ZeroDivisionError):
        return None
    if int(rotation or 0) % 180 == 90:
        w, h = h, w
    return f'{h:.1f} × {w:.1f} cm'


def _dates(edtf):
    # EDTF -> le due date dell'archivio (inizio, fine), e il testo quando dice di piu' ("2014-05?", "199X")
    t = (edtf or '').strip()
    if not t:
        return None, None, None
    m = re.fullmatch(r'(\d{4})-(\d\d)-(\d\d)', t)
    if m:
        return t, None, None
    m = re.fullmatch(r'(\d{4})(?:-(\d\d))?', t)
    if m:
        return f'{m[1]}-{m[2] or "01"}-01', None, None
    ys = re.findall(r'\b(1\d{3}|2\d{3})\b', t.replace('X', '0'))
    if ys:
        a, b = min(ys), max(ys)
        return f'{a}-01-01', (f'{b}-12-31' if b != a else None), t
    return None, None, t


def _current_text(lib, region_id):
    from .bridge import region_texts
    rows = region_texts(lib, region_id)
    return '\n\n'.join(r['plain'] for r in rows if r['plain']) or None, rows


def _cut_file(lib, region_id):
    # il taglio attuale della parte: il file al suo posto (non la storia), con il suo asset
    r = lib.db.execute(f"SELECT a.* FROM cut x JOIN asset a ON a.path = x.path WHERE x.region_id = ? AND {LIVE} ORDER BY x.id DESC LIMIT 1", (region_id,)).fetchone()
    if r and os.path.exists(lib.asset_path(r)):
        return r
    return None


def _place_ref(lib, place_id):
    # il posto nell'archivio: il suo record la', se si conosce (place.archive_id, o un invio di prima)
    if not place_id:
        return None, None
    p = lib.db.execute('SELECT uuid, name, archive_id FROM place WHERE id = ?', (place_id,)).fetchone()
    if not p:
        return None, None
    link = lib.db.execute("SELECT archive_id FROM archive_link WHERE entity = 'place' AND uuid = ? AND archive = ?", (p['uuid'], archive_url())).fetchone()
    return (p['archive_id'] or (link[0] if link else None)), p['name']


def part_title(lib, part, region, source_title):
    # il titolo di una parte: il suo, se no quello del file del taglio, se no "fonte a"
    if part and part['title']:
        return part['title']
    c = _cut_file(lib, region['id'])
    if c:
        return os.path.splitext(c['original_name'])[0]
    return f'{source_title or "untitled"} {LETTERS[region["position"] % 26]}' if region['position'] is not None else (source_title or 'untitled')


def build(lib, items=None, regions=None, texts='inline', sources=True):
    """I record per l'archivio. items: uuid di fonti (tutte le loro parti) o di parti; regions: uuid di zone (parti).
    texts: 'inline' (il testo in Inscriptions della parte), 'records' (un record suo per ogni testo), 'both'.
    sources: anche un record per la fonte, con le parti Part of lei."""
    from .bridge import effective_place, where_kept
    part_ids = set()
    src_ids = set()
    if items is None and regions is None:
        rows = lib.db.execute("SELECT p.id FROM item p JOIN region g ON g.id = p.region_id JOIN item s ON s.id = p.parent_id WHERE p.kind = 'part' "
                              "AND p.trashed_at IS NULL AND g.removed_at IS NULL AND g.export_on = 1 AND s.trashed_at IS NULL").fetchall()
        part_ids = {r[0] for r in rows}
    for u in items or ():
        it = lib.db.execute('SELECT id, kind, region_id FROM item WHERE uuid = ? AND trashed_at IS NULL', (u,)).fetchone()
        if not it:
            continue
        if it['kind'] == 'part':
            part_ids.add(it['id'])
        else:
            src_ids.add(it['id'])
            part_ids |= {r[0] for r in lib.db.execute("SELECT p.id FROM item p JOIN region g ON g.id = p.region_id WHERE p.parent_id = ? AND p.kind = 'part' "
                                                      "AND p.trashed_at IS NULL AND g.removed_at IS NULL AND g.export_on = 1", (it['id'],))}
    for u in regions or ():
        r = lib.db.execute('SELECT id FROM region WHERE uuid = ?', (u,)).fetchone()
        pid = lib.part_of(r[0]) if r else None
        if pid:
            part_ids.add(pid)
    out, seen_src = [], set()
    for pid in sorted(part_ids):
        p = lib.db.execute('SELECT * FROM item WHERE id = ?', (pid,)).fetchone()
        g = lib.db.execute('SELECT * FROM region WHERE id = ?', (p['region_id'],)).fetchone()
        s = lib.db.execute('SELECT * FROM item WHERE id = ?', (p['parent_id'],)).fetchone()
        a = lib.db.execute('SELECT * FROM asset WHERE id = ?', (g['asset_id'],)).fetchone()
        series = lib.db.execute('SELECT name FROM series WHERE id = ?', (s['series_id'],)).fetchone() if s['series_id'] else None
        if sources and s['id'] not in seen_src:
            seen_src.add(s['id'])
            d0, d1, dt = _dates(s['date'])
            out.append({'source': SOURCE, 'source_id': s['uuid'], 'kind': 'source', 'category': 'scan', 'title': s['title'] or a['original_name'],
                        'date_start': d0, 'date_end': d1, 'date_text': dt, 'item': ITEM_KIND,
                        'dimensions': f'{a["height"] / float(a["dpi"]) * 2.54:.1f} × {a["width"] / float(a["dpi"]) * 2.54:.1f} cm' if a['dpi'] and a['width'] else None,
                        'description': None, 'inscriptions': None, 'files': [], 'within': [], 'kept_in': None, 'number': None,
                        'notes': _notes([('Scan Studio library', lib.meta('uuid')), ('Source file', a['original_name']), ('SHA-256', a['sha256']),
                                         ('Series', series[0] if series else None), ('Notes', s['notes'])]),
                        'rights': 'none', 'status': 'draft'})
        d0, d1, dt = _dates(p['date'] or s['date'])
        place_id, cat = effective_place(lib, g['id'])
        kept = where_kept(lib, g['id']) or {}
        archive_place, place_name = _place_ref(lib, place_id)
        text, readings = _current_text(lib, g['id']) if texts in ('inline', 'both', 'records') else (None, [])
        cut = _cut_file(lib, g['id'])
        title = part_title(lib, p, g, s['title'])
        rec = {'source': SOURCE, 'source_id': p['uuid'], 'kind': 'part', 'category': cat or DEFAULT_CATEGORY, 'title': title,
               'date_start': d0, 'date_end': d1, 'date_text': dt, 'item': ITEM_KIND,
               'dimensions': _dims(g['geometry'], a['dpi'], g['rotation']) if a['dpi'] else None,
               'description': None, 'inscriptions': text if texts in ('inline', 'both') else None,
               'files': [{'uuid': cut['uuid'], 'path': lib.asset_path(cut), 'sha256': cut['sha256'], 'name': cut['original_name'],
                          'width': cut['width'], 'height': cut['height']}] if cut else [],
               'within': [s['uuid']] if sources else [], 'kept_in': archive_place, 'number': p['place_number'],
               'notes': _notes([('Scan Studio library', lib.meta('uuid')), ('Part of scan', s['title'] or a['original_name']), ('Part', g['label'] or f'part {g["position"] + 1}'),
                                ('Region', g['uuid']), ('Cut SHA-256', cut['sha256'] if cut else None), ('Kept in (library)', ' › '.join(x for x in [kept.get('path')] if x) + (f' · {p["place_number"]}' if p['place_number'] else '') or None),
                                ('Place not yet in the archive', place_name if place_id and not archive_place else None),
                                ('Series', series[0] if series else None), ('Notes', p['notes'])]),
               'rights': 'view', 'status': 'draft'}
        out.append(rec)
        if texts in ('records', 'both') and text:
            last = readings[-1] if readings else None
            out.append({'source': SOURCE, 'source_id': f'text:{g["uuid"]}', 'kind': 'text', 'category': 'document', 'title': f'{title} — text',
                        'date_start': d0, 'date_end': d1, 'date_text': dt, 'item': None, 'dimensions': None,
                        'description': None, 'inscriptions': text, 'files': [], 'within': [p['uuid']], 'kept_in': None, 'number': None,
                        'notes': _notes([('Scan Studio library', lib.meta('uuid')), ('Text of part', title), ('Region', g['uuid']),
                                         ('Read with', f'{last["engine"]} {last["model"] or ""}'.strip() if last else None),
                                         ('Corrected', f'×{last["corrected_version"]}' if last and last['corrected_version'] else None)]),
                        'rights': 'none', 'status': 'draft'})
    return out


def _notes(pairs):
    return '\n'.join(f'**{k}:** {v}' for k, v in pairs if v not in (None, '', [])) or None


# ---------------------------------------------------------------- il pacchetto: una cartella che l'archivio sa leggere
def package(lib, dest, recs, log=print):
    dest = os.path.abspath(os.path.expanduser(dest))
    files_dir = os.path.join(dest, 'files')
    os.makedirs(files_dir, exist_ok=True)
    copied = 0
    for r in recs:
        for f in r['files']:
            name = f'{f["sha256"]}{os.path.splitext(f["path"])[1].lower()}'
            out = os.path.join(files_dir, name)
            if not os.path.exists(out):
                shutil.copy2(f['path'], out + '.part'); os.replace(out + '.part', out); copied += 1
            f['file'] = os.path.join('files', name)
    manifest = {'format': 'scanstudio-archive/1', 'written_at': now(), 'library': lib.meta('uuid'), 'library_name': lib.meta('name'),
                'source': SOURCE, 'records': [{k: v for k, v in r.items() if k != 'files'} | {'files': [{'file': f['file'], 'sha256': f['sha256'], 'name': f['name']} for f in r['files']]} for r in recs]}
    tmp = os.path.join(dest, 'records.json.part')
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(dest, 'records.json'))
    with open(os.path.join(dest, 'README.md'), 'w', encoding='utf-8') as fh:
        fh.write(README)
    lib.log('archive_package', 'library', lib.meta('uuid'), dir=dest, records=len(recs), files=copied)
    log(f'{len(recs)} record(s), {copied} file(s) copied into {dest}')
    return {'dir': dest, 'records': len(recs), 'files': copied}


README = """# Scan Studio archive package

`records.json` lists records for the archive (Directus `records` collection), one per source scan, per cut
part and (optionally) per transcribed text. Every record carries `source` = `scanstudio` and `source_id` =
its stable id in the Scan Studio library, so importing twice never makes duplicates. `within` lists the
`source_id`s the record is part of (a part is within its scan; a text is within its part). `files` are the
cut images, named by their SHA-256 (`files/<sha256>.<ext>`). `kept_in` is the archive id of the place, when
known; `number` its number there. `notes` is private provenance (library id, region id, checksums).
Fields the studio owns on later imports: `inscriptions`, `dimensions`, `files`. Everything else is the
archive's after the first import.
"""


# ---------------------------------------------------------------- l'invio diretto (Directus REST)
class Directus:
    def __init__(self, url, token, log=print):
        self.url, self.token, self.log = url.rstrip('/'), token, log

    def call(self, method, path, body=None, params=None, files=None):
        u = self.url + path + (('?' + urllib.parse.urlencode(params)) if params else '')
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json'}
        data = None
        if files:
            boundary = _uuid.uuid4().hex
            parts = []
            for field, (name, blob, mime) in files.items():
                parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{_quote(name)}"\r\n'
                              f'Content-Type: {mime}\r\n\r\n').encode() + blob + b'\r\n')
            data = b''.join(parts) + f'--{boundary}--\r\n'.encode()
            headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
        elif body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(u, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'{method} {path}: {e.code} {e.read()[:300].decode(errors="replace")}') from None
        return json.loads(raw).get('data') if raw else None

    def all(self, collection, fields, **filters):
        return self.call('GET', f'/items/{collection}', params={'fields': fields, 'limit': -1, **filters}) or []


def _quote(name):
    return name.replace('"', '').replace('\r', '').replace('\n', '')


def push(lib, recs, url=None, token=None, log=print, progress=None, client=None):
    """Manda i record all'archivio: nuovi come bozze; gia' la' (stesso source_id) solo i campi dello studio.
    client: un Directus gia' fatto (prove)."""
    url = (url or archive_url())
    if not url:
        raise ValueError('no archive address: set it in Settings › Archive')
    api = client or Directus(url, token or token_get(url) or '', log)
    if not api.token:
        raise ValueError('no archive token: paste it in Settings › Archive (it is kept in the Keychain)')
    known = {r['source_id']: r for r in api.all('records', 'id,source_id,status,title,inscriptions,dimensions,media.directus_files_id',
                                                **{'filter[source][_eq]': SOURCE})}
    kinds = {k['name'].casefold(): k['id'] for k in api.all('item_kinds', 'id,name')}
    done = {'created': 0, 'updated': 0, 'same': 0, 'files': 0}
    order = {'source': 0, 'part': 1, 'text': 2}
    recs = sorted(recs, key=lambda r: order.get(r['kind'], 9))
    ids = {}                                  # source_id -> id nell'archivio (per within)
    for i, r in enumerate(recs):
        if progress:
            progress(i, len(recs), r['title'])
        file_ids = []
        for f in r['files']:
            fid = _file_id(lib, api, url, f, log)
            if fid:
                file_ids.append(fid)
                done['files'] += 1 if fid.startswith('+') else 0
        file_ids = [x.lstrip('+') for x in file_ids]
        within = [ids.get(w) or (known.get(w) or {}).get('id') for w in r['within']]
        within = [w for w in within if w]
        item_id = None
        if r.get('item'):
            k = r['item'].casefold()
            if k not in kinds:
                kinds[k] = api.call('POST', '/items/item_kinds', {'name': r['item']})['id']
            item_id = kinds[k]
        old = known.get(r['source_id'])
        if old is None:
            body = {'status': 'draft', 'rights': r['rights'], 'language': 'en', 'category': r['category'], 'title': r['title'],
                    'date_start': r['date_start'], 'date_end': r['date_end'], 'date_text': r['date_text'], 'dimensions': r['dimensions'],
                    'inscriptions': r['inscriptions'], 'description': r['description'], 'notes': r['notes'], 'item': item_id,
                    'source': SOURCE, 'source_id': r['source_id'], 'media': [{'directus_files_id': f} for f in file_ids],
                    'within': [{'wholes_id': w} for w in within], 'kept_in': r['kept_in'], 'number': r['number'] if r['kept_in'] else None}
            new = api.call('POST', '/items/records', {k: v for k, v in body.items() if v not in (None, [])})
            ids[r['source_id']] = new['id']
            done['created'] += 1
            log(f'  new: {r["title"]}')
        else:
            ids[r['source_id']] = old['id']
            patch = {}
            if (r['inscriptions'] or None) != (old.get('inscriptions') or None):
                patch['inscriptions'] = r['inscriptions']
            if r['dimensions'] and r['dimensions'] != old.get('dimensions'):
                patch['dimensions'] = r['dimensions']
            have = [m.get('directus_files_id') if isinstance(m, dict) else m for m in (old.get('media') or [])]
            if file_ids and any(f not in have for f in file_ids):
                patch['media'] = [{'directus_files_id': f} for f in file_ids]         # il taglio attuale prende il posto di quello di prima
            if patch:
                api.call('PATCH', f'/items/records/{old["id"]}', patch)
                done['updated'] += 1
                log(f'  updated ({", ".join(patch)}): {r["title"]}')
            else:
                done['same'] += 1
        entity = 'text' if r['kind'] == 'text' else 'item'
        with lib.db:
            lib.db.execute('INSERT OR REPLACE INTO archive_link (entity, uuid, archive, archive_id, sha256, synced_at) VALUES (?,?,?,?,?,?)',
                           (entity, r['source_id'].split(':', 1)[-1], url, ids[r['source_id']], None, now()))
        lib.log('archive', entity, r['source_id'].split(':', 1)[-1], archive=url, archive_id=ids[r['source_id']], new=old is None)
    log(f'{done["created"]} new, {done["updated"]} updated, {done["same"]} unchanged, {done["files"]} file(s) uploaded')
    return done


def _file_id(lib, api, url, f, log):
    # il file nell'archivio: lo stesso (per checksum) non si carica due volte. "+" davanti: caricato ora
    link = lib.db.execute("SELECT archive_id, sha256 FROM archive_link WHERE entity = 'asset' AND uuid = ? AND archive = ?", (f['uuid'], url)).fetchone()
    if link and link['sha256'] == f['sha256']:
        return link['archive_id']
    with open(f['path'], 'rb') as fh:
        blob = fh.read()
    if sha256(f['path']) != f['sha256']:
        raise RuntimeError(f'{f["name"]}: the file on disk is not the one the library knows (checksum differs)')
    mime = mimetypes.guess_type(f['name'])[0] or ('image/jxl' if f['name'].lower().endswith('.jxl') else 'application/octet-stream')
    up = api.call('POST', '/files', files={'file': (f['name'], blob, mime)})
    if f.get('width') and f.get('height'):
        try:
            api.call('PATCH', f'/files/{up["id"]}', {'width': f['width'], 'height': f['height'], 'description': f'Scan Studio cut {f["uuid"]} sha256 {f["sha256"]}'})
        except RuntimeError:
            pass
    with lib.db:
        lib.db.execute('INSERT OR REPLACE INTO archive_link (entity, uuid, archive, archive_id, sha256, synced_at) VALUES (?,?,?,?,?,?)',
                       ('asset', f['uuid'], url, up['id'], f['sha256'], now()))
    log(f'  uploaded {f["name"]}')
    return '+' + up['id']


def status(lib, uuids):
    # per le viste: cosa e' gia' nell'archivio (per uuid di oggetti/parti)
    url = archive_url()
    if not url or not uuids:
        return {}
    ph = ','.join('?' * len(uuids))
    return {r['uuid']: {'archive_id': r['archive_id'], 'at': r['synced_at']} for r in lib.db.execute(
        f"SELECT uuid, archive_id, synced_at FROM archive_link WHERE entity = 'item' AND archive = ? AND uuid IN ({ph})", [url] + list(uuids))}
