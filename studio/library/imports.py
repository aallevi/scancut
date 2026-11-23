# cartelle d'importazione, come l'Auto-Import di Eagle: cartelle scelte (una chiavetta, la cartella dei
# download, quella di un altro programma) che lo studio guarda mentre e' aperto. Un'immagine nuova e ferma
# entra nella libreria come una scansione fatta dallo studio: copiata (controllata) nella cartella dello
# scanner, poi archiviata con le stesse regole (mai sovrascritta, doppioni riconosciuti, JPEG XL senza perdita
# in una libreria con i file dentro). Con "move" il file lascia la cartella solo quando e' al sicuro; con
# "copy" resta, e non si importa due volte. L'elenco sta nella libreria (setting 'import_folders').

import os, json, time, shutil, hashlib, threading

from .. import core

KEY = 'import_folders'
_seen_lock = threading.Lock()
_sizes = {}                                     # percorso -> (dimensione, ora) al giro prima: un file fermo si prende
STEADY = 3                                      # secondi senza cambiare prima di prenderlo (lo scanner o la copia finiscono)


def folders(lib):
    r = lib.db.execute('SELECT value FROM setting WHERE key = ?', (KEY,)).fetchone()
    out = json.loads(r[0]) if r else []
    return [f for f in out if isinstance(f, dict) and f.get('path')]


def set_folders(lib, items):
    clean, seen = [], set()
    root = os.path.realpath(core.ROOT)
    for f in items or []:
        p = os.path.realpath(os.path.expanduser(str(f.get('path') or '')))
        if not p or p in seen:
            continue
        if not os.path.isdir(p):
            raise ValueError(f'not a folder: {p}')
        # la radice e le sue cartelle (inbox, originals, il pacchetto) le guarda gia' l'agente o sono la libreria
        if p == root or p.startswith(root + os.sep) or root.startswith(p + os.sep):
            raise ValueError(f'{p} is the scans folder or inside it: its inbox is already watched')
        seen.add(p)
        clean.append({'path': p, 'mode': 'copy' if f.get('mode') == 'copy' else 'move'})
    with lib.db:
        lib.db.execute('INSERT OR REPLACE INTO setting (key, value) VALUES (?, ?)', (KEY, json.dumps(clean)))
    lib.log('settings', 'library', lib.meta('uuid'), import_folders=[f['path'] for f in clean])
    return clean


def _seen_path():
    return os.path.join(core.DATA, 'cache', 'imported.json')


