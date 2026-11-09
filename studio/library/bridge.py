# il ponte fra la libreria e lo studio di oggi: import della cartella delle scansioni (originali
# referenziati dove sono, fogli e testo dallo stato dello studio) e "Modifica in…" (Affinity o altro):
# una copia di lavoro senza perdita si apre nell'app; ogni volta che la si salva, la libreria la
# prende come nuova versione legata all'originale. L'originale non si tocca mai.

import os, re, json, time, shutil, threading, subprocess, glob

from .. import core
from .db import Library, now, sha256

COLORS = ['#3399ff', '#ff8c1a', '#2fb84f', '#c84ad0', '#e0b600', '#14b8c4', '#ff4d5e', '#7a6cff']

_lib = None
_lib_lock = threading.Lock()


def series_of(rel):
    # la serie e' la cartella dentro originals/; un file sciolto non ha serie (niente nomi indovinati)
    parts = rel.split('/')
    return parts[1] if len(parts) == 3 and parts[0] == 'originals' else None


def library_path():
    p = core.settings().get('library') or os.path.join(core.ROOT, core.sc.PACKAGE)
    return os.path.expanduser(p)


def library(create=True):
    # la libreria della radice aperta (una per finestra dell'app)
    global _lib
    with _lib_lock:
        p = library_path()
        if _lib is None or _lib.path != p:
            if os.path.exists(os.path.join(p, 'library.sqlite')):
                _lib = Library(p)
            elif create:
                _lib = Library(p, create=True, name=os.path.basename(core.ROOT.rstrip('/')))
            else:
                return None
        return _lib


def rel_of(lib, asset):
    # il percorso dentro la radice (per anteprime e studio), se c'e'
    p = os.path.realpath(lib.asset_path(asset))
    return core.relpath(p) if p.startswith(core.ROOT + os.sep) else None


# ---------------------------------------------------------------- import della cartella di oggi

def import_root(lib, progress=None, log=print):
    files = []
    for base, dirs, fs in os.walk(core.abspath('originals')):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        files += [os.path.join(base, f) for f in sorted(fs) if core.is_image(f)]
    added = 0
    for i, path in enumerate(files):
        rel = core.relpath(path)
        aid, new = lib.add_asset(path, managed=False)
        row = lib.db.execute('SELECT item_id FROM item_asset WHERE asset_id = ? ORDER BY position LIMIT 1', (aid,)).fetchone()
        if row:
            iid = row[0]
            sid = lib.series(series_of(rel))                 # la serie segue dove sta il file (niente nomi indovinati)
            if lib.db.execute('SELECT series_id FROM item WHERE id = ?', (iid,)).fetchone()[0] != sid:
                lib.db.execute('UPDATE item SET series_id = ? WHERE id = ?', (sid, iid)); lib.db.commit()
        else:
            stem = os.path.splitext(os.path.basename(path))[0]
            date = time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(path)))
            iid = lib.new_item(stem, kind='scan', batch=series_of(rel), date=date, assets=[aid])
            added += 1
        import_cutouts(lib, rel)
        if progress:
            progress(i + 1, len(files), os.path.basename(path))
    for (u, name) in lib.db.execute('SELECT uuid, name FROM series s WHERE NOT EXISTS (SELECT 1 FROM item WHERE series_id = s.id)').fetchall():
        lib.db.execute('DELETE FROM series WHERE uuid = ?', (u,)); lib.log('remove', 'series', u, name=name, why='no objects')
    lib.db.commit()
    log(f'{len(files)} originals, {added} new item(s)')
    return {'files': len(files), 'new_items': added}


# ---------------------------------------------------------------- arrivi: scanner, file trascinati
# Regola: ogni file fra le fonti e' nella libreria (registrato appena c'e'), e chi l'ha portato lo dice
# (lo scanner con le sue impostazioni, o un file aggiunto). Non serve "aggiornare" a mano.

def record_capture(lib, path, how, name=None, series=None, device=None, settings=None):
    from .db import new_uuid
    u = new_uuid()
    lib.db.execute('INSERT INTO capture (uuid, sha256, how, name, series, device, settings, captured_at) VALUES (?,?,?,?,?,?,?,?)',
                   (u, sha256(path), how, name or os.path.basename(path), series, device,
                    json.dumps(settings) if settings else None, now()))
    lib.db.commit()
    return u


def captured(lib, uuids, after_id):
    # le fonti nate da queste scansioni (per checksum, anche se l'agente le ha rinumerate o un'altra
    # archiviazione le ha prese prima); una scansione legata a un file che c'era gia' e' una copia identica
    rows = lib.db.execute(f'SELECT c.uuid, a.* FROM capture c LEFT JOIN asset a ON a.id = c.asset_id WHERE c.uuid IN ({",".join("?" * len(uuids))})',
                          list(uuids)).fetchall() if uuids else []
    return [rel_of(lib, r) for r in rows if r['id'] and r['id'] > after_id]


_reg_last = [0.0]


def register_new(lib, force=True):
    # le fonti nuove (arrivate nell'inbox e messe fra le fonti dall'agente) entrano nella libreria; le loro
    # registrazioni d'arrivo si legano al file per checksum. Veloce: solo i percorsi che il catalogo non ha.
    if not force and time.time() - _reg_last[0] < 3:
        return []
    _reg_last[0] = time.time()
    _heal_packed(lib)
    known = {r[0] for r in lib.db.execute("SELECT path FROM asset WHERE storage = 'referenced'")}
    new = []
    for base, dirs, fs in os.walk(core.abspath('originals')):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for f in sorted(fs):
            p = os.path.realpath(os.path.join(base, f))
            if core.is_image(f) and p not in known:
                iid, aid = item_for(lib, core.relpath(os.path.join(base, f)))
                new.append((iid, aid))
    # gli arrivi registrati prima, ora con il loro file (un file passato in JPEG XL ha un checksum nuovo: packed.tsv)
    led = os.path.join(core.ROOT, '.scancut', 'packed.tsv')
    if os.path.exists(led):
        for line in open(led):
            p = line.rstrip('\n').split('\t')
            if len(p) >= 2:
                lib.db.execute('UPDATE capture SET sha256 = ? WHERE sha256 = ? AND asset_id IS NULL', (p[1], p[0]))
        lib.db.commit()
    for c in lib.db.execute('SELECT * FROM capture WHERE asset_id IS NULL').fetchall():
        a = lib.db.execute("SELECT a.id, a.uuid, a.dpi FROM asset a JOIN item_asset ia ON ia.asset_id = a.id WHERE a.sha256 = ? AND a.path NOT LIKE '%/studio-data/replaced/%' AND a.path NOT LIKE '%/studio-data/trash/%' "
                           "ORDER BY a.id DESC LIMIT 1", (c['sha256'],)).fetchone()
        if not a:
            continue
        st = json.loads(c['settings'] or '{}')
        lib.db.execute('UPDATE capture SET asset_id = ? WHERE id = ?', (a['id'], c['id']))
        if st.get('res') and not a['dpi']:
            lib.db.execute('UPDATE asset SET dpi = ? WHERE id = ?', (float(st['res']), a['id']))
        lib.db.commit()
        lib.log('capture', 'asset', a['uuid'], how=c['how'], device=c['device'], **{k: v for k, v in st.items() if k in ('res', 'mode', 'area', 'frames')})
    if new:
        lib.log('register', 'library', lib.meta('uuid'), sources=len(new))
    return new


def _heal_packed(lib):
    # un file passato in JPEG XL (registro packed.tsv: checksum di prima, di dopo, percorso): la sua riga segue il file.
    # Se il TIFF era gia' stato registrato e il JPEG XL anche (due oggetti per una scansione), le registrazioni
    # d'arrivo passano al JPEG XL e il doppione vuoto (niente parti, ritocchi, altri file) si toglie
    led = os.path.join(core.ROOT, '.scancut', 'packed.tsv')
    if not os.path.exists(led):
        return
    for line in open(led):
        p = line.rstrip('\n').split('\t')
        if len(p) < 3:
            continue
        old = lib.db.execute("SELECT * FROM asset WHERE sha256 = ? AND storage = 'referenced'", (p[0],)).fetchone()
        if not old or os.path.exists(old['path']):
            continue
        path = os.path.realpath(core.abspath(os.path.join('originals', p[2])))
        if not os.path.exists(path):
            continue
        new = lib.db.execute('SELECT * FROM asset WHERE path = ?', (path,)).fetchone()
        if not new:
            lib.db.execute("UPDATE asset SET path = ?, sha256 = ?, size = ?, mime = 'image/jxl', original_name = ? WHERE id = ?",
                           (path, p[1], os.path.getsize(path), os.path.basename(path), old['id']))
            lib.db.commit()
            lib.log('move', 'asset', old['uuid'], new_path=path, why='lossless JPEG XL, same pixels')
            continue
        busy = lib.db.execute('SELECT 1 FROM region WHERE asset_id = ? UNION SELECT 1 FROM editstate WHERE asset_id = ?', (old['id'], old['id'])).fetchone()
        items = [r[0] for r in lib.db.execute('SELECT item_id FROM item_asset WHERE asset_id = ?', (old['id'],))]
        alone = all(lib.db.execute('SELECT COUNT(*) FROM item_asset WHERE item_id = ?', (i,)).fetchone()[0] == 1 and
                    not lib.db.execute('SELECT trashed_at FROM item WHERE id = ?', (i,)).fetchone()[0] for i in items)   # nel cestino: ci pensa il cestino
        if busy or not alone:
            continue                                   # c'e' lavoro sopra: non si tocca, lo dice il controllo
        lib.db.execute('UPDATE capture SET asset_id = ? WHERE asset_id = ?', (new['id'], old['id']))
        for i in items:
            u = lib.db.execute('SELECT uuid FROM item WHERE id = ?', (i,)).fetchone()[0]
            lib.db.execute('DELETE FROM search WHERE item_uuid = ?', (u,))
            lib.db.execute('DELETE FROM item_asset WHERE item_id = ?', (i,))
            lib.db.execute('DELETE FROM item WHERE id = ?', (i,))
            lib.log('merge', 'item', u, into_asset=new['uuid'], why='the same scan registered before and after JPEG XL')
        lib.db.execute('DELETE FROM asset WHERE id = ?', (old['id'],))
        lib.db.commit()


def new_rels(lib, new):
    # i percorsi nella radice delle fonti appena registrate
    return [rel_of(lib, lib.db.execute('SELECT * FROM asset WHERE id = ?', (aid,)).fetchone()) for _, aid in new]


def add_cut_file(lib, path):
    # un taglio portato da fuori (trascinato su Tagli): un oggetto suo, con il file come taglio
    aid, _ = lib.add_asset(path, managed=False)
    if not lib.db.execute('SELECT 1 FROM item_asset WHERE asset_id = ?', (aid,)).fetchone():
        iid = lib.new_item(os.path.splitext(os.path.basename(path))[0], kind='cut', date=time.strftime('%Y-%m-%d'), assets=[])
        lib.link_asset(iid, aid, role='cutout')
    return aid


def capture_of(lib, asset_id):
    r = lib.db.execute('SELECT how, name, series, device, settings, captured_at FROM capture WHERE asset_id = ? ORDER BY id DESC LIMIT 1', (asset_id,)).fetchone()
    return dict(r, settings=json.loads(r['settings'] or '{}')) if r else None


# ---------------------------------------------------------------- dove sono le cose: posti, numeri, categorie
# Come l'archivio del sito: un posto tiene cose (e altri posti); ogni cosa e' in un posto solo, con un numero
# li'; l'indirizzo sono i numeri dall'esterno ("1 · 24 · 5", "?" se manca). Un foglio senza posto suo ha
# quello della sua fonte; lo stesso per la categoria. Le regole (numeri liberi, niente giri) le tiene il
# database; qui si scrive e si registra ogni spostamento.

def _place_chain(lib, pid):
    out = []
    while pid:
        r = lib.db.execute('SELECT id, uuid, name, number, parent_id FROM place WHERE id = ?', (pid,)).fetchone()
        if not r:
            break
        out.insert(0, r); pid = r['parent_id']
    return out


def address(lib, place_id, number=None):
    # "1 · 24 · 5" (i numeri dall'esterno), e il nome per esteso "Cassettiera › Box 24 › Folder 5"
    ch = _place_chain(lib, place_id)
    nums = [str(r['number']) if r['number'] else '?' for r in ch] + ([str(number)] if number else ['?'] if ch else [])
    return {'address': ' · '.join(nums), 'path': ' › '.join(r['name'] for r in ch)} if ch else None


