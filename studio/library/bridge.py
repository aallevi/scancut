# il ponte fra la libreria e lo studio di oggi: import della cartella delle scansioni (originali
# referenziati dove sono, fogli e testo dallo stato dello studio) e "Modifica in…" (Affinity o altro):
# una copia di lavoro senza perdita si apre nell'app; ogni volta che la si salva, la libreria la
# prende come nuova versione legata all'originale. L'originale non si tocca mai.

import os, json, time, shutil, threading, subprocess, glob

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
    p = core.settings().get('library') or os.path.join(core.ROOT, 'Library.scanlib')
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
    return os.path.relpath(p, core.ROOT) if p.startswith(core.ROOT + os.sep) else None


# ---------------------------------------------------------------- import della cartella di oggi

def import_root(lib, progress=None, log=print):
    files = []
    for base, dirs, fs in os.walk(os.path.join(core.ROOT, 'originals')):
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
        sync_rel(rel)                    # fogli, ritocchi, testo: aggiornati, non solo aggiunti
        import_text(lib, aid, rel)
        import_cutouts(lib, rel)
        if progress:
            progress(i + 1, len(files), os.path.basename(path))
    for (u, name) in lib.db.execute('SELECT uuid, name FROM series s WHERE NOT EXISTS (SELECT 1 FROM item WHERE series_id = s.id)').fetchall():
        lib.db.execute('DELETE FROM series WHERE uuid = ?', (u,)); lib.log('remove', 'series', u, name=name, why='no objects')
    lib.db.commit()
    log(f'{len(files)} originals, {added} new item(s)')
    return {'files': len(files), 'new_items': added}


def import_state(lib, iid, aid, rel):
    # i fogli dello studio diventano zone (con i ritocchi, la rotazione, il testo letto)
    st = core.load_state(rel, create=False)
    if not st:
        return
    have = {r[0] for r in lib.db.execute("SELECT json_extract(source, '$.studio_id') FROM region WHERE item_id = ? AND asset_id = ?", (iid, aid))}
    for i, sh in enumerate(st['sheets']):
        if sh['id'] in have:
            continue
        src = {'studio_id': sh['id'], 'studio_rel': rel, 'engine': sh.get('engine'), 'src': sh.get('src'),
               'poly0': sh.get('poly0'), 'holes': sh.get('holes'), 'base': sh.get('base')}
        rid = lib.add_region(iid, aid, 'sheet', {'poly': sh['poly']}, label=sh.get('label') or None, source=src,
                             color=COLORS[i % len(COLORS)])
        lib.db.execute('UPDATE region SET ops = ?, rotation = ?, export_on = ? WHERE id = ?',
                       (json.dumps(sh.get('ops') or []), int(sh.get('rot') or 0), 0 if sh.get('on') is False else 1, rid))
        lib.db.commit()
        if sh.get('ocr'):
            e_, m_ = reader_of()
            lib.add_reading(aid, e_, sh['ocr'], region_id=rid, model=m_)


def import_text(lib, aid, rel):
    # il testo dei documenti interi gia' letto (studio-data/text)
    key = core.file_key(rel)
    for p in glob.glob(os.path.join(core.DATA, 'text', key + '-*.md')):
        if lib.db.execute("SELECT 1 FROM reading WHERE asset_id = ? AND region_id IS NULL AND json_extract(params, '$.cache') = ?",
                          (aid, os.path.basename(p))).fetchone():
            continue
        lib.add_reading(aid, 'studio', open(p, encoding='utf-8').read(), params={'cache': os.path.basename(p)})


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


