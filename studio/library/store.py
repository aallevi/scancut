# lo stato di modifica di un file, come lo vede lo studio (parti, ritocchi, testi, aree), e' fatto di
# righe della libreria: load() lo compone, save() lo scrive. Non c'e' altro posto dove stia: niente file
# JSON, niente cache privata. Ogni cosa che lo studio mostra viene da qui; ogni cosa che cambia passa da qui,
# e da qui partono le conseguenze (tagli rifatti, metadati dei tagli, diario).

import os, json, time, threading

from .. import core
from . import bridge
from .db import now

_lock = threading.RLock()
_cache = {}                       # (percorso, versione) -> stato composto; le tessere della maschera lo chiedono spesso


def _lib():
    return bridge.library(create=True)


def asset_for(lib, rel, create=True):
    # l'asset di un file aperto nello studio (creato se manca: una fonte, o un file qualsiasi della radice)
    p = os.path.realpath(core.abspath(rel))
    a = lib.db.execute('SELECT * FROM asset WHERE path = ?', (p,)).fetchone()
    if a or not create or not os.path.exists(p):
        return a
    if rel.startswith('originals/'):
        bridge.item_for(lib, rel)
    else:
        aid, _ = lib.add_asset(p, managed=False)
        if not lib.db.execute('SELECT 1 FROM item_asset WHERE asset_id = ?', (aid,)).fetchone():
            lib.new_item(os.path.splitext(os.path.basename(p))[0], kind='file', assets=[aid])
    return lib.db.execute('SELECT * FROM asset WHERE path = ?', (p,)).fetchone()


def _item_of_asset(lib, aid):
    # l'oggetto delle parti trovate su questo file. Un taglio ritagliato di nuovo: i pezzi sono un oggetto loro
    # (figlio) che appartiene anche all'oggetto da cui viene il taglio; il loro posto e' quello della parte d'origine
    rows = lib.db.execute('SELECT item_id, role FROM item_asset WHERE asset_id = ? ORDER BY position', (aid,)).fetchall()
    if not rows:
        return None
    own = next((r[0] for r in rows if r[1] != 'cutout'), None)
    if own:
        return own
    parent = rows[0][0]
    a = lib.db.execute('SELECT original_name FROM asset WHERE id = ?', (aid,)).fetchone()
    p = lib.db.execute('SELECT series_id, date FROM item WHERE id = ?', (parent,)).fetchone()
    from .db import new_uuid
    u, t = new_uuid(), now()
    iid = lib.db.execute('INSERT INTO item (uuid, kind, parent_id, title, date, series_id, created_at, modified_at) VALUES (?,?,?,?,?,?,?,?)',
                         (u, 'piece', parent, os.path.splitext(a[0])[0], p['date'], p['series_id'], t, t)).lastrowid
    lib.db.execute("INSERT INTO item_asset (item_id, asset_id, role, position) VALUES (?, ?, 'view', 0)", (iid, aid))
    lib.db.commit()
    lib.log('create', 'item', u, kind='piece', came_from=lib.db.execute('SELECT uuid FROM item WHERE id = ?', (parent,)).fetchone()[0])
    return iid


def _text(lib, rid):
    t = lib.db.execute('SELECT plain, model, engine FROM current_text WHERE region_id = ? ORDER BY created_at DESC LIMIT 1', (rid,)).fetchone()
    return t