def places(lib):
    # tutti i posti, con indirizzo e quante cose tengono (fogli che ci stanno, anche per la loro fonte)
    out, count = [], {}
    for (rid,) in lib.db.execute("SELECT g.id FROM region g JOIN item i ON i.id = g.item_id WHERE g.removed_at IS NULL AND g.parent_id IS NULL "
                                 "AND g.kind = 'sheet' AND i.trashed_at IS NULL"):
        pid = effective_place(lib, rid)[0]
        if pid:
            count[pid] = count.get(pid, 0) + 1
    for r in lib.db.execute('SELECT p.*, 0 AS things, (SELECT uuid FROM place q WHERE q.id = p.parent_id) AS parent FROM place p ORDER BY p.parent_id IS NOT NULL, p.number, p.name'):
        r = dict(r); r['things'] = count.get(r['id'], 0)
        a = address(lib, r['id'])
        out.append({'uuid': r['uuid'], 'name': r['name'], 'kind': r['kind'], 'number': r['number'], 'parent': r['parent'],
                    'things': r['things'], 'notes': r['notes'], 'archive_id': r['archive_id'], **(a or {})})
    return sorted(out, key=lambda x: ([int(n) if n.isdigit() else 10 ** 9 for n in x['address'].split(' · ')[:-1]], x['name'].lower()))


def _pid(lib, uuid):
    if not uuid:
        return None
    r = lib.db.execute('SELECT id FROM place WHERE uuid = ?', (uuid,)).fetchone()
    if not r:
        raise ValueError('no such place')
    return r[0]


def save_place(lib, uuid=None, name=None, parent=None, number=None, kind='storage', notes=None, delete=False):
    from .db import new_uuid
    if delete:
        lib.db.execute('DELETE FROM place WHERE uuid = ?', (uuid,)); lib.db.commit()
        lib.log('remove', 'place', uuid); return None
    num = int(number) if number not in (None, '') else None
    if uuid:
        lib.db.execute('UPDATE place SET name = COALESCE(?, name), parent_id = ?, number = ?, kind = ?, notes = ?, modified_at = ? WHERE uuid = ?',
                       (name, _pid(lib, parent), num, kind, notes, now(), uuid))
    else:
        uuid = new_uuid()
        lib.db.execute('INSERT INTO place (uuid, name, kind, parent_id, number, notes, created_at, modified_at) VALUES (?,?,?,?,?,?,?,?)',
                       (uuid, (name or '').strip() or 'Place', kind, _pid(lib, parent), num, notes, now(), now()))
    lib.db.commit()
    lib.log('place', 'place', uuid, name=name, number=num)
    return uuid


def resolve_address(lib, text):
    # "24-05", "24 5", "1 · 24 · 5": i numeri dall'esterno. Con due numeri e un posto di partenza scelto
    # (impostazione places_in, come positions_in dell'archivio) si parte da li'; se no dal piu' esterno.
    nums = [int(n) for n in re.findall(r'\d+', text or '')]
    if not nums:
        return None
    start = lib.db.execute("SELECT value FROM setting WHERE key = 'places_in'").fetchone()
    pid = _pid(lib, json.loads(start[0])) if start and len(nums) <= 2 else None
    for n in nums:
        r = lib.db.execute('SELECT id, uuid FROM place WHERE COALESCE(parent_id, 0) = ? AND number = ?', (pid or 0, n)).fetchone()
        if not r:
            return None
        pid = r['id']
    return lib.db.execute('SELECT uuid FROM place WHERE id = ?', (pid,)).fetchone()[0]


def put(lib, items=(), regions=(), place=..., number=..., category=...):
    # mettere in un posto (con un numero) e/o dare una categoria: a fonti intere (le loro parti senza posto
    # proprio lo seguono) o a singole parti. ... = non cambia. Ogni spostamento e' registrato.
    changed = 0
    with lib.db:
        for u in items:
            it = lib.db.execute('SELECT id, place_id, category FROM item WHERE uuid = ?', (u,)).fetchone()
            if not it:
                continue
            if place is not ...:
                new = _pid(lib, place)
                if new != it['place_id']:
                    lib.db.execute('UPDATE item SET place_id = ?, modified_at = ? WHERE id = ?', (new, now(), it['id']))
                    lib.log('move', 'item', u, **{'from': (address(lib, it['place_id']) or {}).get('path'), 'to': (address(lib, new) or {}).get('path')})
            if category is not ...:
                lib.db.execute('UPDATE item SET category = ? WHERE id = ?', (category or None, it['id']))
            changed += 1
        for u in regions:
            r = lib.db.execute('SELECT id, place_id, place_number FROM region WHERE uuid = ?', (u,)).fetchone()
            if not r:
                continue
            new = _pid(lib, place) if place is not ... else r['place_id']
            num = (int(number) if number not in (None, '') else None) if number is not ... else r['place_number']
            if new is None:
                num = None
            if (new, num) != (r['place_id'], r['place_number']):
                lib.db.execute('UPDATE region SET place_id = ?, place_number = ?, modified_at = ? WHERE id = ?', (new, num, now(), r['id']))
                lib.log('move', 'region', u, **{'from': (address(lib, r['place_id'], r['place_number']) or {}).get('address'),
                                                'to': (address(lib, new, num) or {}).get('address')})
            if category is not ...:
                lib.db.execute('UPDATE region SET category = ? WHERE id = ?', (category or None, r['id']))
            changed += 1
    return changed


def _origin_region(lib, region_id):
    # un pezzo di un taglio ritagliato: la parte da cui viene quel taglio (per posto e categoria)
    r = lib.db.execute("SELECT x.region_id FROM region g JOIN asset a ON a.id = g.asset_id JOIN cut x ON x.path = a.path "
                       "WHERE g.id = ? AND x.region_id IS NOT NULL AND x.region_id != g.id ORDER BY x.id DESC LIMIT 1", (region_id,)).fetchone()
    return r[0] if r else None


def effective_place(lib, region_id, depth=0):
    # (posto, categoria) che valgono per un foglio: il suo, se no quello della sua fonte, se no quello della parte d'origine
    r = lib.db.execute('SELECT g.place_id, g.category, i.place_id AS ip, i.category AS ic FROM region g JOIN item i ON i.id = g.item_id WHERE g.id = ?',
                       (region_id,)).fetchone()
    if not r:
        return None, None
    pid, cat = r['place_id'] or r['ip'], r['category'] or r['ic']
    if (pid is None or cat is None) and depth < 5:
        o = _origin_region(lib, region_id)
        if o:
            op, oc = effective_place(lib, o, depth + 1)
            pid, cat = pid or op, cat or oc
    return pid, cat


def where_kept(lib, region_id):
    # il posto, il numero, la categoria di un foglio, con quel che eredita (dalla sua fonte, o dalla parte d'origine)
    r = lib.db.execute('SELECT g.place_id, g.place_number, g.category, i.place_id AS ip, i.category AS ic FROM region g JOIN item i ON i.id = g.item_id '
                       'WHERE g.id = ?', (region_id,)).fetchone()
    if not r:
        return None
    pid, cat = effective_place(lib, region_id)
    a = address(lib, pid, r['place_number']) or {}
    return {'place': lib.db.execute('SELECT uuid FROM place WHERE id = ?', (pid,)).fetchone()[0] if pid else None, 'own_place': bool(r['place_id']),
            'number': r['place_number'], 'category': cat, 'own_category': bool(r['category']), **a}


def categories(lib):
    return [dict(r) for r in lib.db.execute('SELECT key, label FROM category ORDER BY position, label')]


# ---------------------------------------------------------------- cestino della libreria
# Una fonte (con i suoi tagli) o un taglio vanno nel cestino: i file si spostano in studio-data/trash/
# (mai cancellati subito), la libreria ricorda da dove venivano. Si rimettono a posto con un clic.
# Il cestino si svuota da solo dopo i giorni scelti (trash_days, di base 91: ogni tre mesi): allora si
# cancella davvero, file e righe.

def _to_trash(lib, path, stamp):
    dst = core.sc.unique(os.path.join(core.DATA, 'trash', stamp, core.relpath(path) if path.startswith(core.ROOT + os.sep) else os.path.basename(path)))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.rename(path, dst)
    lib.db.execute('UPDATE asset SET path = ? WHERE path = ?', (dst, path))
    lib.db.execute('UPDATE cut SET path = ? WHERE path = ?', (dst, path))
    return dst


def _editors_reload(lib, asset_ids):
    # lo studio rilegge lo stato di quei file (parti incluse o no)
    from . import store
    for aid in asset_ids:
        lib.db.execute('UPDATE editstate SET version = version + 1 WHERE asset_id = ?', (aid,))
    store._cache.clear()


def trash(lib, items=(), cuts=()):
    from .db import new_uuid
    stamp = time.strftime('%Y%m%d-%H%M%S')
    n = 0
    with files_lock:
        for u in items:
            it = lib.db.execute('SELECT id, title FROM item WHERE uuid = ? AND trashed_at IS NULL', (u,)).fetchone()
            if not it:
                continue
            files = []
            ids = [it['id']] + [r[0] for r in lib.db.execute('SELECT id FROM item WHERE parent_id = ?', (it['id'],))]
            for a in lib.db.execute(f"SELECT DISTINCT a.* FROM asset a JOIN item_asset ia ON ia.asset_id = a.id WHERE ia.item_id IN ({','.join('?' * len(ids))})", ids).fetchall():
                p = lib.asset_path(a)
                if a['storage'] == 'referenced' and os.path.exists(p) and '/studio-data/' not in p:
                    files.append({'asset': a['uuid'], 'from': p, 'to': _to_trash(lib, p, stamp)})
            lib.db.execute(f"UPDATE item SET trashed_at = ? WHERE id IN ({','.join('?' * len(ids))})", [now()] + ids)
            lib.db.execute('INSERT INTO trash (uuid, what, ref, title, files, trashed_at) VALUES (?,?,?,?,?,?)', (new_uuid(), 'item', u, it['title'], json.dumps(files), now()))
            lib.log('trash', 'item', u, files=len(files)); n += 1
        for u in cuts:
            a = lib.db.execute('SELECT * FROM asset WHERE uuid = ?', (u,)).fetchone()
            if not a or not os.path.exists(lib.asset_path(a)):
                continue
            p = lib.asset_path(a)
            # le parti di cui era il taglio non si ritagliano piu' (escluse dal taglio), finche' non torna
            regs = [r[0] for r in lib.db.execute('SELECT DISTINCT region_id FROM cut WHERE path = ? AND region_id IS NOT NULL', (p,))]
            regs = [r for r in regs if lib.db.execute('SELECT export_on FROM region WHERE id = ?', (r,)).fetchone()[0]]
            for r in regs:
                lib.db.execute('UPDATE region SET export_on = 0 WHERE id = ?', (r,))
            _editors_reload(lib, [x[0] for x in lib.db.execute(f"SELECT DISTINCT asset_id FROM region WHERE id IN ({','.join(map(str, regs)) or '-1'})")])
            dst = _to_trash(lib, p, stamp)
            it = lib.db.execute("SELECT i.id, i.uuid FROM item i JOIN item_asset ia ON ia.item_id = i.id WHERE ia.asset_id = ? AND i.kind = 'cut'", (a['id'],)).fetchone()
            if it:                                        # un taglio portato da fuori: e' un oggetto suo
                lib.db.execute('UPDATE item SET trashed_at = ? WHERE id = ?', (now(), it['id']))
            lib.db.execute('INSERT INTO trash (uuid, what, ref, title, files, regions_off, trashed_at) VALUES (?,?,?,?,?,?,?)',
                           (new_uuid(), 'cut', u, a['original_name'], json.dumps([{'asset': u, 'from': p, 'to': dst}]), json.dumps(regs), now()))
            lib.log('trash', 'asset', u); n += 1
        lib.db.commit()
    schedule_journal()
    return n


def trash_list(lib):
    days = int(core.settings().get('trash_days') or 91)
    out = []
    for t in lib.db.execute('SELECT * FROM trash ORDER BY trashed_at DESC'):
        files = json.loads(t['files'])
        f0 = files[0]['to'] if files else None
        out.append({'uuid': t['uuid'], 'what': t['what'], 'title': t['title'], 'at': t['trashed_at'], 'files': len(files),
                    'rel': core.relpath(f0) if f0 and f0.startswith(core.ROOT + os.sep) and os.path.exists(f0) else None,
                    'empties': time.strftime('%Y-%m-%d', time.localtime(time.mktime(time.strptime(t['trashed_at'][:19], '%Y-%m-%dT%H:%M:%S')) + days * 86400))})
    return out