def item_list(lib, q=None, limit=500, offset=0, series=None):
    if q:
        uu = [r['uuid'] for r in lib.search(q, limit=limit)]
        if not uu:
            return []
        rows = lib.db.execute(f"SELECT * FROM item WHERE uuid IN ({','.join('?' * len(uu))})", uu).fetchall()
        rows.sort(key=lambda r: uu.index(r['uuid']))
    else:
        rows = lib.db.execute('SELECT * FROM item WHERE trashed_at IS NULL AND parent_id IS NULL'
                              + (' AND series_id IS NULL' if series == 'none' else ' AND series_id = (SELECT id FROM series WHERE uuid = ?)' if series else '')
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
    assets = [dict(r) | {'rel': rel_of(lib, r)} for r in lib.db.execute(
        'SELECT a.*, ia.role FROM asset a JOIN item_asset ia ON ia.asset_id = a.id WHERE ia.item_id = ? ORDER BY ia.position', (it['id'],))]
    regions = [dict(r) for r in lib.db.execute('SELECT * FROM region WHERE item_id = ? ORDER BY position', (it['id'],))]
    for g in regions:
        t = lib.db.execute('SELECT plain, engine, model, corrected_version FROM current_text WHERE region_id = ? ORDER BY created_at DESC LIMIT 1', (g['id'],)).fetchone()
        g['text'] = dict(t) if t else None
        g['geometry'] = json.loads(g['geometry'])
        e = lib.db.execute('SELECT path, created_at FROM cut WHERE region_id = ? ORDER BY created_at DESC, id DESC LIMIT 1', (g['id'],)).fetchone()
        g['cutout'] = None
        if e and os.path.exists(e['path']):
            p = os.path.realpath(e['path'])
            g['cutout'] = {'rel': os.path.relpath(p, core.ROOT) if p.startswith(core.ROOT + os.sep) else None,
                           'name': os.path.basename(p), 'at': e['created_at']}
    events = [dict(r) for r in lib.db.execute(
        "SELECT at, type, outcome, detail FROM event WHERE entity_uuid IN (SELECT uuid FROM asset WHERE id IN (SELECT asset_id FROM item_asset WHERE item_id = ?)) OR entity_uuid = ? ORDER BY at DESC LIMIT 30",
        (it['id'], it['uuid']))]
    parts = [dict(r) for r in lib.db.execute('SELECT uuid, title FROM item WHERE parent_id = ? ORDER BY id', (it['id'],))]
    sr = lib.db.execute('SELECT uuid, name FROM series WHERE id = ?', (it['series_id'],)).fetchone() if it['series_id'] else None
    return {'item': dict(it, batch=sr['name'] if sr else None, series_uuid=sr['uuid'] if sr else None), 'assets': assets, 'regions': regions,
            'events': events, 'parts': parts}


def info(lib):
    q = lambda s: lib.db.execute(s).fetchone()[0]
    return {'path': lib.path, 'name': lib.meta('name'), 'uuid': lib.meta('uuid'),
            'items': q('SELECT COUNT(*) FROM item WHERE trashed_at IS NULL'), 'files': q('SELECT COUNT(*) FROM asset'),
            'texts': q('SELECT COUNT(*) FROM reading'), 'cutouts': q("SELECT COUNT(*) FROM item_asset WHERE role = 'cutout'"),
            'edits': q("SELECT COUNT(*) FROM item_asset WHERE role = 'edit'")}


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
    # lo stato dello studio di una scansione -> le zone e il testo nella libreria
    if not rel.startswith('originals/'):
        return
    lib = library(create=False)
    if not lib:
        return
    iid, aid = item_for(lib, rel)
    st = core.load_state(rel, create=False)
    if not st:
        return
    have = {r['studio_id']: r for r in lib.db.execute(
        "SELECT id, json_extract(source, '$.studio_id') AS studio_id, geometry, ops, rotation, export_on, label FROM region WHERE item_id = ? AND asset_id = ?", (iid, aid))}
    seen, recut_needed = set(), False
    has_cut = bool(lib.db.execute('SELECT 1 FROM cut WHERE item_id = ? LIMIT 1', (iid,)).fetchone())
    for i, sh in enumerate(st['sheets']):
        seen.add(sh['id'])
        geom, ops = json.dumps({'poly': sh['poly']}), json.dumps(sh.get('ops') or [])
        color = sh.get('color') or COLORS[i % len(COLORS)]
        rot, on, label = int(sh.get('rot') or 0), 0 if sh.get('on') is False else 1, sh.get('label') or None
        r = have.get(sh['id'])
        if r is None:
            src = {'studio_id': sh['id'], 'studio_rel': rel, 'engine': sh.get('engine'), 'src': sh.get('src'),
                   'poly0': sh.get('poly0'), 'holes': sh.get('holes'), 'base': sh.get('base')}
            rid = lib.add_region(iid, aid, 'sheet', {'poly': sh['poly']}, label=label, source=src, color=color)
            recut_needed = recut_needed or has_cut
        else:
            rid = r['id']
            if r['rotation'] != rot:
                # girata nello studio: i ritagli gia' esportati girano anche loro (senza perdita)
                lib.db.execute('UPDATE region SET rotation = ? WHERE id = ?', (rot, rid)); lib.db.commit()
                rotate_region_cutouts(lib, rid, (rot - int(r['rotation'] or 0)) % 360)
            src_now = lib.db.execute("SELECT json_extract(source, '$.holes'), position FROM region WHERE id = ?", (rid,)).fetchone()
            if (r['geometry'], r['ops'], r['export_on'], r['label']) != (geom, ops, on, label) or src_now[1] != i \
                    or json.loads(src_now[0] or 'null') != sh.get('holes'):
                recut_needed = recut_needed or has_cut       # cambia il taglio: contorno, ritocchi, buchi, nome, ordine, inclusione
                lib.db.execute("UPDATE region SET source = json_set(COALESCE(source, '{}'), '$.holes', json(?)) WHERE id = ?", (json.dumps(sh.get('holes')), rid))
            if (r['geometry'], r['ops'], r['rotation'], r['export_on'], r['label']) != (geom, ops, rot, on, label):
                lib.db.execute('UPDATE region SET geometry = ?, ops = ?, rotation = ?, export_on = ?, label = ?, modified_at = ? WHERE id = ?',
                               (geom, ops, rot, on, label, now(), rid))
                lib.db.commit()
                lib.log('edit', 'region', None, studio_id=sh['id'])
        lib.db.execute('UPDATE region SET ops = ?, rotation = ?, export_on = ?, position = ?, color = ? WHERE id = ?', (ops, rot, on, i, color, rid))
        lib.db.commit()
        # testo: nuovo -> lettura; cambiato a mano -> correzione (la lettura di prima resta)
        sync_text(lib, aid, rid, sh.get('ocr'))
        # aree secondarie del foglio: zone figlie (kind "text"), ognuna con il suo testo
        sub = {r['sid']: r['id'] for r in lib.db.execute(
            "SELECT id, json_extract(source, '$.studio_area') AS sid FROM region WHERE parent_id = ?", (rid,))}
        for k, a in enumerate(sh.get('areas') or []):
            key = f'{sh["id"]}/{a["id"]}'
            if key in sub:
                cid = sub.pop(key)
                lib.db.execute('UPDATE region SET geometry = ?, position = ? WHERE id = ?', (json.dumps({'box': a['box']}), k, cid))
                lib.db.commit()
            else:
                cid = lib.add_region(iid, aid, 'text', {'box': a['box']}, label=None, parent_id=rid,
                                     source={'studio_area': key, 'studio_rel': rel}, color=COLORS[i % len(COLORS)])
            sync_text(lib, aid, cid, a.get('text'), reader=a.get('reader'))
        for key, cid in list(sub.items()):           # area tolta nello studio: resta nella storia, segnata
            lib.db.execute("UPDATE region SET export_on = 0, label = 'removed in studio' WHERE id = ?", (cid,))
            lib.db.commit()
    for rid in [r[0] for r in lib.db.execute('SELECT DISTINCT region_id FROM cut WHERE item_id = ? AND region_id IS NOT NULL', (iid,))]:
        refresh_cutout_text(lib, rid)
    if recut_needed:
        schedule_recut(rel)
    schedule_journal()
    # fogli tolti nello studio: le zone non si cancellano, si segnano (la storia resta)
    for sid, r in have.items():
        if sid not in seen and r['export_on']:
            recut_needed = recut_needed or has_cut
        if sid not in seen:
            lib.db.execute("UPDATE region SET export_on = 0, label = COALESCE(label, '') || ' (removed in studio)', modified_at = ? WHERE id = ? AND label NOT LIKE '%(removed in studio)%'",
                           (now(), r['id']))
            lib.db.commit()
    lib.touched(iid)


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
    # i ritagli scritti diventano file dell'oggetto: ruolo "cutout", legati all'originale e alla zona
    if not rel.startswith('originals/'):
        return
    lib = library(create=False)
    if not lib:
        return
    sync_rel(rel)
    iid, aid = item_for(lib, rel)
    for w in written:
        if w.get('status') not in ('written', 'identical') or not os.path.exists(w['path']):
            continue
        cid, _ = lib.add_asset(w['path'], managed=False, derived_from=aid, made_with='Scan Studio')
        lib.db.execute("INSERT OR IGNORE INTO item_asset (item_id, asset_id, role, position) VALUES (?, ?, 'cutout', 100 + ?)", (iid, cid, cid))
        reg = lib.db.execute("SELECT id FROM region WHERE item_id = ? AND json_extract(source, '$.studio_id') = ?", (iid, w.get('id'))).fetchone()
        if reg:
            link_cutout_texts(lib, reg[0], cid)
        a = lib.db.execute('SELECT sha256 FROM asset WHERE id = ?', (cid,)).fetchone()
        if not lib.db.execute('SELECT 1 FROM cut WHERE path = ? AND sha256 = ?', (w['path'], a['sha256'])).fetchone():
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
    d = os.path.join(core.ROOT, 'cut', core.batch_of(rel))
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


def _safe(fn, *a):
    try:
        fn(*a)
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
        'WITH RECURSIVE sub(id) AS (SELECT id FROM region WHERE parent_id = ? UNION ALL SELECT r.id FROM region r JOIN sub ON r.parent_id = sub.id) SELECT id FROM sub', (region_id,))]
    return lib.db.execute(f"SELECT * FROM current_text WHERE region_id IN ({','.join('?' * len(ids))}) ORDER BY created_at", ids).fetchall()


