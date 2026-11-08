# libreria di Scan Studio: un pacchetto <nome>.scanlib/ con
#   library.sqlite   il catalogo (schema.sql)
#   store/ab/<sha256>.<ext>   i file "gestiti", per contenuto: il nome e' il checksum (niente doppioni)
#   store/ab/<sha256>.<ext>.json   il sidecar: cio' che il catalogo sa di quel file, scritto solo quando cambia
#   snapshots/       copie del catalogo (le ultime 10), prima di ogni modifica grossa e all'apertura
#   cache/           anteprime e maschere, si possono cancellare
# I file "referenziati" restano dove sono (es. ~/Scans/originals): il catalogo ne tiene percorso e checksum.
# Regole di sempre: un file non si sovrascrive mai, non si perde mai, i pixel non cambiano.

import os, json, uuid as _uuid, shutil, sqlite3, hashlib, time, threading
from datetime import datetime, timezone

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
PLACES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'places.sql')
SCHEMA_VERSION = 1
CATEGORIES = [('drawing', 'Drawing'), ('document', 'Document'), ('photograph', 'Digital photograph'), ('scan', 'Digital scan'), ('print', 'Print'), ('painting', 'Painting'), ('book', 'Book'), ('object', 'Object'), ('installation', 'Installation'), ('sculpture', 'Sculpture'), ('model', '3D model'), ('video', 'Digital video'), ('sound', 'Sound recording')]
AGENT = 'Scan Studio'
KEEP_SNAPSHOTS = 10


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def new_uuid():
    return str(_uuid.uuid4())


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