def restore(lib, uuid):
    t = lib.db.execute('SELECT * FROM trash WHERE uuid = ?', (uuid,)).fetchone()
    if not t:
        return False
    with files_lock:
        for f in json.loads(t['files']):
            if not os.path.exists(f['to']):
                continue
            back = core.sc.unique(f['from'])                 # mai sopra un file che intanto e' arrivato li'
            os.makedirs(os.path.dirname(back), exist_ok=True)
            os.rename(f['to'], back)
            lib.db.execute('UPDATE asset SET path = ? WHERE path = ?', (back, f['to']))
            lib.db.execute('UPDATE cut SET path = ? WHERE path = ?', (back, f['to']))
        if t['what'] == 'item':
            iid = lib.db.execute('SELECT id FROM item WHERE uuid = ?', (t['ref'],)).fetchone()[0]
            lib.db.execute('UPDATE item SET trashed_at = NULL WHERE id = ? OR parent_id = ?', (iid, iid))
        else:
            regs = json.loads(t['regions_off'] or '[]')
            for r in regs:
                lib.db.execute('UPDATE region SET export_on = 1 WHERE id = ?', (r,))
            _editors_reload(lib, [x[0] for x in lib.db.execute(f"SELECT DISTINCT asset_id FROM region WHERE id IN ({','.join(map(str, regs)) or '-1'})")])
            lib.db.execute("UPDATE item SET trashed_at = NULL WHERE kind = 'cut' AND id IN (SELECT item_id FROM item_asset WHERE asset_id = (SELECT id FROM asset WHERE uuid = ?))", (t['ref'],))
        lib.db.execute('DELETE FROM trash WHERE id = ?', (t['id'],))
        lib.db.commit()
    lib.log('restore', t['what'], t['ref'])
    schedule_journal()
    return True


def empty_trash(lib, older_than_days=None, only=None):
    # cancella davvero: i file nel cestino e le righe di cio' che era loro. older_than_days=None: tutto
    gone = 0
    with files_lock:
        for t in lib.db.execute('SELECT * FROM trash ORDER BY id').fetchall():
            if only and t['uuid'] not in only:
                continue
            if older_than_days is not None and time.time() - time.mktime(time.strptime(t['trashed_at'][:19], '%Y-%m-%dT%H:%M:%S')) < older_than_days * 86400:
                continue
            files = json.loads(t['files'])
            for f in files:
                if os.path.exists(f['to']) and '/studio-data/trash/' in f['to']:
                    os.remove(f['to'])
                lib.db.execute('DELETE FROM cut WHERE path = ?', (f['to'],))
            assets = [r[0] for r in lib.db.execute(f"SELECT id FROM asset WHERE uuid IN ({','.join('?' * len(files)) or 'NULL'})", [f['asset'] for f in files])]
            if t['what'] == 'item':
                it = lib.db.execute('SELECT id, uuid FROM item WHERE uuid = ?', (t['ref'],)).fetchone()
                if it:
                    lib.db.execute('DELETE FROM search WHERE item_uuid IN (SELECT uuid FROM item WHERE id = ? OR parent_id = ?)', (it['id'], it['id']))
                    lib.db.execute('DELETE FROM item WHERE parent_id = ?', (it['id'],))
                    lib.db.execute('DELETE FROM item WHERE id = ?', (it['id'],))
            else:
                lib.db.execute("DELETE FROM item WHERE kind = 'cut' AND trashed_at IS NOT NULL AND id IN (SELECT item_id FROM item_asset WHERE asset_id IN (%s))" % (','.join(map(str, assets)) or '-1'))
            for aid in assets:
                lib.db.execute("DELETE FROM item_asset WHERE asset_id = ? AND role = 'cutout'", (aid,))      # un taglio: non e' piu' di nessuno
                if not lib.db.execute('SELECT 1 FROM item_asset WHERE asset_id = ? UNION SELECT 1 FROM region WHERE asset_id = ?', (aid, aid)).fetchone():
                    lib.db.execute('DELETE FROM reading WHERE asset_id = ? AND region_id IS NULL', (aid,))
                    lib.db.execute('DELETE FROM asset WHERE id = ?', (aid,))
            lib.db.execute('DELETE FROM trash WHERE id = ?', (t['id'],))
            lib.log('emptied', t['what'], t['ref'], title=t['title'], files=len(files))
            gone += 1
        lib.db.commit()
        d = os.path.join(core.DATA, 'trash')
        for base, dirs, fs in os.walk(d, topdown=False):         # cartelle rimaste vuote
            if base != d and not os.listdir(base):
                os.rmdir(base)
    return gone


# ---------------------------------------------------------------- tagli fuori, in cartelle (come l'esportazione di Eagle)
# Una copia dei tagli in una cartella scelta, ordinata come si vuole: per posto (Cassettiera / Box 24 /
# Folder 5), per serie, o tutti insieme. I file sono gli stessi byte; mai sopra un altro (identico: resta).

def _safe_dir(name):
    return re.sub(r'[/:\\]+', '-', (name or '').strip()) or 'untitled'


def export_cuts(lib, dest, structure='place', series=None, place=None, cuts=None):
    import filecmp
    dest = os.path.abspath(os.path.expanduser(dest))
    rows = cutout_list(lib, limit=100000, series=series, place=place)
    if cuts:
        rows = [c for c in rows if c['uuid'] in set(cuts)]
    done = {'copied': 0, 'same': 0, 'dir': dest}
    for c in rows:
        a = lib.db.execute('SELECT * FROM asset WHERE uuid = ?', (c['uuid'],)).fetchone()
        src = lib.asset_path(a)
        if not os.path.exists(src) or '/studio-data/' in src:
            continue
        if structure == 'place':
            k = c.get('kept') or {}
            sub = [_safe_dir(x) for x in k['path'].split(' › ')] if k.get('path') else ['Not placed']
            name = (f'{k["number"]:02d} ' if k.get('number') else '') + os.path.basename(src)
        elif structure == 'series':
            sr = lib.db.execute('SELECT s.name FROM item i JOIN series s ON s.id = i.series_id WHERE i.uuid = ?', (c['item'],)).fetchone()
            sub, name = [_safe_dir(sr[0]) if sr else 'No series'], os.path.basename(src)
        else:
            sub, name = [], os.path.basename(src)
        d = os.path.join(dest, *sub)
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, name)
        if os.path.exists(out) and filecmp.cmp(src, out, shallow=False):
            done['same'] += 1; continue
        out = core.sc.unique(out)
        shutil.copy2(src, out)
        done['copied'] += 1
    lib.log('export', 'library', lib.meta('uuid'), dir=dest, structure=structure, copied=done['copied'])
    return done


# ---------------------------------------------------------------- Modifica in…

EDITORS = ['Affinity', 'Affinity Photo 2', 'Affinity Photo', 'Adobe Photoshop 2026', 'Adobe Photoshop 2025', 'Pixelmator Pro',
           'Photomator', 'Acorn', 'GIMP', 'Krita', 'Preview']


def editors():
    out = []
    for name in EDITORS:
        for d in ('/Applications', os.path.expanduser('~/Applications'), '/System/Applications'):
            if os.path.exists(os.path.join(d, name + '.app')):
                out.append(name); break
    extra = core.settings().get('edit_app')
    if extra and extra not in out:
        out.insert(0, extra)
    return out


_watch = {}            # copia di lavoro -> {asset, item, app, mtime}
_watch_started = False


def edit_in(lib, asset_uuid, app):
    a = lib.db.execute('SELECT * FROM asset WHERE uuid = ?', (asset_uuid,)).fetchone()
    if not a:
        raise ValueError('no such file in the library')
    item = lib.db.execute('SELECT i.* FROM item i JOIN item_asset ia ON ia.item_id = i.id WHERE ia.asset_id = ? LIMIT 1', (a['id'],)).fetchone()
    src = lib.asset_path(a)
    d = os.path.join(lib.path, 'edits', item['uuid'] if item else 'loose')
    os.makedirs(d, exist_ok=True)
    stem, ext = os.path.splitext(a['original_name'])
    work = os.path.join(d, f'{stem} edit {time.strftime("%Y%m%d-%H%M%S")}{ext.lower()}')
    shutil.copy2(src, work)                              # una copia: l'originale resta com'e'
    _watch[work] = {'asset': a['id'], 'item': item['id'] if item else None, 'app': app, 'mtime': os.path.getmtime(work),
                    'sha': a['sha256']}
    _save_watch(lib)
    start_watch(lib)
    subprocess.run(['open', '-a', app, work], check=True)
    lib.log('edit_open', 'asset', a['uuid'], app=app, work=work)
    return work


def _save_watch(lib):
    with lib.db:
        lib.db.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('edit_watches', ?)", (json.dumps(_watch),))


def start_watch(lib):
    # ogni 2 s: una copia di lavoro salvata (e ferma da 2 s) entra nella libreria come nuova versione
    global _watch_started
    if _watch_started:
        return
    _watch_started = True
    row = lib.db.execute("SELECT value FROM setting WHERE key = 'edit_watches'").fetchone()
    if row:
        _watch.update({k: v for k, v in json.loads(row[0]).items() if os.path.exists(k)})

    def loop():
        while True:
            time.sleep(2)
            for work, w in list(_watch.items()):
                try:
                    m = os.path.getmtime(work)
                except OSError:
                    _watch.pop(work, None); continue
                if m != w['mtime'] and time.time() - m > 2:
                    w['mtime'] = m
                    try:
                        take_edit(library(), work, w)
                    except Exception as e:
                        print('edit import failed:', e)
                    _save_watch(library())
    threading.Thread(target=loop, daemon=True).start()


def take_edit(lib, work, w):
    from .db import sha256
    if sha256(work) == w.get('sha'):
        return None                                      # salvato senza cambiare niente
    aid, new = lib.add_asset(work, managed=True, derived_from=w['asset'], made_with=w['app'])
    w['sha'] = sha256(work)
    if w.get('item'):
        lib.link_asset(w['item'], aid, role='edit')
    return aid


# ---------------------------------------------------------------- per l'interfaccia

def reader_of():
    eng = core.settings().get('ocr_engine') or 'vision'
    return (eng.split(':', 1)[0], eng.split(':', 1)[1]) if ':' in eng else (eng, eng)


def place_subtree(lib, uuid):
    # un posto e tutti quelli dentro (id interi: si possono mettere in una query)
    return [r[0] for r in lib.db.execute('WITH RECURSIVE sub(id) AS (SELECT id FROM place WHERE uuid = ? UNION SELECT p.id FROM place p JOIN sub ON p.parent_id = sub.id) '
                                          'SELECT id FROM sub', (uuid,))] or [-1]


def regions_in(lib, ids):
    # i fogli vivi il cui posto (con l'eredita') e' fra questi
    ids = set(ids)
    return [rid for (rid,) in lib.db.execute("SELECT id FROM region WHERE removed_at IS NULL AND parent_id IS NULL AND kind = 'sheet'")
            if effective_place(lib, rid)[0] in ids]


def _in_place_sql(lib, ids, item_col='i.id'):
    # le fonti con almeno un foglio (o loro stesse) in quei posti; i pezzi contano anche per l'oggetto da cui vengono
    rs = ','.join(str(x) for x in regions_in(lib, ids)) or '-1'
    s = ','.join(str(int(x)) for x in ids)
    return (f" AND ({item_col} IN (SELECT item_id FROM region WHERE id IN ({rs})) OR {item_col} IN (SELECT parent_id FROM item WHERE id IN (SELECT item_id FROM region WHERE id IN ({rs}))) "
            f"OR {item_col} IN (SELECT id FROM item WHERE place_id IN ({s})))")