def link_cutout_texts(lib, region_id, asset_id):
    for t in region_texts(lib, region_id):
        lib.db.execute('INSERT OR IGNORE INTO text_link (reading_id, asset_id) VALUES (?, ?)', (t['reading_id'], asset_id))
    lib.db.commit()


def refresh_cutout_text(lib, region_id):
    from .db import sha256
    texts = region_texts(lib, region_id)
    reg = lib.db.execute('SELECT r.uuid, i.uuid AS item FROM region r JOIN item i ON i.id = r.item_id WHERE r.id = ?', (region_id,)).fetchone()
    if not texts or not reg or not core.tool('exiftool'):
        return 0
    plain = '\n\n'.join(t['plain'] for t in texts if t['plain'])
    refs = [f'scanstudio://text/{t["uuid"]}?v={t["corrected_version"] or 0}' for t in texts]
    n = 0
    for e in lib.db.execute('SELECT id, path, sha256 FROM cut WHERE region_id = ?', (region_id,)).fetchall():
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
        txt = os.path.join(lib.path, 'cache', f'.text-{region_id}.txt')
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
    latest = ("SELECT t.* FROM current_text t WHERE t.region_id IS NULL OR t.created_at = "
              "(SELECT MAX(created_at) FROM reading WHERE region_id = t.region_id)")
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
                    'whole': reg is None, 'cutouts': cuts})
    return out