class Library:
    def __init__(self, path, create=False, name=None):
        self.path = os.path.abspath(os.path.expanduser(path))
        if not self.path.endswith('.scanlib'):
            self.path += '.scanlib'
        self.db_path = os.path.join(self.path, 'library.sqlite')
        if create:
            if os.path.exists(self.db_path):
                raise FileExistsError(f'{self.path} is already a library')
            for d in ('store', 'snapshots', 'cache'):
                os.makedirs(os.path.join(self.path, d), exist_ok=True)
        elif not os.path.exists(self.db_path):
            raise FileNotFoundError(f'no library at {self.path}')
        self._local = threading.local()
        if create:
            c = self.db
            c.executescript(open(SCHEMA).read())
            c.executescript(open(PLACES).read())
            c.executemany('INSERT INTO category (key, label, position) VALUES (?,?,?)', [(k, l, i) for i, (k, l) in enumerate(CATEGORIES)])
            with c:
                c.executemany('INSERT INTO meta VALUES (?, ?)', [
                    ('schema_version', str(SCHEMA_VERSION)), ('uuid', new_uuid()),
                    ('name', name or os.path.splitext(os.path.basename(self.path))[0]), ('created_at', now())])
            self.log('create', 'library', None)
        else:
            self.snapshot('open')
            self.migrate()

    # una connessione per thread (il server e' a thread); WAL: chi legge non aspetta chi scrive
    @property
    def db(self):
        c = getattr(self._local, 'c', None)
        if c is None:
            c = sqlite3.connect(self.db_path, timeout=30)
            c.row_factory = sqlite3.Row
            for p in ('journal_mode = WAL', 'synchronous = NORMAL', 'foreign_keys = ON', 'temp_store = MEMORY',
                      'mmap_size = 268435456', 'cache_size = -65536', 'busy_timeout = 30000'):
                c.execute('PRAGMA ' + p)
            self._local.c = c
        return c

    def meta(self, key):
        r = self.db.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()
        return r[0] if r else None

    # ------------------------------------------------------------ registro (come PREMIS)
    def log(self, type_, entity, entity_uuid, outcome='ok', **detail):
        self.db.execute('INSERT INTO event (at, type, entity, entity_uuid, outcome, detail, agent) VALUES (?,?,?,?,?,?,?)',
                        (now(), type_, entity, entity_uuid, outcome, json.dumps(detail) if detail else None, AGENT))
        self.db.commit()

    # ------------------------------------------------------------ copie del catalogo
    def snapshot(self, why='manual'):
        # la API di backup di SQLite: una copia coerente anche mentre si scrive
        d = os.path.join(self.path, 'snapshots')
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, time.strftime('%Y%m%d-%H%M%S') + f'-{why}.sqlite')
        if os.path.exists(out):
            return out
        dst = sqlite3.connect(out)
        with dst:
            self.db.backup(dst)
        dst.close()
        snaps = sorted(f for f in os.listdir(d) if f.endswith('.sqlite'))
        for f in snaps[:-KEEP_SNAPSHOTS]:
            os.remove(os.path.join(d, f))
        return out

    # ------------------------------------------------------------ file
    def add_asset(self, src, managed=True, derived_from=None, made_with=None):
        # un file entra nella libreria: gestito (copiato nello store per checksum) o referenziato (resta li')
        src = os.path.abspath(src)
        digest, size = sha256(src), os.path.getsize(src)
        if managed:
            # gestiti: il nome e' il contenuto, stessi byte = lo stesso file (nessun doppione)
            old = self.db.execute("SELECT * FROM asset WHERE sha256 = ? AND storage = 'managed'", (digest,)).fetchone()
            if old:
                return old['id'], False
        else:
            # referenziati: un percorso e' un file. Stessi byte in due posti sono due file; lo stesso percorso
            # con byte diversi e' un file cambiato (chi lo cambia sposta prima il record di prima nella storia)
            real = os.path.realpath(src)
            old = self.db.execute('SELECT * FROM asset WHERE path IN (?, ?)', (src, real)).fetchone()
            if old and old['sha256'] == digest:
                return old['id'], False
            if old:
                self.db.execute('UPDATE asset SET sha256 = ?, size = ? WHERE id = ?', (digest, size, old['id']))
                self.db.commit()
                self.log('changed', 'asset', old['uuid'], path=src, old_sha256=old['sha256'], new_sha256=digest)
                return old['id'], False
            # lo stesso file spostato (il vecchio percorso non c'e' piu'): il record segue il file
            gone = [r for r in self.db.execute("SELECT * FROM asset WHERE sha256 = ? AND storage = 'referenced'", (digest,)).fetchall()
                    if not os.path.exists(r['path'])]
            if gone:
                self.db.execute('UPDATE asset SET path = ? WHERE id = ?', (real, gone[0]['id']))
                self.db.commit()
                self.log('move', 'asset', gone[0]['uuid'], old_path=gone[0]['path'], new_path=real)
                return gone[0]['id'], False
            src = real
        ext = os.path.splitext(src)[1].lower()
        if managed:
            rel = os.path.join('store', digest[:2], digest + ext)
            dst = os.path.join(self.path, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                tmp = dst + '.part'
                try:
                    os.link(src, tmp)                    # stesso disco: un nome in piu', niente copia
                except OSError:
                    shutil.copy2(src, tmp)
                if sha256(tmp) != digest:
                    os.remove(tmp)
                    raise IOError(f'copy of {src} differs from the original')
                os.replace(tmp, dst)
            path = rel
        else:
            path = src
        info = image_info(src)
        u = new_uuid()
        cur = self.db.execute(
            'INSERT INTO asset (uuid, sha256, size, storage, path, original_name, mime, width, height, dpi, bits, channels, icc,'
            ' file_mtime, imported_at, technical, derived_from, made_with) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (u, digest, size, 'managed' if managed else 'referenced', path, os.path.basename(src), info.get('mime'),
             info.get('width'), info.get('height'), info.get('dpi'), info.get('bits'), info.get('channels'), info.get('icc'),
             datetime.fromtimestamp(os.path.getmtime(src), timezone.utc).isoformat(timespec='seconds'), now(),
             json.dumps(info.get('technical')) if info.get('technical') else None, derived_from, made_with))
        self.db.commit()
        self.log('import', 'asset', u, sha256=digest, source=src, storage='managed' if managed else 'referenced')
        return cur.lastrowid, True

    def asset_path(self, asset):
        return os.path.join(self.path, asset['path']) if asset['storage'] == 'managed' else asset['path']

    def check_fixity(self, limit=None):
        # ogni file e' ancora quello? (il checksum di oggi contro quello dell'import)
        bad = []
        for a in self.db.execute('SELECT * FROM asset ORDER BY id' + (f' LIMIT {int(limit)}' if limit else '')).fetchall():
            p = self.asset_path(a)
            ok = os.path.exists(p) and sha256(p) == a['sha256']
            self.log('fixity', 'asset', a['uuid'], 'ok' if ok else 'fail', path=p)
            if not ok:
                bad.append(a['uuid'])
        return bad

    # ------------------------------------------------------------ oggetti, zone, testo
    def series(self, name):
        # la serie con questo nome (creata se non c'e'); None per nessuna serie
        if not name:
            return None
        r = self.db.execute('SELECT id FROM series WHERE name = ?', (name,)).fetchone()
        if r:
            return r[0]
        u = new_uuid()
        cur = self.db.execute('INSERT INTO series (uuid, name, created_at) VALUES (?, ?, ?)', (u, name, now()))
        self.db.commit()
        self.log('create', 'series', u, name=name)
        return cur.lastrowid

    def new_item(self, title=None, kind='scan', batch=None, date=None, assets=(), parent_id=None):
        u, t = new_uuid(), now()
        cur = self.db.execute('INSERT INTO item (uuid, kind, parent_id, title, date, series_id, created_at, modified_at) VALUES (?,?,?,?,?,?,?,?)',
                              (u, kind, parent_id, title, date, self.series(batch), t, t))
        iid = cur.lastrowid
        for i, a in enumerate(assets):
            self.db.execute('INSERT INTO item_asset (item_id, asset_id, position) VALUES (?,?,?)', (iid, a, i))
        self.db.commit()
        self.reindex(iid)
        return iid

    def link_asset(self, item_id, asset_id, role='view'):
        pos = self.db.execute('SELECT COALESCE(MAX(position) + 1, 0) FROM item_asset WHERE item_id = ?', (item_id,)).fetchone()[0]
        self.db.execute('INSERT OR IGNORE INTO item_asset (item_id, asset_id, role, position) VALUES (?,?,?,?)', (item_id, asset_id, role, pos))
        self.db.commit()
        self.touched(item_id)

    def add_region(self, item_id, asset_id, kind, geometry, label=None, parent_id=None, source=None, color=None):
        u, t = new_uuid(), now()
        pos = self.db.execute('SELECT COALESCE(MAX(position) + 1, 0) FROM region WHERE item_id = ?', (item_id,)).fetchone()[0]
        cur = self.db.execute('INSERT INTO region (uuid, item_id, asset_id, parent_id, kind, label, geometry, source, position, color,'
                              ' created_at, modified_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                              (u, item_id, asset_id, parent_id, kind, label, json.dumps(geometry),
                               json.dumps(source) if source else None, pos, color, t, t))
        self.db.commit()
        self.touched(item_id)
        return cur.lastrowid

    def add_reading(self, asset_id, engine, plain, region_id=None, model=None, doc=None, raw=None, languages=None,
                    confidence=None, params=None, model_digest=None):
        u = new_uuid()
        cur = self.db.execute('INSERT INTO reading (uuid, region_id, asset_id, engine, model, model_digest, params, languages,'
                              ' confidence, plain, doc, raw, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                              (u, region_id, asset_id, engine, model, model_digest, json.dumps(params) if params else None,
                               languages, confidence, plain, json.dumps(doc) if doc else None, raw, now()))
        self.db.commit()
        self.log('read', 'reading', u, engine=engine, model=model)
        self.touched(self._item_of(asset_id, region_id))
        return cur.lastrowid

    def correct(self, reading_id, plain, doc=None, note=None):
        # una correzione a mano: una versione in piu', la lettura del motore resta com'era
        v = self.db.execute('SELECT COALESCE(MAX(version), 0) + 1 FROM correction WHERE reading_id = ?', (reading_id,)).fetchone()[0]
        self.db.execute('INSERT INTO correction (reading_id, version, plain, doc, note, created_at) VALUES (?,?,?,?,?,?)',
                        (reading_id, v, plain, json.dumps(doc) if doc else None, note, now()))
        self.db.commit()
        r = self.db.execute('SELECT uuid, asset_id, region_id FROM reading WHERE id = ?', (reading_id,)).fetchone()
        self.log('correct', 'reading', r['uuid'], version=v)
        self.touched(self._item_of(r['asset_id'], r['region_id']))
        return v

    def migrate(self):
        # librerie gia' create con uno schema precedente: le tabelle nuove si aggiungono
        have = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if 'export' in have and 'cut' not in have:
            self.db.executescript('ALTER TABLE export RENAME TO cut; CREATE INDEX IF NOT EXISTS cut_region ON cut(region_id); CREATE INDEX IF NOT EXISTS cut_path ON cut(path);')
            self.log('migrate', 'library', self.meta('uuid'), renamed='export -> cut')
        if 'series' not in have:
            # la serie diventa una cosa: dalla vecchia colonna item.batch, solo dove l'oggetto sta in una cartella
            self.db.executescript('''CREATE TABLE series (id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                notes TEXT, created_at TEXT NOT NULL) STRICT;
                ALTER TABLE item ADD COLUMN series_id INTEGER REFERENCES series(id) ON DELETE SET NULL;
                CREATE INDEX item_series ON item(series_id);''')
            cols = {r[1] for r in self.db.execute('PRAGMA table_info(item)')}
            if 'batch' in cols:
                for (b,) in self.db.execute('SELECT DISTINCT batch FROM item WHERE batch IS NOT NULL').fetchall():
                    self.db.execute('INSERT OR IGNORE INTO series (uuid, name, created_at) VALUES (?, ?, ?)', (new_uuid(), b, now()))
                self.db.execute('UPDATE item SET series_id = (SELECT id FROM series WHERE name = item.batch)')
                self.db.executescript('DROP INDEX IF EXISTS item_batch; ALTER TABLE item DROP COLUMN batch;')
            self.db.commit()
            self.log('migrate', 'library', self.meta('uuid'), added='series (from item.batch)')
        if 'editstate' not in have:
            self.db.executescript('''CREATE TABLE editstate (asset_id INTEGER PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
                version INTEGER NOT NULL DEFAULT 0, engine TEXT, params TEXT CHECK (params IS NULL OR json_valid(params)), cut_at REAL,
                history TEXT CHECK (history IS NULL OR json_valid(history)), saved_at REAL) STRICT;''')
            if 'removed_at' not in {r[1] for r in self.db.execute('PRAGMA table_info(region)')}:
                self.db.executescript('ALTER TABLE region ADD COLUMN removed_at TEXT; CREATE INDEX IF NOT EXISTS region_asset ON region(asset_id, removed_at, position);')
            # le zone segnate a mano come tolte (versione di prima) diventano tolte davvero
            self.db.execute("UPDATE region SET removed_at = modified_at, label = NULLIF(TRIM(REPLACE(REPLACE(label, '(removed in studio)', ''), 'removed in studio', '')), '') "
                            "WHERE label LIKE '%removed in studio%'")
            self.db.commit()
            self.log('migrate', 'library', self.meta('uuid'), added='editstate, region.removed_at')
        if 'trash' not in have:
            self.db.executescript('''CREATE TABLE trash (
  id          INTEGER PRIMARY KEY,
  uuid        TEXT NOT NULL UNIQUE,
  what        TEXT NOT NULL CHECK (what IN ('item', 'cut')),
  ref         TEXT NOT NULL,                        -- uuid dell'oggetto o dell'asset del taglio
  title       TEXT,
  files       TEXT NOT NULL CHECK (json_valid(files)),     -- [{asset, from, to}]
  regions_off TEXT CHECK (regions_off IS NULL OR json_valid(regions_off)),   -- parti tolte dal taglio con lui
  trashed_at  TEXT NOT NULL
) STRICT;
''')
            self.log('migrate', 'library', self.meta('uuid'), added='trash')
        if 'place' not in have:
            cols = {r[1] for r in self.db.execute('PRAGMA table_info(region)')}
            self.db.executescript(open(PLACES).read().split('CREATE TRIGGER')[0])
            if 'place_id' not in cols:
                self.db.executescript('ALTER TABLE region ADD COLUMN place_id INTEGER REFERENCES place(id) ON DELETE SET NULL; '
                                      'ALTER TABLE region ADD COLUMN place_number INTEGER; ALTER TABLE region ADD COLUMN category TEXT; '
                                      'ALTER TABLE item ADD COLUMN place_id INTEGER REFERENCES place(id) ON DELETE SET NULL; ALTER TABLE item ADD COLUMN category TEXT;')
            self.db.executescript('CREATE TRIGGER' + 'CREATE TRIGGER'.join(open(PLACES).read().split('CREATE TRIGGER')[1:]))
            self.db.executemany('INSERT OR IGNORE INTO category (key, label, position) VALUES (?,?,?)', [(k, l, i) for i, (k, l) in enumerate(CATEGORIES)])
            self.db.commit()
            self.log('migrate', 'library', self.meta('uuid'), added='place, category')
        if 'capture' not in have:
            self.db.executescript('''CREATE TABLE capture (id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
                asset_id INTEGER REFERENCES asset(id) ON DELETE SET NULL, how TEXT NOT NULL, name TEXT, series TEXT, device TEXT,
                settings TEXT CHECK (settings IS NULL OR json_valid(settings)), captured_at TEXT NOT NULL) STRICT;
                CREATE INDEX capture_sha ON capture(sha256); CREATE INDEX capture_asset ON capture(asset_id);''')
            self.log('migrate', 'library', self.meta('uuid'), added='capture')
        if 'text_link' not in have:
            self.db.executescript('''CREATE TABLE text_link (reading_id INTEGER NOT NULL REFERENCES reading(id) ON DELETE CASCADE,
                asset_id INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE, PRIMARY KEY (reading_id, asset_id)) STRICT;
                CREATE INDEX text_link_asset ON text_link(asset_id);''')
            self.log('migrate', 'library', self.meta('uuid'), added='text_link')

    def _item_of(self, asset_id, region_id):
        if region_id:
            return self.db.execute('SELECT item_id FROM region WHERE id = ?', (region_id,)).fetchone()[0]
        r = self.db.execute('SELECT item_id FROM item_asset WHERE asset_id = ? ORDER BY position LIMIT 1', (asset_id,)).fetchone()
        return r[0] if r else None

    # ------------------------------------------------------------ dopo ogni modifica: ricerca e sidecar
    def touched(self, item_id):
        if not item_id:
            return
        self.db.execute('UPDATE item SET modified_at = ? WHERE id = ?', (now(), item_id))
        self.db.commit()
        self.reindex(item_id)
        self.write_sidecars(item_id)

    def reindex(self, item_id):
        it = self.db.execute('SELECT * FROM item WHERE id = ?', (item_id,)).fetchone()
        labels = ' '.join(r[0] for r in self.db.execute('SELECT label FROM region WHERE item_id = ? AND label IS NOT NULL', (item_id,)))
        text = '\n'.join(r[0] for r in self.db.execute(
            'SELECT t.plain FROM current_text t WHERE t.region_id IN (SELECT id FROM region WHERE item_id = ?)'
            ' OR (t.region_id IS NULL AND t.asset_id IN (SELECT asset_id FROM item_asset WHERE item_id = ?))', (item_id, item_id)))
        self.db.execute('DELETE FROM search WHERE item_uuid = ?', (it['uuid'],))
        self.db.execute('INSERT INTO search (item_uuid, title, notes, labels, text) VALUES (?,?,?,?,?)',
                        (it['uuid'], it['title'] or '', it['notes'] or '', labels, text))
        self.db.commit()

    def write_sidecars(self, item_id):
        # accanto a ogni file gestito, cio' che la libreria ne sa (pochi KB): se il catalogo si perde,
        # da store/ si ricostruisce tutto. Solo quando qualcosa cambia, mai solo guardando.
        for a in self.db.execute('SELECT a.* FROM asset a JOIN item_asset ia ON ia.asset_id = a.id WHERE ia.item_id = ?', (item_id,)):
            if a['storage'] != 'managed':
                continue
            data = self.describe_asset(a['id'])
            p = self.asset_path(a) + '.json'
            tmp = p + '.part'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)

    def describe_asset(self, asset_id):
        q = lambda sql, *a: [dict(r) for r in self.db.execute(sql, a)]
        a = q('SELECT * FROM asset WHERE id = ?', asset_id)[0]
        items = q('SELECT i.* FROM item i JOIN item_asset ia ON ia.item_id = i.id WHERE ia.asset_id = ?', asset_id)
        regions = q('SELECT * FROM region WHERE asset_id = ? ORDER BY position', asset_id)
        readings = q('SELECT * FROM reading WHERE asset_id = ? ORDER BY created_at', asset_id)
        corrections = q('SELECT c.* FROM correction c JOIN reading r ON r.id = c.reading_id WHERE r.asset_id = ? ORDER BY c.reading_id, c.version', asset_id)
        return {'scan_studio_sidecar': SCHEMA_VERSION, 'library': self.meta('uuid'), 'written_at': now(),
                'asset': a, 'items': items, 'regions': regions, 'readings': readings, 'corrections': corrections}

    # ------------------------------------------------------------ ricerca
    def search(self, q, limit=50):
        return [dict(r) for r in self.db.execute(
            "SELECT i.uuid, i.title, snippet(search, 4, '[', ']', '…', 12) AS snippet FROM search"
            ' JOIN item i ON i.uuid = search.item_uuid WHERE search MATCH ? AND i.trashed_at IS NULL ORDER BY rank LIMIT ?', (q, limit))]


def image_info(path):
    # misure, profondita', profilo: per il catalogo (si legge senza caricare i pixel)
    out = {}
    try:
        from PIL import Image
        with Image.open(path) as im:
            out['width'], out['height'] = im.size
            out['mime'] = Image.MIME.get(im.format)
            d = im.info.get('dpi')
            out['dpi'] = float(d[0]) if d and d[0] else None
            out['bits'] = 16 if im.mode in ('I;16', 'I;16B', 'I;16L', 'I') else 8
            out['channels'] = len(im.getbands())
            if im.info.get('icc_profile'):
                out['icc'] = f'{len(im.info["icc_profile"])} bytes'
    except Exception:
        pass
    return out