def item_list(lib, q=None, limit=500, offset=0, series=None, place=None):
    if q:
        uu = [r['uuid'] for r in lib.search(q, limit=limit)]
        if not uu:
            return []
        rows = lib.db.execute(f"SELECT * FROM item WHERE uuid IN ({','.join('?' * len(uu))})", uu).fetchall()
        rows.sort(key=lambda r: uu.index(r['uuid']))
    else:
        rows = lib.db.execute("SELECT * FROM item i WHERE trashed_at IS NULL AND parent_id IS NULL AND kind != 'cut'"
                              + (' AND series_id IS NULL' if series == 'none' else ' AND series_id = (SELECT id FROM series WHERE uuid = ?)' if series else '')
                              + (_in_place_sql(lib, place_subtree(lib, place)) if place else '')
                              + ' ORDER BY date DESC, id DESC LIMIT ? OFFSET ?',
                              ((series,) if series and series != 'none' else ()) + (limit, offset)).fetchall()
    out = []
    for it in rows:
        a = lib.db.execute("SELECT a.* FROM asset a JOIN item_asset ia ON ia.asset_id = a.id WHERE ia.item_id = ? ORDER BY ia.role = 'edit', ia.position LIMIT 1", (it['id'],)).fetchone()
        n = lib.db.execute('SELECT (SELECT COUNT(*) FROM item_asset WHERE item_id = ?), (SELECT COUNT(*) FROM region WHERE item_id = ?),'
                           ' (SELECT COUNT(*) FROM reading r JOIN region g ON g.id = r.region_id WHERE g.item_id = ?)', (it['id'],) * 3).fetchone()
        sr = lib.db.execute('SELECT name FROM series WHERE id = ?', (it['series_id'],)).fetchone() if it['series_id'] else None
        cuts = [rel_of(lib, c) for c in lib.db.execute("SELECT a.* FROM asset a JOIN item_asset ia ON ia.asset_id = a.id WHERE ia.item_id = ? AND ia.role = 'cutout' "
                                                         "ORDER BY a.original_name LIMIT 4", (it['id'],))]
        out.append({'uuid': it['uuid'], 'title': it['title'], 'kind': it['kind'], 'date': it['date'], 'batch': sr[0] if sr else None,
                    'files': n[0], 'regions': n[1], 'texts': n[2], 'thumb': rel_of(lib, a) if a else None,
                    'cut_thumbs': [c for c in cuts if c],
                    'cuts': lib.db.execute("SELECT COUNT(*) FROM item_asset WHERE item_id = ? AND role = 'cutout'", (it['id'],)).fetchone()[0],
                    'dpi': a['dpi'] if a else None, 'width': a['width'] if a else None, 'height': a['height'] if a else None,
                    'added': it['created_at']})
    return out


def item_detail(lib, uuid):
    it = lib.db.execute('SELECT * FROM item WHERE uuid = ?', (uuid,)).fetchone()
    if not it:
        return None
    assets = [dict(r) | {'rel': rel_of(lib, r), 'capture': capture_of(lib, r['id'])} for r in lib.db.execute(
        'SELECT a.*, ia.role FROM asset a JOIN item_asset ia ON ia.asset_id = a.id WHERE ia.item_id = ? ORDER BY ia.position', (it['id'],))]
    regions = [dict(r) for r in lib.db.execute("SELECT * FROM region WHERE item_id = ? AND removed_at IS NULL AND parent_id IS NULL AND kind = 'sheet' "
                                                "AND asset_id IN (SELECT asset_id FROM item_asset WHERE item_id = ? AND role != 'cutout') ORDER BY position", (it['id'], it['id']))]
    for g in regions:
        t = lib.db.execute('SELECT plain, engine, model, corrected_version FROM current_text WHERE region_id = ? ORDER BY created_at DESC LIMIT 1', (g['id'],)).fetchone()
        g['text'] = dict(t) if t else None
        g['geometry'] = json.loads(g['geometry'])
        e = lib.db.execute('SELECT path, created_at FROM cut WHERE region_id = ? ORDER BY created_at DESC, id DESC LIMIT 1', (g['id'],)).fetchone()
        g['kept'] = where_kept(lib, g['id'])
        g['cutout'] = None
        if e and os.path.exists(e['path']):
            p = os.path.realpath(e['path'])
            g['cutout'] = {'rel': core.relpath(p) if p.startswith(core.ROOT + os.sep) else None,
                           'name': os.path.basename(p), 'at': e['created_at']}
    events = [dict(r) for r in lib.db.execute(
        "SELECT at, type, outcome, detail FROM event WHERE entity_uuid IN (SELECT uuid FROM asset WHERE id IN (SELECT asset_id FROM item_asset WHERE item_id = ?)) OR entity_uuid = ? ORDER BY at DESC LIMIT 30",
        (it['id'], it['uuid']))]
    parts = [dict(r) for r in lib.db.execute('SELECT uuid, title FROM item WHERE parent_id = ? ORDER BY id', (it['id'],))]
    sr = lib.db.execute('SELECT uuid, name FROM series WHERE id = ?', (it['series_id'],)).fetchone() if it['series_id'] else None
    pl = lib.db.execute('SELECT uuid FROM place WHERE id = ?', (it['place_id'],)).fetchone() if it['place_id'] else None
    return {'item': dict(it, batch=sr['name'] if sr else None, series_uuid=sr['uuid'] if sr else None, place=pl[0] if pl else None,
                         kept=address(lib, it['place_id'])), 'assets': assets, 'regions': regions,
            'events': events, 'parts': parts}


def info(lib):
    q = lambda s: lib.db.execute(s).fetchone()[0]
    return {'path': lib.path, 'name': lib.meta('name'), 'uuid': lib.meta('uuid'),
            'items': q('SELECT COUNT(*) FROM item WHERE trashed_at IS NULL'), 'files': q('SELECT COUNT(*) FROM asset'),
            'texts': q('SELECT COUNT(*) FROM reading'), 'cutouts': q("SELECT COUNT(*) FROM item_asset WHERE role = 'cutout'"),
            'edits': q("SELECT COUNT(*) FROM item_asset WHERE role = 'edit'"), 'packed': core.sc.PACKED}


# ---------------------------------------------------------------- sincronia con lo studio (dal vivo)
# Ogni salvataggio dello studio (Detect, ritocchi, testo, export) aggiorna l'oggetto nella libreria.

def item_for(lib, rel):
    # l'oggetto di una scansione degli originali (lo crea se non c'e')
    path = core.abspath(rel)
    aid, _ = lib.add_asset(path, managed=False)
    row = lib.db.execute("SELECT item_id FROM item_asset WHERE asset_id = ? ORDER BY position LIMIT 1", (aid,)).fetchone()
    if row:
        return row[0], aid
    stem = os.path.splitext(os.path.basename(path))[0]
    date = time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(path)))
    return lib.new_item(stem, kind='scan', batch=series_of(rel), date=date, assets=[aid]), aid


def sync_rel(rel):
    # (prima: copiava lo stato JSON nella libreria. Ora lo stato E' la libreria: non c'e' niente da copiare)
    return None


def apply_state(lib, rel, st, iid, aid):
    # uno stato salvato dallo studio diventa righe: parti, ritocchi, rotazione, inclusione, nome, colore,
    # testo, aree secondarie, aree sciolte. Poi le conseguenze: tagli rifatti o girati, metadati, diario.
    # le parti di questo file per id dello studio; a parita' di id vince quella viva (le tolte sono storia)
    have = {r['studio_id']: r for r in lib.db.execute(
        "SELECT id, json_extract(source, '$.studio_id') AS studio_id, geometry, ops, rotation, export_on, label, position, removed_at, "
        "json_extract(source, '$.holes') AS holes, json_extract(source, '$.src') AS src, json_extract(source, '$.poly0') AS poly0 "
        "FROM region WHERE asset_id = ? AND parent_id IS NULL AND kind = 'sheet' ORDER BY (removed_at IS NULL), id", (aid,))}
    seen, recut_needed = set(), False
    only = set()                 # parti cambiate solo nella sagoma (contorno, ritocchi, buchi): si rifa' solo il loro taglio
    has_cut = bool(lib.db.execute('SELECT 1 FROM cut WHERE region_id IN (SELECT id FROM region WHERE asset_id = ?) LIMIT 1', (aid,)).fetchone())
    for i, sh in enumerate(st.get('sheets') or []):
        seen.add(sh['id'])
        geom, ops = json.dumps({'poly': sh['poly']}), json.dumps(sh.get('ops') or [])
        color = sh.get('color') or COLORS[i % len(COLORS)]
        rot, on, label = int(sh.get('rot') or 0), 0 if sh.get('on') is False else 1, sh.get('label') or None
        r = have.get(sh['id'])
        if r is not None and (json.loads(r['src'] or 'null') != sh.get('src') or json.loads(r['poly0'] or 'null') != sh.get('poly0')):
            # stesso id ma un'altra origine (un nuovo rilevamento ha ridato "s1", o una parte nuova ha preso l'id di
            # una tolta): non e' la stessa parte. Quella di prima va nella storia con l'id ritirato (con i suoi testi
            # e tagli); la nuova ha il suo record e non eredita niente
            lib.db.execute("UPDATE region SET source = json_set(source, '$.studio_id', ?), removed_at = COALESCE(removed_at, ?) WHERE id = ?",
                           (f'{sh["id"]}~{r["id"]}', now(), r['id']))
            lib.db.execute('UPDATE region SET removed_at = COALESCE(removed_at, ?) WHERE parent_id = ?', (now(), r['id']))
            lib.db.commit()
            if not r['removed_at']:
                recut_needed = recut_needed or has_cut
                lib.log('replace', 'region', None, studio_id=sh['id'], why='same id, new origin')
            have.pop(sh['id'])
            r = None
        if r is None:
            src = {'studio_id': sh['id'], 'studio_rel': rel, 'engine': sh.get('engine'), 'src': sh.get('src'),
                   'poly0': sh.get('poly0'), 'holes': sh.get('holes'), 'base': sh.get('base')}
            rid = lib.add_region(iid, aid, 'sheet', {'poly': sh['poly']}, label=label, source=src, color=color)
            recut_needed = recut_needed or has_cut
        else:
            rid = r['id']
            if r['removed_at']:                                   # tornata (annulla): di nuovo viva
                # il suo numero nel posto, se intanto l'ha preso un'altra cosa, non torna (la regola vince)
                lib.db.execute("UPDATE region SET place_number = NULL WHERE id = ? AND place_number IS NOT NULL AND (EXISTS (SELECT 1 FROM region o WHERE o.id != region.id "
                               "AND o.place_id = region.place_id AND o.place_number = region.place_number AND o.removed_at IS NULL) OR EXISTS (SELECT 1 FROM place p "
                               "WHERE p.parent_id = region.place_id AND p.number = region.place_number))", (rid,))
                lib.db.execute('UPDATE region SET removed_at = NULL WHERE id = ?', (rid,))
                recut_needed = recut_needed or has_cut
            if r['rotation'] != rot:
                # girata: i tagli gia' fatti girano anche loro (senza perdita)
                lib.db.execute('UPDATE region SET rotation = ? WHERE id = ?', (rot, rid)); lib.db.commit()
                rotate_region_cutouts(lib, rid, (rot - int(r['rotation'] or 0)) % 360)
            if (r['export_on'], r['label'], r['position']) != (on, label, i):
                recut_needed = recut_needed or has_cut           # nome, ordine, inclusione: cambiano i nomi, si rifanno tutti
                lib.log('edit', 'region', None, studio_id=sh['id'])
            elif (r['geometry'], r['ops']) != (geom, ops) or json.loads(r['holes'] or 'null') != sh.get('holes'):
                if has_cut:
                    only.add(sh['id'])                           # solo la sagoma: solo il suo taglio
                lib.log('edit', 'region', None, studio_id=sh['id'])
        lib.db.execute("UPDATE region SET geometry = ?, ops = ?, rotation = ?, export_on = ?, label = ?, position = ?, color = ?, modified_at = ?, "
                       "source = json_set(COALESCE(source, '{}'), '$.holes', json(?), '$.poly0', json(?), '$.src', json(?), '$.engine', ?, '$.studio_rel', ?) "
                       "WHERE id = ?", (geom, ops, rot, on, label, i, color, now(), json.dumps(sh.get('holes')), json.dumps(sh.get('poly0')),
                                        json.dumps(sh.get('src')), sh.get('engine'), rel, rid))
        lib.db.commit()
        sync_text(lib, aid, rid, sh.get('ocr'))
        # aree secondarie: zone figlie, ognuna con il suo testo
        sub = {r['sid']: (r['id'], r['removed_at']) for r in lib.db.execute(
            "SELECT id, json_extract(source, '$.studio_area') AS sid, removed_at FROM region WHERE parent_id = ?", (rid,))}
        for k, ar in enumerate(sh.get('areas') or []):
            key = f'{sh["id"]}/{ar["id"]}'
            if key in sub:
                cid, gone = sub.pop(key)
                lib.db.execute('UPDATE region SET geometry = ?, position = ?, removed_at = NULL, color = ? WHERE id = ?',
                               (json.dumps({'box': ar['box']}), k, color, cid))
                lib.db.commit()
            else:
                cid = lib.add_region(iid, aid, 'text', {'box': ar['box']}, parent_id=rid, source={'studio_area': key, 'studio_rel': rel}, color=color)
            sync_text(lib, aid, cid, ar.get('text'), reader=ar.get('reader'))
        for key, (cid, gone) in sub.items():                # area tolta: non si vede piu', resta nella storia
            if not gone:
                lib.db.execute('UPDATE region SET removed_at = ? WHERE id = ?', (now(), cid))
        lib.db.commit()
    # parti tolte: non si vedono piu', restano nella storia; il loro taglio esce
    for sid, r in have.items():
        if sid not in seen and not r['removed_at']:
            lib.db.execute('UPDATE region SET removed_at = ? WHERE id = ?', (now(), r['id']))
            lib.db.execute("UPDATE region SET removed_at = ? WHERE parent_id = ? AND removed_at IS NULL", (now(), r['id']))
            recut_needed = recut_needed or has_cut
            lib.log('remove', 'region', None, studio_id=sid)
    # aree sciolte (lette fuori da ogni parte)
    loose = {r['lid']: (r['id'], r['removed_at']) for r in lib.db.execute(
        "SELECT id, json_extract(source, '$.studio_loose') AS lid, removed_at FROM region WHERE asset_id = ? AND parent_id IS NULL AND kind = 'text'", (aid,))}
    for k, ar in enumerate(st.get('loose') or []):
        if ar['id'] in loose:
            cid, _ = loose.pop(ar['id'])
            lib.db.execute('UPDATE region SET geometry = ?, position = ?, removed_at = NULL WHERE id = ?', (json.dumps({'box': ar['box']}), 1000 + k, cid))
            lib.db.commit()
        else:
            cid = lib.add_region(iid, aid, 'text', {'box': ar['box']}, source={'studio_loose': ar['id'], 'studio_rel': rel}, color='#888888')
        sync_text(lib, aid, cid, ar.get('text'), reader=ar.get('reader'))
    for lid, (cid, gone) in loose.items():
        if not gone:
            lib.db.execute('UPDATE region SET removed_at = ? WHERE id = ?', (now(), cid))
    lib.db.commit()
    # il testo nei metadati dei tagli: dopo il salvataggio, fuori dal suo lucchetto (store.save lo chiama)
    pending = [r[0] for r in lib.db.execute('SELECT DISTINCT region_id FROM cut WHERE region_id IN (SELECT id FROM region WHERE asset_id = ?)', (aid,))]
    if recut_needed:
        schedule_recut(rel)
    elif only:
        schedule_recut(rel, only=only)
    schedule_journal()
    if iid:
        lib.touched(iid)
    return pending