def _seen():
    try:
        with open(_seen_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _remember(keys):
    with _seen_lock:
        s = _seen()
        s.update({k: time.time() for k in keys})
        os.makedirs(os.path.dirname(_seen_path()), exist_ok=True)
        with open(_seen_path() + '.part', 'w') as f:
            json.dump(s, f)
        os.replace(_seen_path() + '.part', _seen_path())


def _key(p, st):
    return f'{p}\0{st.st_size}\0{st.st_mtime_ns}'


def waiting(folder, now=None):
    # le immagini nuove e ferme di una cartella (non le sottocartelle, non i file nascosti o a meta')
    now = now or time.time()
    out, seen = [], _seen()
    try:
        names = sorted(os.listdir(folder['path']), key=str.lower)
    except OSError:
        return []
    for f in names:
        p = os.path.join(folder['path'], f)
        if f.startswith('.') or f.endswith(('.part', '.crdownload', '.download')) or not core.is_image(f):
            continue
        try:
            st = os.stat(p)
        except OSError:
            continue
        if not os.path.isfile(p) or st.st_size == 0:
            continue
        if folder['mode'] == 'copy' and _key(p, st) in seen:
            continue                                # gia' importata: resta li', non si prende di nuovo
        prev = _sizes.get(p)
        _sizes[p] = (st.st_size, st.st_mtime_ns)
        if prev != (st.st_size, st.st_mtime_ns) or now - st.st_mtime < STEADY:
            continue                                # cambia ancora (o appena visto): al prossimo giro
        out.append((p, st))
    return out


def _sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def already_in(lib, h):
    # la stessa immagine, byte per byte, e' gia' nella libreria (con qualunque nome, in qualunque serie)? Anche se
    # poi e' passata in JPEG XL: packed.tsv tiene il checksum con cui e' arrivata
    r = lib.db.execute("SELECT a.path FROM asset a WHERE a.sha256 = ? AND a.path NOT LIKE '%/studio-data/%' LIMIT 1", (h,)).fetchone()
    if r and os.path.exists(r[0]):
        return r[0]
    led = os.path.join(core.ROOT, '.scancut', 'packed.tsv')
    if os.path.exists(led):
        for line in open(led):
            x = line.rstrip('\n').split('\t')
            if len(x) >= 3 and x[0] == h and os.path.exists(os.path.join(core.sc.ORIG, x[2])):
                return os.path.join(core.sc.ORIG, x[2])
    return None


def stage(p):
    # una copia controllata nella cartella dello scanner (nascosta mentre si scrive): da li' l'archiviazione
    # la porta fra le fonti; se lo studio si chiude a meta', alla prossima apertura si archivia (scans_left)
    d = core.scanning_dir()
    name = os.path.basename(p)
    dst = os.path.join(d, name)
    k = 2
    while os.path.exists(dst):
        stem, ext = os.path.splitext(name)
        dst = os.path.join(d, f'{stem} ({k}){ext}'); k += 1
    tmp = os.path.join(d, '.' + os.path.basename(dst) + '.part')
    shutil.copy2(p, tmp)
    if _sha(tmp) != _sha(p):
        os.remove(tmp)
        raise IOError(f'the copy of {name} differs from the file')
    os.replace(tmp, dst)
    return dst


def run_once(lib, file_scans, say=print):
    # un giro su tutte le cartelle: copia, archivia (file_scans: quella del server, che si vede in Lavori),
    # poi, con "move", toglie il file dalla sua cartella solo se e' fra le fonti (o c'era gia', identico)
    done = []
    for folder in folders(lib):
        todo = waiting(folder)
        if not todo:
            continue
        staged, seen = [], []
        for p, st in todo:
            try:
                twin = already_in(lib, _sha(p))
                if twin:
                    # gia' nella libreria: non entra due volte; "move" la toglie (e' al sicuro), "copy" la ricorda
                    say(f'{os.path.basename(p)}: identical to {core.relpath(twin)}, already in the library')
                    if folder['mode'] == 'move':
                        os.remove(p)
                    else:
                        seen.append(_key(p, st))
                    done.append((p, None))
                    continue
                staged.append((p, st, stage(p)))
            except OSError as e:
                say(f'{os.path.basename(p)}: not imported ({e})')
        if seen:
            _remember(seen); seen = []
        if not staged:
            continue
        res = dict(file_scans([s for _, _, s in staged]))
        from . import bridge
        bridge.register_new(lib)                    # nella libreria subito (un doppione al giro dopo si riconosce)
        for p, st, s in staged:
            if s not in res or os.path.exists(s):
                continue                            # non archiviata (resta nella cartella dello scanner): il file resta
            if folder['mode'] == 'move':
                try:
                    if os.stat(p).st_mtime_ns == st.st_mtime_ns and os.path.getsize(p) == st.st_size:
                        os.remove(p)                # al sicuro nella libreria: via dalla cartella
                except OSError:
                    pass
            else:
                seen.append(_key(p, st))
            done.append((p, res[s]))
        if seen:
            _remember(seen)
    return done


_started = [False]


def start(lib_fn, file_scans, every=3):
    # il giro ogni pochi secondi, finche' lo studio e' aperto (come Eagle: l'importazione e' dell'app aperta)
    if _started[0]:
        return
    _started[0] = True

    def loop():
        while True:
            time.sleep(every)
            try:
                lib = lib_fn()
                if lib and folders(lib):
                    run_once(lib, file_scans)
            except Exception as e:
                print('import folders:', type(e).__name__, e)
    threading.Thread(target=loop, daemon=True).start()