def cutout_list(lib, limit=1000, series=None):
    out = []
    flt = " AND i.series_id IS NULL" if series == 'none' else " AND i.series_id = (SELECT id FROM series WHERE uuid = ?)" if series else ""
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
        out.append({'uuid': a['uuid'], 'rel': rel_of(lib, a), 'name': a['original_name'], 'item': a['item'], 'title': a['title'], 'added': a['imported_at'],
                    'width': a['width'], 'height': a['height'], 'dpi': a['dpi'], 'sha256': a['sha256'],
                    'region': {'uuid': e['uuid'], 'label': e['label'] or f'{e["kind"]} {e["position"] + 1}', 'color': e['color']} if e else None,
                    'texts': texts})
    return out


# ---------------------------------------------------------------- testo dei ritagli, a lotti
# Il testo si legge di solito sui ritagli gia' fatti: ogni ritaglio letto intero, il testo legato a lui
# e alla sua zona, e scritto anche nello stato dello studio (il pannello Testo lo mostra).

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
        e = lib.db.execute('SELECT region_id FROM cut WHERE path = ? ORDER BY id DESC LIMIT 1', (lib.asset_path(a),)).fetchone()
        rid = e['region_id'] if e else None
        e_, m_ = reader_of()
        r = lib.add_reading(a['id'], e_, text, region_id=rid, model=m_, params={'read_on': 'cutout'})
        lib.db.execute('INSERT OR IGNORE INTO text_link (reading_id, asset_id) VALUES (?, ?)', (r, a['id']))
        lib.db.commit()
        if rid:
            # anche nello studio: il foglio di quella zona ha questo testo
            src = lib.db.execute("SELECT json_extract(source, '$.studio_rel'), json_extract(source, '$.studio_id') FROM region WHERE id = ?", (rid,)).fetchone()
            if src and src[0]:
                st = core.load_state(src[0], create=False)
                for sh in (st or {}).get('sheets', []):
                    if sh['id'] == src[1]:
                        sh['ocr'] = text
                        core.save_state(st)
                        break
            refresh_cutout_text(lib, rid)
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
    for t in lib.db.execute('SELECT t.* FROM current_text t JOIN text_link l ON l.reading_id = t.reading_id WHERE l.asset_id = ? ORDER BY t.created_at DESC', (a['id'],)):
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
        core.rotate_files([core.relpath(p)], delta, log=lambda m: None)
        _refresh_asset_file(lib, p, 'rotate', degrees=delta, why='its part was rotated')


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