def sync_text(lib, aid, rid, text, reader=None):
    if text is None:
        return
    cur = lib.db.execute('SELECT reading_id, plain FROM current_text WHERE region_id = ? ORDER BY created_at DESC LIMIT 1', (rid,)).fetchone()
    if cur is None:
        e_, m_ = reader_of()
        lib.add_reading(aid, e_, text, region_id=rid, model=m_)
    elif cur['plain'] != text:
        lib.correct(cur['reading_id'], text)


def on_export(rel, written, superseded=None):
    # i tagli scritti diventano file dell'oggetto: ruolo "cutout", legati alla fonte e alla parte
    lib = library(create=False)
    if not lib:
        return
    from . import store
    a = store.asset_for(lib, rel, create=True)
    aid = a['id']
    iid = lib.db.execute('SELECT item_id FROM item_asset WHERE asset_id = ? ORDER BY position LIMIT 1', (aid,)).fetchone()[0]
    for w in written:
        if w.get('status') not in ('written', 'identical') or not os.path.exists(w['path']):
            continue
        if w.get('moved_old'):
            # il taglio di prima con questo nome e' andato nella storia: il suo record lo segue
            old = lib.db.execute('SELECT id, uuid FROM asset WHERE path = ?', (w['path'],)).fetchone()
            if old:
                lib.db.execute('UPDATE asset SET path = ? WHERE id = ?', (w['moved_old'], old['id']))
                lib.db.execute("DELETE FROM item_asset WHERE asset_id = ? AND role = 'cutout'", (old['id'],))
                lib.db.execute('UPDATE cut SET path = ? WHERE path = ? AND sha256 != ?', (w['moved_old'], w['path'], sha256(w['path'])))
                lib.db.commit()
                lib.log('superseded', 'asset', old['uuid'], old_path=w['path'], kept_at=w['moved_old'], why='re-cut: its part changed')
        cid, _ = lib.add_asset(w['path'], managed=False, derived_from=aid, made_with='Scan Studio')
        lib.db.execute("INSERT OR IGNORE INTO item_asset (item_id, asset_id, role, position) VALUES (?, ?, 'cutout', 100 + ?)", (iid, cid, cid))
        reg = lib.db.execute("SELECT id FROM region WHERE asset_id = ? AND json_extract(source, '$.studio_id') = ? AND removed_at IS NULL", (aid, w.get('id'))).fetchone()
        if reg:
            link_cutout_texts(lib, reg[0], cid)
        a = lib.db.execute('SELECT sha256 FROM asset WHERE id = ?', (cid,)).fetchone()
        if reg:
            # un percorso e' il taglio di UNA parte: se prima era di un'altra, quel record si ritira (resta nel registro)
            for o in lib.db.execute('SELECT id, region_id FROM cut WHERE path = ? AND (region_id IS NULL OR region_id != ?)', (w['path'], reg[0])).fetchall():
                lib.db.execute('DELETE FROM cut WHERE id = ?', (o['id'],))
                lib.log('reassigned', 'cut', None, path=w['path'], from_region=o['region_id'], to_region=reg[0])
        if not lib.db.execute('SELECT 1 FROM cut WHERE path = ? AND sha256 = ? AND region_id IS ?', (w['path'], a['sha256'], reg[0] if reg else None)).fetchone():
            from .db import new_uuid
            lib.db.execute('INSERT INTO cut (uuid, item_id, region_id, format, path, sha256, settings, created_at) VALUES (?,?,?,?,?,?,?,?)',
                           (new_uuid(), iid, reg[0] if reg else None, os.path.splitext(w['path'])[1][1:].lower(), w['path'], a['sha256'],
                            json.dumps({'tilt': w.get('tilt'), 'size': w.get('size')}), now()))
        lib.db.commit()
    if superseded:
        now_paths = {os.path.realpath(w['path']) for w in written if w.get('status') in ('written', 'identical')}
        for rid, old in superseded.items():
            if os.path.realpath(old) not in now_paths:
                _supersede(lib, old, 'its part changed (name, order or excluded from the cut)')
    lib.log('recut' if superseded else 'cut', 'item', lib.db.execute('SELECT uuid FROM item WHERE id = ?', (iid,)).fetchone()[0], files=len(written))
    for rid in [r[0] for r in lib.db.execute('SELECT DISTINCT region_id FROM cut WHERE item_id = ? AND region_id IS NOT NULL', (iid,))]:
        refresh_cutout_text(lib, rid)
    lib.touched(iid)


def import_cutouts(lib, rel):
    # ritagli gia' fatti prima della libreria: quelli col nome che lo studio darebbe adesso
    try:
        names = core.out_names(rel)
    except Exception:
        return
    found = [{'id': sid, 'path': p, 'status': 'identical'} for sid, p in names if os.path.exists(p)]
    stem = os.path.splitext(os.path.basename(rel))[0]
    d = core.abspath(os.path.join('cut', core.batch_of(rel)))
    if not found and os.path.isdir(d):              # ritagli dell'agente senza stato dello studio
        import re
        # solo "<nome>.png" o "<nome> a.png", "<nome> b.png"…: "quaderno 6" non e' un pezzo di "quaderno"
        pat = re.compile(re.escape(stem) + r'( [a-z])?')
        found = [{'id': None, 'path': os.path.join(d, f), 'status': 'identical'} for f in sorted(os.listdir(d))
                 if core.is_image(f) and pat.fullmatch(os.path.splitext(f)[0])]
    if found:
        on_export(rel, found)


def sync_async(fn, *a):
    threading.Thread(target=lambda: _safe(fn, *a), daemon=True).start()


def _safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:
        print('library sync:', type(e).__name__, e)


# ---------------------------------------------------------------- il testo segue i ritagli
# Il testo di una zona cambia dopo l'export (riletto, corretto): il ritaglio esportato si aggiorna.
# Solo i metadati (XMP/IPTC/EXIF), mai i pixel; nel file anche i riferimenti alla libreria
# (oggetto, zona, lettura e versione), cosi' il file "punta" al suo testo. Il nuovo checksum del
# file entra nel catalogo con l'evento che spiega perche' e' cambiato.

def region_texts(lib, region_id):
    # i testi attuali della zona e delle zone dentro di lei, in ordine
    ids = [region_id] + [r[0] for r in lib.db.execute(
        'WITH RECURSIVE sub(id) AS (SELECT id FROM region WHERE parent_id = ? AND removed_at IS NULL UNION ALL SELECT r.id FROM region r JOIN sub ON r.parent_id = sub.id '
        'WHERE r.removed_at IS NULL) SELECT id FROM sub', (region_id,))]
    return lib.db.execute(f"SELECT * FROM current_text WHERE region_id IN ({','.join('?' * len(ids))}) ORDER BY created_at", ids).fetchall()


def link_cutout_texts(lib, region_id, asset_id):
    for t in region_texts(lib, region_id):
        lib.db.execute('INSERT OR IGNORE INTO text_link (reading_id, asset_id) VALUES (?, ?)', (t['reading_id'], asset_id))
    lib.db.commit()


# i file dei tagli li cambia uno alla volta: un taglio rifatto (che sposta i vecchi nella storia) e la
# riscrittura del testo nei metadati non si incrociano mai sullo stesso file
files_lock = threading.RLock()


def refresh_cutout_text(lib, region_id):
    with files_lock:
        return _refresh_cutout_text(lib, region_id)


def _refresh_cutout_text(lib, region_id):
    from .db import sha256
    texts = region_texts(lib, region_id)
    reg = lib.db.execute('SELECT r.uuid, i.uuid AS item FROM region r JOIN item i ON i.id = r.item_id WHERE r.id = ?', (region_id,)).fetchone()
    if not texts or not reg or not core.tool('exiftool'):
        return 0
    plain = '\n\n'.join(t['plain'] for t in texts if t['plain'])
    refs = [f'scanstudio://text/{t["uuid"]}?v={t["corrected_version"] or 0}' for t in texts]
    n = 0
    # solo i tagli attuali: quelli nella storia restano com'erano
    for e in lib.db.execute("SELECT id, path, sha256 FROM cut WHERE region_id = ? AND path NOT LIKE '%/studio-data/replaced/%' AND path NOT LIKE '%/studio-data/trash/%'", (region_id,)).fetchall():
        p = e['path']
        if not os.path.exists(p) or not p.lower().endswith(('.png', '.jxl', '.tif', '.tiff')):
            continue
        a = lib.db.execute('SELECT id, uuid FROM asset WHERE path = ?', (p,)).fetchone()
        if a:
            link_cutout_texts(lib, region_id, a['id'])
        ref = f'scanstudio://cutout/{a["uuid"] if a else ""}?item={reg["item"]}&region={reg["uuid"]}&' + '&'.join(r.split('/')[-1] for r in refs)
        cur = subprocess.run([core.tool('exiftool'), '-s3', '-XMP-dc:Identifier', p], capture_output=True, text=True).stdout.strip()
        if cur == ref:
            continue                                      # gia' allineato
        before = sha256(p)
        os.makedirs(os.path.join(lib.path, 'cache'), exist_ok=True)
        txt = os.path.join(lib.path, 'cache', f'.text-{region_id}-{os.getpid()}-{threading.get_ident()}.txt')   # un nome per chi scrive
        with open(txt, 'w', encoding='utf-8') as f:
            f.write(plain)
        r = subprocess.run([core.tool('exiftool'), '-q', '-q', '-m', '-overwrite_original',
                            f'-XMP-dc:Description<={txt}', f'-IPTC:Caption-Abstract<={txt}', f'-IFD0:ImageDescription<={txt}',
                            f'-XMP-dc:Identifier={ref}', '-XMP-dc:Relation=',
                            f'-XMP-dc:Relation+=scanstudio://item/{reg["item"]}', f'-XMP-dc:Relation+=scanstudio://region/{reg["uuid"]}']
                           + [f'-XMP-dc:Relation+={x}' for x in refs] + [p],
                           capture_output=True, text=True, timeout=120)
        os.remove(txt)
        if r.returncode != 0:
            lib.log('metadata', 'region', reg['uuid'], 'fail', path=p, error=r.stderr[-200:])
            continue
        after, size = sha256(p), os.path.getsize(p)
        lib.db.execute('UPDATE cut SET sha256 = ? WHERE id = ?', (after, e['id']))
        lib.db.execute('UPDATE asset SET sha256 = ?, size = ? WHERE sha256 = ? AND path = ?', (after, size, before, p))
        lib.db.commit()
        lib.log('metadata', 'region', reg['uuid'], path=p, why='text changed after export', old_sha256=before, new_sha256=after,
                texts=refs)
        n += 1
    return n


# ---------------------------------------------------------------- tre cose: oggetti, ritagli, testi