# ---------------------------------------------------------------- leggere
def load(rel, create=True):
    lib = _lib()
    with _lock:
        a = asset_for(lib, rel, create=create)
        if not a:
            return None
        es = lib.db.execute('SELECT * FROM editstate WHERE asset_id = ?', (a['id'],)).fetchone()
        ver = es['version'] if es else 0
        key = (a['path'], ver)
        if key in _cache:
            st = json.loads(_cache[key])
            st['rel'] = rel
            return st
        sheets, loose = [], []
        rows = lib.db.execute('SELECT * FROM region WHERE asset_id = ? AND removed_at IS NULL ORDER BY position, id', (a['id'],)).fetchall()
        kids = {}
        for r in rows:
            if r['parent_id']:
                kids.setdefault(r['parent_id'], []).append(r)
        for r in rows:
            if r['parent_id']:
                continue
            src = json.loads(r['source'] or '{}')
            geom = json.loads(r['geometry'])
            if r['kind'] == 'sheet':
                sh = {'id': src.get('studio_id') or f'r{r["id"]}', 'src': src.get('src'), 'engine': src.get('engine'),
                      'poly0': src.get('poly0'), 'poly': geom.get('poly') or [], 'ops': json.loads(r['ops'] or '[]'),
                      'on': bool(r['export_on']), 'label': r['label'] or '', 'holes': src.get('holes') or [],
                      'rot': int(r['rotation'] or 0), 'color': r['color']}
                if src.get('base'):
                    sh['base'] = src['base']
                t = _text(lib, r['id'])
                if t is not None:
                    sh['ocr'] = t['plain']
                areas = []
                for c in kids.get(r['id'], []):
                    cs = json.loads(c['source'] or '{}')
                    ct = _text(lib, c['id'])
                    areas.append({'id': (cs.get('studio_area') or '').split('/')[-1] or f'a{c["id"]}', 'box': json.loads(c['geometry']).get('box'),
                                  'text': ct['plain'] if ct else '', 'reader': ct['model'] if ct else ''})
                if areas:
                    sh['areas'] = areas
                sheets.append(sh)
            elif r['kind'] == 'text':
                # un riquadro letto fuori da ogni parte: resta, con il suo testo
                t = _text(lib, r['id'])
                loose.append({'id': src.get('studio_loose') or f'l{r["id"]}', 'box': geom.get('box'), 'text': t['plain'] if t else '',
                              'reader': t['model'] if t else ''})
        st = {'rel': rel, 'version': ver, 'engine': es['engine'] if es else None, 'params': json.loads(es['params'] or '{}') if es else {},
              'exported': es['cut_at'] if es and es['cut_at'] else False, 'history': json.loads(es['history'] or '[]') if es else [],
              'saved': es['saved_at'] if es else None, 'sheets': sheets, 'loose': loose}
        if len(_cache) > 64:
            _cache.pop(next(iter(_cache)))
        _cache[key] = json.dumps(st)
        return st


def summary(rel):
    # per le gallerie: quante parti incluse, il motore, se e' stato tagliato (senza comporre tutto)
    lib = _lib()
    a = asset_for(lib, rel, create=False)
    if not a:
        return None
    es = lib.db.execute('SELECT engine, cut_at FROM editstate WHERE asset_id = ?', (a['id'],)).fetchone()
    n = lib.db.execute("SELECT COUNT(*) FROM region WHERE asset_id = ? AND parent_id IS NULL AND kind = 'sheet' AND removed_at IS NULL AND export_on = 1",
                       (a['id'],)).fetchone()[0]
    if not es and not n:
        return None
    return {'sheets': n, 'engine': es['engine'] if es else None, 'exported': bool(es and es['cut_at'])}


# ---------------------------------------------------------------- scrivere
def save(st):
    lib = _lib()
    rel = st['rel']
    with _lock:
        a = asset_for(lib, rel, create=True)
        if not a:
            raise FileNotFoundError(rel)
        iid = _item_of_asset(lib, a['id'])
        es = lib.db.execute('SELECT version FROM editstate WHERE asset_id = ?', (a['id'],)).fetchone()
        ver = (es['version'] if es else 0) + 1
        pending = bridge.apply_state(lib, rel, st, iid, a['id'])
        exported = st.get('exported')
        lib.db.execute('INSERT INTO editstate (asset_id, version, engine, params, cut_at, history, saved_at) VALUES (?,?,?,?,?,?,?) '
                       'ON CONFLICT(asset_id) DO UPDATE SET version = excluded.version, engine = excluded.engine, params = excluded.params, '
                       'cut_at = excluded.cut_at, history = excluded.history, saved_at = excluded.saved_at',
                       (a['id'], ver, st.get('engine'), json.dumps(st.get('params') or {}),
                        float(exported) if exported and exported is not True else None,
                        json.dumps(st.get('history') or []), time.time()))
        lib.db.commit()
        _cache.clear()
        out = load(rel)
    for rid in pending:                                  # fuori dal lucchetto dello stato (un taglio rifatto puo' tenere i file)
        bridge.refresh_cutout_text(lib, rid)
    return out