def schedule_recut(rel, delay=2.5):
    t = _recut_timers.pop(rel, None)
    if t:
        t.cancel()
    t = threading.Timer(delay, lambda: _safe(recut, rel))
    t.daemon = True
    _recut_timers[rel] = t
    t.start()


def recut(rel):
    lib = library(create=False)
    if not lib:
        return
    iid, aid = item_for(lib, rel)
    before = {r['region_id']: r['path'] for r in lib.db.execute(
        'SELECT region_id, path FROM cut WHERE item_id = ? AND region_id IS NOT NULL ORDER BY id', (iid,))}
    if not before:
        return                                            # mai tagliata: niente da seguire
    written = core.export(rel, replace=True, log=lambda m: None)
    on_export(rel, written, superseded=before)


def _supersede(lib, path, why):
    # un file di taglio non piu' attuale: in replaced/, il catalogo segue il file
    if not os.path.exists(path):
        return
    stamp = time.strftime('%Y%m%d-%H%M%S')
    dst = core.sc.unique(os.path.join(core.DATA, 'replaced', stamp, os.path.relpath(path, core.ROOT) if path.startswith(core.ROOT) else os.path.basename(path)))
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
        out['cuts'] = [{'name': c['name'], 'rel': os.path.relpath(c['path'], core.ROOT) if c['path'].startswith(core.ROOT + os.sep) else None} for c in cuts]
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