def text_list(lib, q=None, limit=500):
    # ogni testo come cosa a se': dove sta (oggetto › zona) e quali ritagli lo mostrano
    # l'ultimo testo di ogni zona (o di ogni lettura intera); le letture prima restano nella storia
    latest = ("SELECT t.* FROM current_text t WHERE (t.region_id IS NULL OR (t.created_at = "
              "(SELECT MAX(created_at) FROM reading WHERE region_id = t.region_id) AND "
              "(SELECT removed_at FROM region WHERE id = t.region_id) IS NULL))")
    if q:
        rows = lib.db.execute(f"SELECT * FROM ({latest}) WHERE plain LIKE ? ORDER BY created_at DESC LIMIT ?", (f'%{q}%', limit)).fetchall()
    else:
        rows = lib.db.execute(f'SELECT * FROM ({latest}) ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    out = []
    for t in rows:
        reg = lib.db.execute("SELECT r.uuid, r.label, r.kind, r.color, r.position, i.uuid AS item, i.title, json_extract(r.source, '$.studio_rel') AS srel, "
                             "COALESCE(json_extract(r.source, '$.studio_id'), json_extract(p.source, '$.studio_id')) AS sid "
                             "FROM region r JOIN item i ON i.id = r.item_id LEFT JOIN region p ON p.id = r.parent_id WHERE r.id = ?",
                             (t['region_id'],)).fetchone() if t['region_id'] else None
        whole = None if reg else lib.db.execute('SELECT i.uuid AS item, i.title FROM item i JOIN item_asset ia ON ia.item_id = i.id WHERE ia.asset_id = ? LIMIT 1',
                                                (t['asset_id'],)).fetchone()
        cuts = [{'uuid': a['uuid'], 'rel': rel_of(lib, a), 'name': a['original_name']} for a in lib.db.execute(
            'SELECT a.* FROM asset a JOIN text_link l ON l.asset_id = a.id WHERE l.reading_id = ?', (t['reading_id'],))]
        out.append({'uuid': t['uuid'], 'plain': t['plain'], 'engine': t['engine'], 'model': t['model'], 'at': t['created_at'],
                    'version': t['corrected_version'] or 0,
                    'item': (reg or whole)['item'] if (reg or whole) else None, 'title': (reg or whole)['title'] if (reg or whole) else '',
                    'region': {'uuid': reg['uuid'], 'label': reg['label'] or f'{reg["kind"]} {reg["position"] + 1}', 'color': reg['color'],
                               'studio_rel': reg['srel'], 'studio_id': reg['sid']} if reg else None,
                    'whole': reg is None, 'cutouts': cuts,
                    'rel': rel_of(lib, lib.db.execute('SELECT * FROM asset WHERE id = ?', (t['asset_id'],)).fetchone())})
    return out


def cutout_list(lib, limit=1000, series=None, place=None):
    out = []
    flt = " AND i.series_id IS NULL" if series == 'none' else " AND i.series_id = (SELECT id FROM series WHERE uuid = ?)" if series else ""
    if place:
        rs = ','.join(str(x) for x in regions_in(lib, place_subtree(lib, place))) or '-1'
        flt += f" AND a.path IN (SELECT x.path FROM cut x WHERE x.region_id IN ({rs}))"
    for a in lib.db.execute("SELECT a.*, i.uuid AS item, i.title FROM asset a JOIN item_asset ia ON ia.asset_id = a.id JOIN item i ON i.id = ia.item_id "
                            "WHERE ia.role = 'cutout'" + flt + " ORDER BY i.title COLLATE NOCASE, a.original_name LIMIT ?",
                            ((series,) if series and series != 'none' else ()) + (limit,)):
        e = lib.db.execute('SELECT r.uuid, r.label, r.kind, r.color, r.position FROM cut x JOIN region r ON r.id = x.region_id WHERE x.path = ? ORDER BY x.id DESC LIMIT 1',
                           (a['path'],)).fetchone()
        rows = [dict(t) for t in lib.db.execute(
            'SELECT t.uuid, t.plain, t.model, t.engine, t.corrected_version, t.region_id, t.created_at FROM current_text t JOIN text_link l ON l.reading_id = t.reading_id '
            'WHERE l.asset_id = ? ORDER BY t.created_at DESC', (a['id'],))]
        texts, seen = [], set()
        for t in rows:                                  # l'ultimo per zona; gli altri contano come versioni precedenti
            k = t['region_id'] or t['uuid']
            if k in seen:
                texts[[x.get('_k') for x in texts].index(k)]['earlier'] += 1; continue
            seen.add(k); texts.append(dict(t, _k=k, earlier=0))
        rid = lib.db.execute('SELECT region_id FROM cut WHERE path = ? AND region_id IS NOT NULL ORDER BY id DESC LIMIT 1', (a['path'],)).fetchone()
        kept = where_kept(lib, rid[0]) if rid else None
        out.append({'uuid': a['uuid'], 'rel': rel_of(lib, a), 'name': a['original_name'], 'item': a['item'], 'title': a['title'], 'added': a['imported_at'], 'kept': kept,
                    'width': a['width'], 'height': a['height'], 'dpi': a['dpi'], 'sha256': a['sha256'],
                    'region': {'uuid': e['uuid'], 'label': e['label'] or f'{e["kind"]} {e["position"] + 1}', 'color': e['color']} if e else None,
                    'texts': texts})
    return out


# ---------------------------------------------------------------- testo dei ritagli, a lotti
# Il testo si legge di solito sui ritagli gia' fatti: ogni ritaglio letto intero, il testo legato a lui
# e alla sua zona, e scritto anche nello stato dello studio (il pannello Testo lo mostra).

def attach_doc_text(lib, a, text, reader=None):
    # il testo letto su un file intero entra nella libreria:
    #  un taglio -> e' il testo della sua parte (foglio della fonte, metadati del taglio, diario)
    #  una fonte -> e' il testo della fonte intera
    e_, m_ = reader or reader_of()
    e = lib.db.execute('SELECT region_id FROM cut WHERE path = ? ORDER BY id DESC LIMIT 1', (lib.asset_path(a),)).fetchone()
    rid = e['region_id'] if e else None
    cur = lib.db.execute('SELECT reading_id, plain FROM current_text WHERE ' + ('region_id = ?' if rid else 'region_id IS NULL AND asset_id = ?') +
                         ' ORDER BY created_at DESC LIMIT 1', (rid or a['id'],)).fetchone()
    if cur and cur['plain'] == text:
        r = cur['reading_id']                              # gia' cosi': niente doppioni
    else:
        r = lib.add_reading(a['id'], e_, text, region_id=rid, model=m_, params={'read_on': 'cut' if rid else 'whole file'})
    lib.db.execute('INSERT OR IGNORE INTO text_link (reading_id, asset_id) VALUES (?, ?)', (r, a['id']))
    lib.db.commit()
    if rid:
        src = lib.db.execute("SELECT json_extract(source, '$.studio_rel'), json_extract(source, '$.studio_id') FROM region WHERE id = ?", (rid,)).fetchone()
        if src and src[0]:
            st = core.load_state(src[0], create=False)
            for sh in (st or {}).get('sheets', []):
                if sh['id'] == src[1] and sh.get('ocr') != text:
                    sh['ocr'] = text
                    core.save_state(st)
                    break
        refresh_cutout_text(lib, rid)
    schedule_journal()
    return r


def on_read_doc(rel, text):
    # "leggi il documento intero" dallo studio (galleria, editor): passa dalla libreria come tutto il resto
    lib = library(create=False)
    if not lib:
        return
    p = os.path.realpath(core.abspath(rel))
    a = lib.db.execute('SELECT * FROM asset WHERE path = ?', (p,)).fetchone()
    if not a and rel.startswith('originals/'):
        item_for(lib, rel)
        a = lib.db.execute('SELECT * FROM asset WHERE path = ?', (p,)).fetchone()
    if a:
        attach_doc_text(lib, a, text)


def import_read_cache(lib):
    # letture di documenti interi gia' fatte prima (studio-data/text): dentro la libreria
    for a in lib.db.execute('SELECT * FROM asset').fetchall():
        rel = rel_of(lib, a)
        if not rel or not os.path.exists(lib.asset_path(a)):
            continue
        for p in glob.glob(os.path.join(core.DATA, 'text', core.file_key(rel) + '-*.md')):
            attach_doc_text(lib, a, open(p, encoding='utf-8').read())


def read_cutouts(lib, uuids, progress=None, log=print):
    eng = core.settings().get('ocr_engine') or 'vision'
    done = []
    for k, u in enumerate(uuids):
        a = lib.db.execute('SELECT * FROM asset WHERE uuid = ?', (u,)).fetchone()
        rel = rel_of(lib, a) if a else None
        if not rel:
            log(f'{u}: not found'); continue
        if progress:
            progress(k, len(uuids), a['original_name'])
        text = core.read_doc(rel, (lambda i, n, k=k: progress(k + i / n, len(uuids), a['original_name'])) if progress else None)
        attach_doc_text(lib, a, text)
        log(f'{a["original_name"]}: ' + (f'{len(text.splitlines())} line(s)' if text else 'no text'))
        done.append({'uuid': u, 'text': text})
    schedule_journal()
    return done


# ---------------------------------------------------------------- il testo di un file aperto nello studio
def texts_for_rel(lib, rel):
    # i testi che la libreria lega a questo file (un ritaglio: quelli della sua zona)
    p = os.path.realpath(core.abspath(rel))
    a = lib.db.execute('SELECT * FROM asset WHERE path = ?', (p,)).fetchone() or \
        lib.db.execute('SELECT * FROM asset WHERE sha256 = ?', (sha256(p),)).fetchone()
    if not a:
        return []
    out, seen = [], set()
    for t in lib.db.execute('SELECT t.* FROM current_text t WHERE t.reading_id IN (SELECT reading_id FROM text_link WHERE asset_id = ?) '
                            'OR (t.region_id IS NULL AND t.asset_id = ?) ORDER BY t.created_at DESC', (a['id'], a['id'])):
        k = t['region_id'] or t['uuid']
        if k in seen:
            continue
        seen.add(k)
        reg = lib.db.execute('SELECT r.label, r.kind, r.position, r.color, i.title, i.uuid AS item FROM region r JOIN item i ON i.id = r.item_id WHERE r.id = ?',
                             (t['region_id'],)).fetchone() if t['region_id'] else None
        out.append({'reading': t['reading_id'], 'uuid': t['uuid'], 'plain': t['plain'], 'model': t['model'] or t['engine'],
                    'version': t['corrected_version'] or 0, 'title': reg['title'] if reg else '', 'item': reg['item'] if reg else None,
                    'region': (reg['label'] or f'{reg["kind"]} {reg["position"] + 1}') if reg else 'whole file', 'color': reg['color'] if reg else '#8a96a6'})
    return out


def correct_text(lib, reading_id, text):
    # una correzione fatta da qualunque parte: versione nuova nella libreria, poi il foglio della
    # scansione d'origine e i metadati dei ritagli si allineano
    lib.correct(reading_id, text)
    r = lib.db.execute('SELECT region_id FROM reading WHERE id = ?', (reading_id,)).fetchone()
    if r and r['region_id']:
        src = lib.db.execute("SELECT json_extract(source, '$.studio_rel'), json_extract(source, '$.studio_id'), json_extract(source, '$.studio_area'), parent_id FROM region WHERE id = ?",
                             (r['region_id'],)).fetchone()
        if src and src[0]:
            st = core.load_state(src[0], create=False)
            sid, area = (src[2].split('/') if src[2] else (src[1], None))
            for sh in (st or {}).get('sheets', []):
                if sh['id'] != sid:
                    continue
                if area:                                      # un'area secondaria del foglio
                    for a in sh.get('areas') or []:
                        if a['id'] == area and a.get('text') != text:
                            a['text'] = text; core.save_state(st)
                elif sh.get('ocr') != text:
                    sh['ocr'] = text; core.save_state(st)
                break
        refresh_cutout_text(lib, src[3] if src and src[3] else r['region_id'])
    schedule_journal()
    return True


# ---------------------------------------------------------------- rotazione: una sola, della zona
# La rotazione e' della zona (il pezzo). Girare un ritaglio = girare la sua zona; girare la zona nello
# studio = girare i suoi ritagli gia' esportati (senza perdita). Il catalogo aggiorna checksum e misure.

def _refresh_asset_file(lib, path, event, **detail):
    from PIL import Image
    a = lib.db.execute('SELECT * FROM asset WHERE path = ?', (path,)).fetchone()
    if not a or not os.path.exists(path):
        return
    new, size = sha256(path), os.path.getsize(path)
    with Image.open(path) as im:
        w, h = im.size
    lib.db.execute('UPDATE asset SET sha256 = ?, size = ?, width = ?, height = ? WHERE id = ?', (new, size, w, h, a['id']))
    lib.db.execute('UPDATE cut SET sha256 = ? WHERE path = ?', (new, path))
    lib.db.commit()
    lib.log(event, 'asset', a['uuid'], path=path, old_sha256=a['sha256'], new_sha256=new, **detail)


def rotate_region_cutouts(lib, region_id, delta, skip=()):
    # i ritagli gia' fatti di questa zona girano anche loro, cosi' restano uguali al prossimo export
    for e in lib.db.execute('SELECT DISTINCT path FROM cut WHERE region_id = ?', (region_id,)).fetchall():
        p = e['path']
        if p in skip or not os.path.exists(p) or not os.path.realpath(p).startswith(core.ROOT + os.sep):
            continue
        for r in core.rotate_files([core.relpath(p)], delta, log=lambda m: None):    # un JPEG diventa PNG: il percorso nuovo
            _refresh_asset_file(lib, os.path.realpath(core.abspath(r)), 'rotate', degrees=delta, why='its part was rotated')


def on_cutouts_rotated(rels, deg):
    # ritagli girati dalla galleria o aperti nell'editor: e' la loro zona che gira
    lib = library(create=False)
    if not lib:
        return
    for rel in rels:
        p = os.path.realpath(core.abspath(rel))
        _refresh_asset_file(lib, p, 'rotate', degrees=deg, why='cutout rotated')
        e = lib.db.execute('SELECT region_id FROM cut WHERE path = ? AND region_id IS NOT NULL ORDER BY id DESC LIMIT 1', (p,)).fetchone()
        if not e:
            continue
        rid = e['region_id']
        r = lib.db.execute("SELECT rotation, json_extract(source, '$.studio_rel') AS srel, json_extract(source, '$.studio_id') AS sid FROM region WHERE id = ?", (rid,)).fetchone()
        rot = (int(r['rotation'] or 0) + int(deg)) % 360
        lib.db.execute('UPDATE region SET rotation = ?, modified_at = ? WHERE id = ?', (rot, now(), rid))     # prima la libreria...
        lib.db.commit()
        if r['srel']:                                                                                      # ...poi il foglio nello studio
            st = core.load_state(r['srel'], create=False)
            for sh in (st or {}).get('sheets', []):
                if sh['id'] == r['sid']:
                    sh['rot'] = rot
                    core.save_state(st)
                    break
        rotate_region_cutouts(lib, rid, deg, skip={p})            # gli altri ritagli della stessa zona


# ---------------------------------------------------------------- il taglio segue la sua zona
# Una zona gia' tagliata cambia (contorno, ritocchi, buchi, nome, ordine, inclusa o no): il taglio si
# rifa' da solo poco dopo. Il file di prima non si perde: va in studio-data/replaced/ e resta nella storia.
_recut_timers = {}


_recut_only = {}                 # rel -> parti da rifare (None: tutte), sommate fra un ritocco e l'altro


def schedule_recut(rel, delay=2.5, only=None):
    t = _recut_timers.pop(rel, None)
    if t:
        t.cancel()
        prev = _recut_only.get(rel, None)
        only = None if prev is None or only is None else set(prev) | set(only)
    _recut_only[rel] = set(only) if only is not None else None
    t = threading.Timer(delay, lambda: _safe(recut, rel, _recut_only.pop(rel, None)))
    t.daemon = True
    _recut_timers[rel] = t
    t.start()


def cut(rel, follow=True, **kw):
    # tagliare dallo studio: il taglio e la libreria che lo registra, con i file tenuti da un solo scrittore
    with files_lock:
        w = core.export(rel, **kw)
        if follow:
            _safe(on_export, rel, w)
        return w


def recut(rel, only=None):
    with files_lock:                                      # tutto il taglio rifatto: un solo scrittore di file
        _recut(rel, only)


def recut_now(rel, only=None):
    # subito (es. "Fatto" dopo aver ritoccato una parte venendo dal suo taglio), senza aspettare il timer
    t = _recut_timers.pop(rel, None)
    if t:
        t.cancel()
        prev = _recut_only.pop(rel, None)
        only = None if prev is None or only is None else set(prev) | set(only)
    recut(rel, only)


def _recut(rel, only=None):
    lib = library(create=False)
    if not lib:
        return
    p = os.path.realpath(core.abspath(rel))
    a = lib.db.execute('SELECT id FROM asset WHERE path = ?', (p,)).fetchone()
    if not a:
        return
    # i tagli ATTUALI delle parti (quelli al loro posto, non quelli gia' nella storia)
    before = {r['region_id']: r['path'] for r in lib.db.execute(
        "SELECT region_id, path FROM cut WHERE region_id IN (SELECT id FROM region WHERE asset_id = ?) AND path NOT LIKE '%/studio-data/replaced/%' AND path NOT LIKE '%/studio-data/trash/%' ORDER BY id",
        (a['id'],)) if os.path.exists(r['path'])}
    if not before and not lib.db.execute('SELECT 1 FROM cut WHERE region_id IN (SELECT id FROM region WHERE asset_id = ?) LIMIT 1', (a['id'],)).fetchone():
        return                                            # mai tagliata: niente da seguire (gia' tagliata, anche se ora tutto e' nella storia: si segue)
    written = core.export(rel, replace=True, log=lambda m: None, only=only)
    on_export(rel, written, superseded=before)


def _supersede(lib, path, why):
    # un file di taglio non piu' attuale: in replaced/, il catalogo segue il file (la storia non si tocca piu')
    if not os.path.exists(path) or '/studio-data/replaced/' in path or '/studio-data/trash/' in path:
        return
    stamp = time.strftime('%Y%m%d-%H%M%S')
    dst = core.sc.unique(os.path.join(core.DATA, 'replaced', stamp, core.relpath(path) if path.startswith(core.ROOT) else os.path.basename(path)))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.rename(path, dst)
    a = lib.db.execute('SELECT id, uuid FROM asset WHERE path = ?', (path,)).fetchone()
    if a:
        lib.db.execute('UPDATE asset SET path = ? WHERE id = ?', (dst, a['id']))
        lib.db.execute("DELETE FROM item_asset WHERE asset_id = ? AND role = 'cutout'", (a['id'],))
    lib.db.execute('UPDATE cut SET path = ? WHERE path = ?', (dst, path))
    lib.db.commit()
    lib.log('superseded', 'asset', a['uuid'] if a else None, old_path=path, kept_at=dst, why=why)


def series_list(lib):
    return [dict(r) for r in lib.db.execute(
        'SELECT s.uuid, s.name, s.notes, COUNT(i.id) AS items FROM series s LEFT JOIN item i ON i.series_id = s.id AND i.trashed_at IS NULL '
        'GROUP BY s.id ORDER BY s.name COLLATE NOCASE')] + [{'uuid': None, 'name': None, 'items': lib.db.execute(
        'SELECT COUNT(*) FROM item WHERE series_id IS NULL AND trashed_at IS NULL').fetchone()[0]}]


# ---------------------------------------------------------------- dove sta un file nella libreria
def where(lib, rel):
    # per l'editor: questo file e' un originale (con i suoi tagli) o un taglio (con la sua zona e l'originale)
    p = os.path.realpath(core.abspath(rel))
    a = lib.db.execute('SELECT * FROM asset WHERE path = ?', (p,)).fetchone()
    if not a:
        return {'known': False}
    row = lib.db.execute('SELECT i.uuid, i.title, ia.role FROM item_asset ia JOIN item i ON i.id = ia.item_id WHERE ia.asset_id = ? LIMIT 1', (a['id'],)).fetchone()
    out = {'known': True, 'role': row['role'] if row else None, 'item': row['uuid'] if row else None, 'title': row['title'] if row else None}
    if row and row['role'] == 'cutout':
        c = lib.db.execute("SELECT r.label, r.kind, r.position, r.color, json_extract(r.source, '$.studio_rel') AS srel, json_extract(r.source, '$.studio_id') AS sid "
                           'FROM cut x JOIN region r ON r.id = x.region_id WHERE x.path = ? ORDER BY x.id DESC LIMIT 1', (p,)).fetchone()
        src = lib.db.execute('SELECT * FROM asset WHERE id = ?', (a['derived_from'],)).fetchone() if a['derived_from'] else None
        out.update(part=(c['label'] or f'{c["kind"]} {c["position"] + 1}') if c else None, color=c['color'] if c else None,
                   part_id=c['sid'] if c else None, original=rel_of(lib, src) if src and os.path.exists(lib.asset_path(src)) else None,
                   original_missing=bool(src) and not os.path.exists(lib.asset_path(src)))
    else:
        cuts = lib.db.execute("SELECT a.original_name AS name, a.path FROM asset a JOIN item_asset ia ON ia.asset_id = a.id "
                              "WHERE ia.role = 'cutout' AND ia.item_id = (SELECT item_id FROM item_asset WHERE asset_id = ? LIMIT 1) ORDER BY a.original_name", (a['id'],)).fetchall()
        out['cuts'] = [{'name': c['name'], 'rel': core.relpath(c['path']) if c['path'].startswith(core.ROOT + os.sep) else None} for c in cuts]
    return out


# ---------------------------------------------------------------- uscite: il diario LaTeX per nvim
_journal_timer = [None]


def journal_dir(lib):
    r = lib.db.execute("SELECT value FROM setting WHERE key = 'journal_dir'").fetchone()
    return json.loads(r[0]) if r else None


def set_journal_dir(lib, d):
    with lib.db:
        lib.db.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('journal_dir', ?)", (json.dumps(d),))


def write_journal(lib):
    from . import journal
    d = journal_dir(lib)
    return journal.write(lib, os.path.expanduser(d)) if d else None


def schedule_journal(delay=3):
    # una rappresentazione: segue ogni testo cambiato, poco dopo
    lib = library(create=False)
    if not lib or not journal_dir(lib):
        return
    if _journal_timer[0]:
        _journal_timer[0].cancel()
    _journal_timer[0] = threading.Timer(delay, lambda: _safe(write_journal, library(create=False)))
    _journal_timer[0].daemon = True
    _journal_timer[0].start()


def doc_text(rel):
    # il testo gia' letto di un file intero con il lettore di adesso (con le correzioni), o None
    lib = library(create=False)
    if not lib:
        return None
    p = os.path.realpath(core.abspath(rel))
    a = lib.db.execute('SELECT * FROM asset WHERE path = ?', (p,)).fetchone()
    if not a:
        return None
    e_, m_ = reader_of()
    e = lib.db.execute('SELECT region_id FROM cut WHERE path = ? ORDER BY id DESC LIMIT 1', (p,)).fetchone()
    rid = e['region_id'] if e else None
    t = lib.db.execute('SELECT plain FROM current_text WHERE ' + ('region_id = ?' if rid else 'region_id IS NULL AND asset_id = ?') +
                       ' AND engine = ? AND model = ? ORDER BY created_at DESC LIMIT 1', (rid or a['id'], e_, m_)).fetchone()
    return t['plain'] if t else None


# ---------------------------------------------------------------- controllo di coerenza
# Tutto cio' che deriva dalla libreria corrisponde alla libreria? Ritorna l'elenco dei problemi (vuoto: tutto a posto).
# deep: rifa' anche ogni taglio dalla sua parte e lo confronta pixel per pixel (lento).

def check(lib, deep=False):
    import numpy as np
    from PIL import Image
    problems = []
    add = lambda kind, what, detail='': problems.append({'kind': kind, 'what': what, 'detail': detail})
    # 1) i file sono dove dice il catalogo, e sono quelli (tagli: checksum; fonti: esistono e stessa misura)
    for a in lib.db.execute('SELECT a.*, (SELECT role FROM item_asset WHERE asset_id = a.id LIMIT 1) AS role FROM asset a').fetchall():
        p = lib.asset_path(a)
        if a['path'].find('/replaced/') >= 0 or a['path'].find('/studio-data/trash/') >= 0:
            continue                                         # storia: file tenuti da parte
        if not os.path.exists(p):
            add('missing file', a['original_name'], p); continue
        if os.path.getsize(p) != a['size'] or (a['role'] == 'cutout' and sha256(p) != a['sha256']):
            add('file changed outside the library', a['original_name'], p)
    # 2) ogni parte viva gia' tagliata ha il suo taglio attuale, legato, con il testo della parte
    for r in lib.db.execute("SELECT r.*, i.title FROM region r JOIN item i ON i.id = r.item_id WHERE r.removed_at IS NULL AND r.parent_id IS NULL "
                            "AND r.kind = 'sheet' AND i.trashed_at IS NULL AND EXISTS (SELECT 1 FROM cut WHERE region_id = r.id)").fetchall():
        c = lib.db.execute("SELECT path FROM cut WHERE region_id = ? AND path NOT LIKE '%/studio-data/replaced/%' AND path NOT LIKE '%/studio-data/trash/%' ORDER BY id DESC LIMIT 1", (r['id'],)).fetchone()
        name = f'{r["title"]} › {r["label"] or "part " + str(r["position"] + 1)}'
        if not r['export_on']:
            if c and os.path.exists(c['path']) and '/replaced/' not in c['path'] and '/studio-data/trash/' not in c['path']:
                add('cut of an excluded part still in place', name, c['path'])
            continue
        if not c or not os.path.exists(c['path']):
            add('cut missing', name); continue
        a = lib.db.execute('SELECT id FROM asset WHERE path = ?', (c['path'],)).fetchone()
        if not a or not lib.db.execute("SELECT 1 FROM item_asset WHERE asset_id = ? AND role = 'cutout'", (a['id'],)).fetchone():
            add('cut not linked to its source', name, c['path'])
        want = '\n\n'.join(t['plain'] for t in region_texts(lib, r['id']) if t['plain'])
        if want and core.tool('exiftool'):
            got = subprocess.run([core.tool('exiftool'), '-b', '-XMP-dc:Description', c['path']], capture_output=True, text=True).stdout   # -b: il valore esatto (a capo compresi)
            if got.replace('\r', '') != want.replace('\r', ''):
                add('cut text differs from its part', name, c['path'])
        if deep:
            src = json.loads(r['source'] or '{}')
            st = core.load_state(src.get('studio_rel'), create=False) if src.get('studio_rel') else None
            sh = next((x for x in (st or {}).get('sheets', []) if x['id'] == src.get('studio_id')), None)
            res = core.cut_sheet(src['studio_rel'], sh) if sh else None
            if res is not None and c['path'].lower().endswith('.png'):
                img = np.asarray(Image.open(c['path']))
                if img.shape != res[0].shape or not np.array_equal(img, res[0]):
                    if not (img.dtype == np.uint16 or res[0].dtype == np.uint16):
                        add('cut pixels differ from its part', name, c['path'])
    # 3) niente vive piu' fuori dalla libreria
    for d in ('state', 'text'):
        dd = os.path.join(core.DATA, d)
        if os.path.isdir(dd) and os.listdir(dd):
            add('data outside the library', f'studio-data/{d}', dd)
    # 4) il diario (se c'e') dice quello che dice la libreria
    jd = journal_dir(lib)
    if jd and os.path.isdir(os.path.expanduser(jd)):
        from . import journal
        for it in lib.db.execute("SELECT id, title, date FROM item WHERE trashed_at IS NULL").fetchall():
            texts = [t['plain'] for t in lib.db.execute("SELECT t.plain FROM current_text t JOIN region r ON r.id = t.region_id WHERE r.item_id = ? "
                                                        "AND r.removed_at IS NULL AND t.plain != ''", (it['id'],))]
            if not texts:
                continue
            f = os.path.join(os.path.expanduser(jd), f'{it["date"] or "undated"} {journal.safe_name(it["title"] or "")}.tex')
            body = open(f, encoding='utf-8').read() if os.path.exists(f) else ''
            first = journal.inline(texts[-1].splitlines()[0]) if texts[-1].strip() else ''
            if not body or (first and first not in body):
                add('journal out of date', it['title'], f)
    return problems


# ---------------------------------------------------------------- i file dentro la libreria
# Il passaggio: originals/, cut/ e failed/ entrano nel pacchetto della libreria (<radice>/Library.DocuLib, un file
# solo nel Finder); PNG e TIFF diventano JPEG XL senza perdita, ognuno controllato pixel per pixel prima di
# lasciare il file di prima. Fuori resta solo l'inbox. Il file di prima non si cancella: va in
# studio-data/replaced/switch-<ora>/, finche' non si decide di toglierlo. Prima il piano (niente cambia), poi il passaggio.

SWITCH_TOPS = ('originals', 'cut', 'failed')


def switch_plan(lib):
    pkg = os.path.join(core.ROOT, core.sc.PACKAGE)
    out = {'packed': core.sc.PACKED, 'package': pkg, 'tools': core.sc.jxl_tools(), 'exiftool': bool(core.tool('exiftool')),
           'tops': {}, 'files': 0, 'bytes': 0, 'convert': 0, 'convert_bytes': 0, 'keep': 0, 'keep_bytes': 0, 'links': 0}
    if core.sc.PACKED:
        return out
    for top in SWITCH_TOPS:
        d = os.path.join(core.ROOT, top)
        t = {'files': 0, 'bytes': 0}
        for base, dirs, fs in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith('.')]
            for f in fs:
                p = os.path.join(base, f)
                if f.startswith('.'):
                    continue
                if os.path.islink(p):
                    out['links'] += 1; continue
                n = os.path.getsize(p)
                t['files'] += 1; t['bytes'] += n
                if os.path.splitext(f)[1].lower() in ('.png', '.tif', '.tiff'):
                    out['convert'] += 1; out['convert_bytes'] += n
                else:
                    out['keep'] += 1; out['keep_bytes'] += n
        out['tops'][top] = t
        out['files'] += t['files']; out['bytes'] += t['bytes']
    # meta' circa per i PNG delle scansioni (misurato), un TIFF senza compressione ancora meno; il resto uguale
    out['estimate_bytes'] = int(out['convert_bytes'] * 0.5) + out['keep_bytes']
    return out