def mark_cut(rel):
    # il taglio e' stato fatto: solo l'ora (e una versione nuova), il resto dello stato non si tocca
    lib = _lib()
    t = time.time()
    with _lock:
        a = asset_for(lib, rel, create=True)
        lib.db.execute('INSERT INTO editstate (asset_id, version, cut_at, saved_at) VALUES (?,1,?,?) '
                       'ON CONFLICT(asset_id) DO UPDATE SET version = version + 1, cut_at = excluded.cut_at, saved_at = excluded.saved_at',
                       (a['id'], t, t))
        lib.db.commit()
        _cache.clear()
    return t


def moved(old_rel, new_rel):
    # il file e' stato spostato (un ritaglio ritagliato entra nella sua cartella): il catalogo segue il file
    lib = _lib()
    old = core.abspath(old_rel)
    new = os.path.realpath(core.abspath(new_rel))
    with _lock:
        lib.db.execute('UPDATE asset SET path = ? WHERE path = ?', (new, old))
        lib.db.execute('UPDATE cut SET path = ? WHERE path = ?', (new, old))
        lib.db.commit()
        _cache.clear()
    lib.log('move', 'asset', None, old_path=old, new_path=new)


# ---------------------------------------------------------------- dalla versione di prima (file JSON)
def migrate_legacy(lib):
    # gli stati dello studio scritti come file JSON e le letture tenute in cache: dentro la libreria, una volta.
    # Poi le cartelle si mettono da parte (non si cancellano): niente piu' si legge da li'.
    sd, td = os.path.join(core.DATA, 'state'), os.path.join(core.DATA, 'text')
    moved_any = False
    if os.path.isdir(sd) and os.listdir(sd):
        for f in sorted(os.listdir(sd)):
            if not f.endswith('.json'):
                continue
            try:
                st = json.load(open(os.path.join(sd, f)))
                if not os.path.exists(core.abspath(st['rel'])):
                    continue
                a = asset_for(lib, st['rel'], create=True)
                if lib.db.execute('SELECT version FROM editstate WHERE asset_id = ?', (a['id'],)).fetchone():
                    continue                                   # gia' nella libreria
                st.pop('names', None)
                save(st)
                lib.log('migrate', 'asset', a['uuid'], from_file=f)
            except Exception as e:
                lib.log('migrate', 'library', None, 'fail', file=f, error=str(e))
        moved_any = True
    if os.path.isdir(td) and os.listdir(td):
        bridge.import_read_cache(lib)
        moved_any = True
    bm = core.batch_memory_path()
    if os.path.exists(bm):
        # la memoria delle serie (motore dell'ultimo taglio): nella libreria
        try:
            mem = json.load(open(bm))
            with lib.db:
                lib.db.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('series_memory', ?)", (json.dumps(mem),))
            os.rename(bm, bm + '.migrated-' + time.strftime('%Y%m%d-%H%M%S'))
            lib.log('migrate', 'library', lib.meta('uuid'), moved='batch-memory.json -> setting series_memory')
        except (OSError, ValueError) as e:
            lib.log('migrate', 'library', None, 'fail', file='batch-memory.json', error=str(e))
    if moved_any:
        stamp = time.strftime('%Y%m%d-%H%M%S')
        for d in (sd, td):
            if os.path.isdir(d) and os.listdir(d):
                os.rename(d, d + '.migrated-' + stamp)          # tenute da parte, non lette piu'
        lib.log('migrate', 'library', lib.meta('uuid'), retired='studio-data/state and studio-data/text (kept aside)')