def switch_storage(lib, progress=None, log=print):
    if core.sc.PACKED:
        raise RuntimeError('the files are already inside the library')
    if not core.sc.jxl_tools():
        raise RuntimeError('JPEG XL tools missing (brew install jpeg-xl)')
    plan = switch_plan(lib)
    root, pkg = core.ROOT, os.path.realpath(os.path.join(core.ROOT, core.sc.PACKAGE))
    stamp = time.strftime('%Y%m%d-%H%M%S')
    aside = os.path.join(core.DATA, 'replaced', f'switch-{stamp}')
    lib.snapshot('before the files move into the library')
    lib.log('switch', 'library', lib.meta('uuid'), 'start', files=plan['files'], bytes=plan['bytes'])
    moved, links, done_map = [], [], {}
    stage = os.path.join(pkg, '.moving')                 # dentro il pacchetto, finche' non e' tutto al suo posto
    with core.agent_lock(), files_lock:
        # 1. ogni file nel pacchetto (stesso disco: si sposta il nome, niente copia); il catalogo segue
        for top in SWITCH_TOPS:
            d = os.path.join(root, top)
            for base, dirs, fs in os.walk(d):
                dirs[:] = [x for x in dirs if not x.startswith('.')]
                for f in sorted(fs):
                    p = os.path.join(base, f)
                    rel = os.path.relpath(p, root)
                    if f.startswith('.'):
                        continue
                    if os.path.islink(p):
                        links.append((rel, os.path.realpath(p))); continue
                    dst = os.path.join(stage, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.rename(p, dst)
                    moved.append((rel, os.path.realpath(p), dst))
        final = lambda rel: os.path.join(pkg, rel)
        for rel, old, dst in moved:
            lib.db.execute('UPDATE asset SET path = ? WHERE path = ?', (final(rel), old))
            lib.db.execute('UPDATE cut SET path = ? WHERE path = ?', (final(rel), old))
        for t in lib.db.execute('SELECT id, files FROM trash').fetchall():
            fl = json.loads(t['files'])
            for f in fl:
                for top in SWITCH_TOPS:
                    if f['from'].startswith(os.path.join(root, top) + os.sep):
                        f['from'] = os.path.join(pkg, os.path.relpath(f['from'], root))
            lib.db.execute('UPDATE trash SET files = ? WHERE id = ?', (json.dumps(fl), t['id']))
        lib.db.commit()
        for top in SWITCH_TOPS:
            src = os.path.join(stage, top)
            os.makedirs(src, exist_ok=True)
            os.rename(src, os.path.join(pkg, top))
        os.rmdir(stage) if os.path.isdir(stage) and not os.listdir(stage) else None
        # 2. le cartelle di prima, vuote, se ne vanno (un .DS_Store non le tiene in vita)
        for top in SWITCH_TOPS:
            d = os.path.join(root, top)
            for base, dirs, fs in sorted(os.walk(d, topdown=False), key=lambda x: -len(x[0])):
                for f in fs:
                    if f == '.DS_Store' or os.path.islink(os.path.join(base, f)):
                        os.remove(os.path.join(base, f))
                try:
                    os.rmdir(base)
                except OSError:
                    pass
        core.set_root(root)                              # ora i nomi relativi portano dentro il pacchetto
        core.save_settings({'export_format': 'jxl'})     # i tagli nuovi come gli altri: JPEG XL senza perdita
        # 3. failed/: i collegamenti puntano ai file nel pacchetto
        for rel, target in links:
            t = target
            for top in SWITCH_TOPS:
                if target.startswith(os.path.join(root, top) + os.sep):
                    t = os.path.join(pkg, os.path.relpath(target, root))
            lp = os.path.join(pkg, rel)
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            if not os.path.lexists(lp):
                os.symlink(t, lp)
    # 4. PNG e TIFF in JPEG XL senza perdita, uno alla volta (si puo' interrompere: cio' che e' fatto resta fatto)
    todo = [(rel, final(rel)) for rel, _, _ in moved if os.path.splitext(rel)[1].lower() in ('.png', '.tif', '.tiff')]
    saved = conv = 0
    for i, (rel, p) in enumerate(todo):
        if progress:
            progress(i / max(1, len(todo)), f'{i + 1}/{len(todo)} {os.path.basename(p)}')
        r = pack_file(lib, p, aside, done_map)
        if r:
            conv += 1; saved += r
        else:
            log(f'kept as it is: {rel}')
    _rewrite_done(done_map)
    lib.log('switch', 'library', lib.meta('uuid'), files=len(moved), converted=conv, saved_bytes=saved, kept_aside=aside)
    log(f'{len(moved)} files now inside {os.path.basename(pkg)}; {conv} turned into lossless JPEG XL, '
        f'{saved >> 20} MB less. The files as they were are kept in {aside} until you remove them.')
    schedule_journal()
    return {'files': len(moved), 'converted': conv, 'saved_bytes': saved, 'aside': aside}


def pack_file(lib, p, aside, done_map=None):
    # un file del pacchetto in JPEG XL: il catalogo, le registrazioni e done.tsv seguono. Ritorna i byte risparmiati
    from .db import sha256 as _sha
    with files_lock:
        j = core.sc.pack(p)
        if not j:
            return 0
        old_sha, old_size = _sha(p), os.path.getsize(p)
        dst = core.sc.unique(os.path.join(aside, core.relpath(p)))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(p, dst)                                # il file di prima, da parte (non cancellato)
        new_sha, new_size = _sha(j), os.path.getsize(j)
        a = lib.db.execute('SELECT id, uuid FROM asset WHERE path = ?', (os.path.realpath(p),)).fetchone()
        if a:
            lib.db.execute("UPDATE asset SET path = ?, sha256 = ?, size = ?, mime = 'image/jxl', file_mtime = ?, original_name = ? WHERE id = ?",
                           (os.path.realpath(j), new_sha, new_size, now(), os.path.basename(j), a['id']))
            lib.log('convert', 'asset', a['uuid'], old_sha256=old_sha, new_sha256=new_sha, to='lossless JPEG XL, same pixels', kept=dst)
        lib.db.execute("UPDATE cut SET path = ?, sha256 = ?, format = 'jxl' WHERE path = ?", (os.path.realpath(j), new_sha, os.path.realpath(p)))
        lib.db.execute('UPDATE capture SET sha256 = ? WHERE sha256 = ?', (new_sha, old_sha))
        lib.db.commit()
        rel = core.relpath(j)
        if rel.startswith('originals/') and done_map is not None:
            done_map[core.relpath(p)[len('originals/'):]] = rel[len('originals/'):]
        return old_size - new_size


def _rewrite_done(done_map):
    # done.tsv segue i file (nome nuovo, misura nuova; l'ora del file resta quella di prima)
    if not done_map or not os.path.exists(core.sc.DONE):
        return
    lines = []
    for line in open(core.sc.DONE):
        p = line.rstrip('\n').split('\t')
        if len(p) >= 4 and p[0] in done_map:
            q = os.path.join(core.sc.ORIG, done_map[p[0]])
            if os.path.exists(q):
                st = os.stat(q)
                p = [done_map[p[0]], str(st.st_size), str(int(st.st_mtime))] + p[3:]
        lines.append('\t'.join(p) + '\n')
    tmp = core.sc.DONE + '.part'
    open(tmp, 'w').writelines(lines)
    os.replace(tmp, core.sc.DONE)

