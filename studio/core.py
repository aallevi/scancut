# core dello studio: motori di ritaglio, stato dei ritocchi, esportazione.
# Tutto in coordinate della scansione a piena risoluzione. Le sagome dei motori
# restano quelle (pixel per pixel); un ritocco cambia solo la zona toccata.
# Regole di scancut valgono anche qui: gli originali non si toccano, i ritagli
# non si sovrascrivono (i vecchi si spostano da parte), solo pixel veri.

import os, sys, json, time, hashlib, importlib.util, threading, fcntl, subprocess, shutil, re
import numpy as np, cv2
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import scancut as sc  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SCRIPTS = os.path.join(REPO, 'scripts')
SAM3_DIR = os.path.expanduser('~/sam3-hf')

ROOT = DATA = None
_lock = threading.RLock()
_engine_lock = threading.Lock()   # un motore alla volta (file temporanei, memoria)


def set_root(root):
    global ROOT, DATA
    ROOT = os.path.abspath(os.path.expanduser(root))
    sc.set_root(ROOT)
    DATA = os.path.join(ROOT, '.scancut', 'studio-data')
    for d in ('cache', 'state', 'previews', 'replaced'):
        os.makedirs(os.path.join(DATA, d), exist_ok=True)


# ---------------------------------------------------------------- percorsi

def abspath(rel):
    # solo file dentro la radice: rel e' relativo a ROOT (o assoluto ma dentro)
    p = os.path.realpath(os.path.join(ROOT, rel))
    if not (p == ROOT or p.startswith(ROOT + os.sep)):
        raise ValueError('path outside the scans folder')
    return p


def relpath(p):
    return os.path.relpath(os.path.realpath(p), ROOT)


def file_key(rel):
    st = os.stat(abspath(rel))
    return hashlib.sha1(f'{rel}\0{st.st_size}\0{int(st.st_mtime)}'.encode()).hexdigest()[:20]


def tree():
    out = []
    for top in ('originals', 'cut', 'failed', 'inbox'):
        d = os.path.join(ROOT, top)
        node = {'name': top, 'rel': top, 'count': 0, 'children': []}
        if os.path.isdir(d):
            for b in sorted(os.listdir(d), key=str.lower):
                bd = os.path.join(d, b)
                if b.startswith('.'):
                    continue
                if os.path.isdir(bd):
                    n = sum(1 for f in os.listdir(bd) if is_image(f))
                    node['children'].append({'name': b, 'rel': f'{top}/{b}', 'count': n})
                elif is_image(b):
                    node['count'] += 1
        out.append(node)
    return out


def is_image(f):
    return not f.startswith('.') and os.path.splitext(f)[1].lower() in sc.EXT


def listing(rel):
    d = abspath(rel)
    out = []
    for f in sorted(os.listdir(d), key=str.lower):
        p = os.path.join(d, f)
        if not is_image(f) or not os.path.exists(p):
            continue
        r = relpath(p) if not os.path.islink(p) else os.path.join(rel, f)
        st = load_state(r, create=False)
        out.append({'rel': r, 'name': f, 'size': os.path.getsize(p), 'mtime': os.path.getmtime(p),
                    'sheets': len([s for s in st['sheets'] if s.get('on', True)]) if st else None,
                    'engine': st.get('engine') if st else None,
                    'exported': bool(st and st.get('exported')),
                    'done': done_result(r)})
    return out


def done_result(rel):
    if not rel.startswith('originals/') or not os.path.exists(sc.DONE):
        return None
    key = rel[len('originals/'):]
    res = None
    for line in open(sc.DONE):
        p = line.rstrip('\n').split('\t')
        if len(p) >= 4 and p[0] == key:
            res = p[3]
    return res


# ---------------------------------------------------------------- immagini

_img_cache = {}


def image(rel):
    # rgb a piena risoluzione + ppm; le ultime due restano in memoria (zoom, ritagli)
    with _lock:
        k = file_key(rel)
        if k in _img_cache:
            return _img_cache[k]
        rgb, icc, dpi, ppm = sc.load(abspath(rel))
        if len(_img_cache) >= 2:
            _img_cache.pop(next(iter(_img_cache)))
        _img_cache[k] = (rgb, icc, dpi, ppm)
        return _img_cache[k]


def preview_path(rel, size):
    p = os.path.join(DATA, 'previews', f'{file_key(rel)}-{size}.jpg')
    if not os.path.exists(p):
        im = Image.open(abspath(rel))
        im.draft('RGB', (size, size))
        im = im.convert('RGB')
        im.thumbnail((size, size), Image.LANCZOS)
        tmp = p + '.part'
        im.save(tmp, 'JPEG', quality=88)
        os.replace(tmp, p)
    return p


def info(rel):
    rgb, icc, dpi, ppm = image(rel)
    h, w = rgb.shape[:2]
    return {'rel': rel, 'w': w, 'h': h, 'dpi': round(dpi), 'ppm': ppm,
            'mm': [round(w / ppm), round(h / ppm)], 'name': os.path.basename(rel)}


def tile(rel, x, y, w, h, out_w):
    rgb = image(rel)[0]
    H, W = rgb.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x + w)), min(H, int(y + h))
    crop = rgb[y0:y1, x0:x1]
    if crop.size == 0:
        crop = np.zeros((1, 1, 3), np.uint8)
    out_w = max(1, min(int(out_w), crop.shape[1] * 4))
    out_h = max(1, round(crop.shape[0] * out_w / max(crop.shape[1], 1)))
    interp = cv2.INTER_AREA if out_w < crop.shape[1] else cv2.INTER_NEAREST
    crop = cv2.resize(crop, (out_w, out_h), interpolation=interp)
    return crop, (x0, y0, x1, y1)


# ---------------------------------------------------------------- motori

def engines():
    out = [
        {'id': 'auto', 'name': 'Automatic (as the agent)', 'kind': 'builtin', 'available': True,
         'note': 'Classic cut; Apple Vision too when the paper is close to the lid colour.'},
        {'id': 'classic', 'name': 'Classic (magic wand)', 'kind': 'builtin', 'available': True,
         'note': 'Background colour, wand from outside, shadow pass. Keeps fibres and tears.'},
        {'id': 'vision', 'name': 'Apple Vision', 'kind': 'ai', 'available': os.path.exists(sc.VISION),
         'note': 'Foreground instances from macOS. Smooth edges; for white on white.'},
        {'id': 'sam3', 'name': 'SAM 3 (Meta)', 'kind': 'ai', 'available': os.path.exists(os.path.join(SAM3_DIR, 'config.json')),
         'note': f'Text prompt or box. Weights in {SAM3_DIR}.', 'params': [
             {'id': 'prompt', 'label': 'Prompt', 'type': 'text', 'default': 'sheet of paper'},
             {'id': 'threshold', 'label': 'Score', 'type': 'number', 'default': 0.4, 'step': 0.05},
             {'id': 'refine', 'label': 'Refine edge with wand', 'type': 'bool', 'default': True}]},
    ]
    for f in sorted(os.listdir(SCRIPTS)) if os.path.isdir(SCRIPTS) else []:
        if f.endswith('.py') and not f.startswith('_'):
            meta = {'id': 'script:' + f[:-3], 'name': f[:-3], 'kind': 'script', 'available': True, 'note': ''}
            try:
                src = open(os.path.join(SCRIPTS, f)).read()
                m = re.search(r'^NAME\s*=\s*[\'"](.+?)[\'"]', src, re.M)
                n = re.search(r'^NOTE\s*=\s*[\'"](.+?)[\'"]', src, re.M)
                if m: meta['name'] = m.group(1)
                if n: meta['note'] = n.group(1)
            except OSError:
                pass
            out.append(meta)
    return out


def _sheets_from_masks(masks, ppm):
    # masks: lista di (y, x, m, holes, exact) -> sagome per lo stato
    return [{'y': int(y), 'x': int(x), 'm': m.astype(bool), 'h': h.astype(bool), 'exact': bool(e)}
            for y, x, m, h, e in masks]


def run_engine(rel, engine, params=None, box=None):
    # ritorna la chiave della cache con le sagome trovate
    params = params or {}
    path = abspath(rel)
    rgb, icc, dpi, ppm = image(rel)
    key = hashlib.sha1(json.dumps([file_key(rel), engine, params, box], sort_keys=True).encode()).hexdigest()[:20]
    if os.path.exists(os.path.join(DATA, 'cache', key + '.npz')):
        return key
    t0 = time.time()
    sub, off = path, (0, 0)
    if box:
        # solo dentro il riquadro: si ritaglia una copia e si lavora su quella
        x0, y0, x1, y1 = [int(v) for v in box]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(rgb.shape[1], x1), min(rgb.shape[0], y1)
        sub = os.path.join(DATA, 'cache', f'.box-{os.getpid()}-{key}.png')
        Image.fromarray(rgb[y0:y1, x0:x1]).save(sub, dpi=(dpi, dpi))
        off = (y0, x0)
    _engine_lock.acquire()
    try:
        if engine in ('auto', 'classic'):
            sheets, *_ = sc.cut_scan(sub, ai=(engine == 'auto'), ppm=ppm if box else None)
            masks = [(y, x, *shape) for y, x, _, _, _, shape in sheets]
        elif engine == 'vision':
            srgb = np.asarray(Image.open(sub).convert('RGB')) if box else rgb
            masks = [(y, x, *shape) for y, x, _, _, _, shape in sc.cut_scan_ai(sub, srgb, ppm)]
        elif engine == 'sam3':
            masks = sam3_masks(sub, ppm, params, whole=bool(box))
        elif engine.startswith('script:'):
            masks = script_masks(engine[7:], sub, ppm, params)
        else:
            raise ValueError(f'unknown engine {engine}')
    finally:
        _engine_lock.release()
        if box and os.path.exists(sub):
            os.remove(sub)
    masks = [(y + off[0], x + off[1], m, h, e) for y, x, m, h, e in masks]
    save_cache(key, _sheets_from_masks(masks, ppm), {'engine': engine, 'params': params, 'box': box,
                                                      'seconds': round(time.time() - t0, 1)})
    return key


def save_cache(key, sheets, meta):
    arrs = {}
    for i, s in enumerate(sheets):
        arrs[f'm{i}'] = np.packbits(s['m'], axis=None)
        arrs[f'h{i}'] = np.packbits(s['h'], axis=None)
    meta = dict(meta, sheets=[{'y': s['y'], 'x': s['x'], 'shape': list(s['m'].shape), 'exact': s['exact']}
                              for s in sheets])
    tmp = os.path.join(DATA, 'cache', key + '.part.npz')
    np.savez_compressed(tmp, meta=np.frombuffer(json.dumps(meta).encode(), np.uint8), **arrs)
    os.replace(tmp, os.path.join(DATA, 'cache', key + '.npz'))


def load_cache(key):
    z = np.load(os.path.join(DATA, 'cache', key + '.npz'))
    meta = json.loads(bytes(z['meta']).decode())
    out = []
    for i, s in enumerate(meta['sheets']):
        n = s['shape'][0] * s['shape'][1]
        m = np.unpackbits(z[f'm{i}'])[:n].reshape(s['shape']).astype(bool)
        h = np.unpackbits(z[f'h{i}'])[:n].reshape(s['shape']).astype(bool)
        out.append(dict(s, m=m, h=h))
    return meta, out


def script_masks(name, path, ppm, params):
    # scripts/<nome>.py con segment(rgb, ppm, params) -> lista di maschere (piena risoluzione)
    # o di dict {'mask':..., 'holes':...}. Si ricarica a ogni giro: si modifica e si riprova.
    spec = importlib.util.spec_from_file_location('studio_script_' + name, os.path.join(SCRIPTS, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rgb = np.asarray(Image.open(path).convert('RGB'))
    out = []
    for r in mod.segment(rgb, ppm, params) or []:
        m = r['mask'] if isinstance(r, dict) else r
        h = r.get('holes') if isinstance(r, dict) else None
        m = np.asarray(m, bool)
        h = np.zeros_like(m) if h is None else np.asarray(h, bool)
        out.extend(_crop_mask(m, h, ppm))
    return out


def _crop_mask(m, h, ppm, exact=True):
    # una maschera grande come la scansione -> un pezzo per componente, ritagliato
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    out = []
    H, W = m.shape
    mg = int(3 * ppm)
    for i in range(1, n):
        x, y, w, hh, a = st[i]
        if a < 100 * ppm * ppm:
            continue
        x0, y0, x1, y1 = max(0, x - mg), max(0, y - mg), min(W, x + w + mg), min(H, y + hh + mg)
        mm = lab[y0:y1, x0:x1] == i
        out.append((y0, x0, mm, h[y0:y1, x0:x1] & mm, exact))
    return out


# ---------------------------------------------------------------- SAM 3
# Gira in un processo a parte (torch pesa e si carica una volta sola).

_sam = None


def sam3_proc():
    global _sam
    if _sam is None or _sam.poll() is not None:
        _sam = subprocess.Popen([sys.executable, '-I', os.path.join(REPO, 'studio', 'sam3_worker.py'), SAM3_DIR],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    return _sam


def sam3_masks(path, ppm, params, whole=False):
    out = os.path.join(DATA, 'cache', f'.sam-{os.getpid()}.npz')
    req = {'image': path, 'out': out, 'prompt': params.get('prompt') or 'sheet of paper',
           'threshold': float(params.get('threshold', 0.4)), 'whole': whole}
    with _lock:
        p = sam3_proc()
        p.stdin.write(json.dumps(req) + '\n'); p.stdin.flush()
        line = p.stdout.readline()
    if not line:
        raise RuntimeError('SAM 3 worker stopped (see errors in the terminal)')
    res = json.loads(line)
    if 'error' in res:
        raise RuntimeError('SAM 3: ' + res['error'])
    z = np.load(out); os.remove(out)
    full = z['masks']                                     # (n, H, W) bool
    rgb = np.asarray(Image.open(path).convert('RGB'))
    masks = []
    for m in full:
        if params.get('refine', True):
            m = refine_with_wand(rgb, m, ppm)
        masks.extend(_crop_mask(m, np.zeros_like(m), ppm))
    return masks


def refine_with_wand(rgb, m, ppm):
    # SAM da' la zona giusta ma a bassa risoluzione: il bordo vero si prende dalla
    # bacchetta del taglio classico, solo entro 2 mm dal bordo di SAM
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (3, 3), 0), cv2.COLOR_RGB2LAB).astype(np.float32)
    col, T = sc.background(lab)
    d = np.linalg.norm((lab - col) * sc.W_LAB, axis=2)
    band = int(2 * ppm)
    inner = cv2.erode(m.astype(np.uint8), sc.disk(band)).astype(bool)
    outer = cv2.dilate(m.astype(np.uint8), sc.disk(band)).astype(bool)
    zone = outer.copy(); zone[[0, -1], :] = False; zone[:, [0, -1]] = False
    _, L = cv2.connectedComponents(((d < T) & ~inner | ~zone).astype(np.uint8), connectivity=4)
    keep = zone & ~np.isin(L, np.unique(L[~zone]))
    n, lab_m, st, _ = cv2.connectedComponentsWithStats(keep.astype(np.uint8), 8)
    if n < 2:
        return m
    keep = lab_m == 1 + st[1:, 4].argmax()
    # se la bacchetta scappa (carta color fondo) si tiene SAM
    return keep if 0.85 < keep.sum() / max(m.sum(), 1) < 1.15 else m


# ---------------------------------------------------------------- stato dei ritocchi
# state/<chiave>.json: {rel, engine, cache, sheets: [{id, src, poly0, poly, ops, on, label}]}
#   src: [cache, indice] della sagoma del motore (o null: foglio disegnato a mano)
#   poly0: contorno semplificato della sagoma, poly: lo stesso dopo i ritocchi
#   ops: [{op: add|sub, kind: poly|stroke, pts: [[x,y]...], r}] in ordine

def state_path(rel):
    return os.path.join(DATA, 'state', hashlib.sha1(rel.encode()).hexdigest()[:20] + '.json')


def load_state(rel, create=True):
    p = state_path(rel)
    if os.path.exists(p):
        try:
            st = json.load(open(p))
            if st.get('rel') == rel:
                return st
        except ValueError:
            pass
    return {'rel': rel, 'engine': None, 'sheets': [], 'version': 0} if create else None


def save_state(st):
    st['version'] = int(st.get('version', 0)) + 1
    st['saved'] = time.time()
    p = state_path(st['rel'])
    tmp = p + '.part'
    with open(tmp, 'w') as f:
        json.dump(st, f)
    os.replace(tmp, p)
    return st


def contour(m, ppm, y=0, x=0):
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return []
    c = max(cnts, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, max(1.0, 0.12 * ppm), True)[:, 0, :]
    return [[int(px + x), int(py + y)] for px, py in c]


def holes_outline(h, ppm, y=0, x=0):
    cnts, _ = cv2.findContours(h.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [[[int(px + x), int(py + y)] for px, py in cv2.approxPolyDP(c, 1.0, True)[:, 0, :]]
            for c in cnts if len(c) >= 3]


def detect(rel, engine, params=None, box=None, replace=True):
    # gira un motore e mette i suoi fogli nello stato (al posto dei vecchi, o in aggiunta)
    key = run_engine(rel, engine, params, box)
    meta, sheets = load_cache(key)
    ppm = image(rel)[3]
    st = load_state(rel)
    if replace:
        st['sheets'] = []
    st['engine'] = engine
    st['params'] = params or {}
    st['exported'] = False
    n0 = max([int(s['id'][1:]) for s in st['sheets']] + [0])
    for i, s in enumerate(sheets):
        poly = contour(s['m'], ppm, s['y'], s['x'])
        if len(poly) < 3:
            continue
        st['sheets'].append({'id': f's{n0 + i + 1}', 'src': [key, i], 'engine': engine, 'poly0': poly,
                             'poly': poly, 'ops': [], 'on': True, 'label': '',
                             'holes': holes_outline(s['h'], ppm, s['y'], s['x'])})
    order_sheets(st, ppm)
    return save_state(st), meta


def order_sheets(st, ppm):
    # in ordine di lettura, come scancut: a fasce di 40 mm dall'alto, poi da sinistra
    band = 40 * ppm
    def k(s):
        p = np.array(s['poly'])
        return (int(p[:, 1].min() // band), int(p[:, 0].min()))
    st['sheets'].sort(key=k)


def compare(rel, engines_):
    # contorni di piu' motori sulla stessa scansione, senza toccare lo stato
    ppm = image(rel)[3]
    out = {}
    for e in engines_:
        try:
            meta, sheets = load_cache(run_engine(rel, e, {}))
            out[e] = {'polys': [contour(s['m'], ppm, s['y'], s['x']) for s in sheets],
                      'seconds': meta.get('seconds')}
        except Exception as ex:
            out[e] = {'error': str(ex)}
    return out


# ---------------------------------------------------------------- maschera finale

def _raster(pts, shape, off, kind='poly', r=0):
    y0, x0 = off
    M = np.zeros(shape, np.uint8)
    if not pts:
        return M.astype(bool)
    a = (np.array(pts, np.float64) - [x0, y0]).round().astype(np.int32)
    if kind == 'stroke':
        cv2.polylines(M, [a], False, 1, max(1, int(round(2 * r))), cv2.LINE_8)
        for p in a[:1]:
            cv2.circle(M, tuple(int(v) for v in p), max(1, int(round(r))), 1, -1)
    elif len(a) >= 3:
        cv2.fillPoly(M, [a], 1, cv2.LINE_8)
    return M.astype(bool)


def sheet_mask(rel, sheet):
    # (y0, x0, maschera, buchi, exact) del foglio con i ritocchi applicati
    rgb, _, _, ppm = image(rel)
    H, W = rgb.shape[:2]
    base = None
    if sheet.get('src'):
        _, cs = load_cache(sheet['src'][0])
        base = cs[sheet['src'][1]]
    pts = list(sheet['poly'])
    for o in sheet.get('ops', []):
        pts += o['pts']
    pts = np.array(pts) if pts else np.zeros((0, 2))
    r = max([o.get('r', 0) for o in sheet.get('ops', [])] + [0])
    mg = int(3 * ppm + r + 2)
    bx0, by0 = pts.min(0).astype(int) - mg if len(pts) else (0, 0)
    bx1, by1 = pts.max(0).astype(int) + mg if len(pts) else (0, 0)
    if base is not None:
        bx0, by0 = min(bx0, base['x']), min(by0, base['y'])
        bx1, by1 = max(bx1, base['x'] + base['shape'][1]), max(by1, base['y'] + base['shape'][0])
    bx0, by0, bx1, by1 = max(0, bx0), max(0, by0), min(W, bx1), min(H, by1)
    shape, off = (by1 - by0, bx1 - bx0), (by0, bx0)
    P = _raster(sheet['poly'], shape, off)
    M = np.zeros(shape, bool); Hh = np.zeros(shape, bool)
    exact = True
    if base is not None:
        ys, xs = base['y'] - by0, base['x'] - bx0
        h, w = base['m'].shape
        M[ys:ys + h, xs:xs + w] = base['m']
        Hh[ys:ys + h, xs:xs + w] = base['h']
        exact = base['exact']
        if sheet['poly'] != sheet['poly0']:
            # dove il contorno e' stato spostato: fuori si toglie, dentro si aggiunge;
            # altrove resta la sagoma del motore, fibre comprese
            P0 = _raster(sheet['poly0'], shape, off)
            M = (M & ~(P0 & ~P)) | (P & ~P0)
    elif sheet.get('base') == 'ops':
        pass                            # foglio fatto solo di operazioni (bacchetta): parte vuoto
    else:
        M = P
    for o in sheet.get('ops', []):
        if o.get('kind') == 'wand':
            R = wand_region(rel, o['seed'], o['tol'], o.get('contig', True))[by0:by1, bx0:bx1]
        else:
            R = _raster(o['pts'], shape, off, o.get('kind', 'poly'), o.get('r', 0))
        M = M | R if o['op'] == 'add' else M & ~R
    Hh &= M
    return by0, bx0, M, Hh, exact


# ---------------------------------------------------------------- bacchetta magica (a mano)
# Come in Photoshop: dal pixel cliccato, tutti i pixel entro la tolleranza (per canale,
# sulla copia sfocata 3x3 come la bacchetta del taglio), contigui o in tutta la scansione.

_wand_cache = {}


def wand_region(rel, seed, tol, contig=True):
    k = (file_key(rel), tuple(int(v) for v in seed), int(tol), bool(contig))
    if k in _wand_cache:
        return _wand_cache[k]
    rgb = image(rel)[0]
    blur = cv2.GaussianBlur(rgb, (3, 3), 0)
    x, y = int(seed[0]), int(seed[1])
    H, W = blur.shape[:2]
    if not (0 <= x < W and 0 <= y < H):
        return np.zeros((H, W), bool)
    if contig:
        m = np.zeros((H + 2, W + 2), np.uint8)
        cv2.floodFill(blur.copy(), m, (x, y), 0, (int(tol),) * 3, (int(tol),) * 3,
                      4 | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY | (1 << 8))
        R = m[1:-1, 1:-1] > 0
    else:
        R = (np.abs(blur.astype(np.int16) - blur[y, x].astype(np.int16)) <= int(tol)).all(2)
    if len(_wand_cache) > 6:
        _wand_cache.pop(next(iter(_wand_cache)))
    _wand_cache[k] = R
    return R


def wand(rel, x, y, tol, contig=True):
    # l'operazione da mettere nello stato: il seme e la tolleranza (si rifa' uguale a ogni
    # esportazione), piu' riquadro e contorni solo per disegnarla
    R = wand_region(rel, (x, y), tol, contig)
    ppm = image(rel)[3]
    if not R.any():
        return None
    ys, xs = np.nonzero(R)
    cnts, _ = cv2.findContours(R.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:40]
    outline = [[[int(a), int(b)] for a, b in cv2.approxPolyDP(c, max(1.0, 0.12 * ppm), True)[:, 0, :]]
               for c in cnts if len(c) >= 3]
    return {'kind': 'wand', 'seed': [int(x), int(y)], 'tol': int(tol), 'contig': bool(contig),
            'pts': [[int(xs.min()), int(ys.min())], [int(xs.max()) + 1, int(ys.max()) + 1]],
            'outline': outline, 'area': int(R.sum())}


_mask_cache = {}


def sheet_mask_cached(rel, sheet):
    # le stesse maschere servono a ogni zoom: si tengono le ultime
    k = hashlib.sha1(json.dumps([file_key(rel), sheet], sort_keys=True).encode()).hexdigest()
    if k not in _mask_cache:
        if len(_mask_cache) > 12:
            _mask_cache.pop(next(iter(_mask_cache)))
        _mask_cache[k] = sheet_mask(rel, sheet)
    return _mask_cache[k]


def cut_sheet(rel, sheet):
    # il ritaglio come lo fa scancut: raddrizzato, solo la trasparenza cambia
    rgb, icc, dpi, ppm = image(rel)
    y0, x0, M, Hh, exact = sheet_mask_cached(rel, sheet)
    if M.sum() < 50:
        return None
    crop = rgb[y0:y0 + M.shape[0], x0:x0 + M.shape[1]]
    rgba, ang, rect = sc.cutout(crop, M, Hh, ppm, exact=exact)
    return rgba, ang, rect


# ---------------------------------------------------------------- nomi e cartelle

DEFAULT_SETTINGS = {
    'out_root': 'cut',                 # relativo alla radice, o assoluto
    'template': '{batch}/{stem}{sheet}',
    'batch_folders': {},               # lotto -> cartella diversa
    'eagle': False,                    # aggiungere anche a Eagle (API locale)
    'eagle_folder': '',
    'claude_tools': 'Read,Bash(curl -s http://127.0.0.1:*),Bash(/opt/miniconda3/bin/python3 -I studio.py:*)',
    'compare_engines': ['classic', 'vision'],
}


def settings():
    p = os.path.join(DATA, 'settings.json')
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(p):
        try:
            s.update(json.load(open(p)))
        except ValueError:
            pass
    return s


def save_settings(new):
    s = settings()
    s.update({k: v for k, v in new.items() if k in DEFAULT_SETTINGS})
    p = os.path.join(DATA, 'settings.json')
    with open(p + '.part', 'w') as f:
        json.dump(s, f, indent=1)
    os.replace(p + '.part', p)
    return s


def batch_of(rel):
    parts = rel.split('/')
    if len(parts) >= 3 and parts[0] == 'originals':
        return parts[1]
    return sc.split_name(sc.clean_stem(os.path.splitext(parts[-1])[0]))[0]


def out_names(rel, st=None):
    st = st or load_state(rel)
    s = settings()
    on = [x for x in st['sheets'] if x.get('on', True)]
    stem = sc.clean_stem(os.path.splitext(os.path.basename(rel))[0])
    batch = batch_of(rel)
    root = s['batch_folders'].get(batch) or s['out_root']
    root = root if os.path.isabs(os.path.expanduser(root)) else os.path.join(ROOT, root)
    names = []
    for j, x in enumerate(on):
        letter = '' if len(on) == 1 else 'abcdefghijklmnopqrstuvwxyz'[j % 26]
        tok = {'batch': batch, 'stem': stem, 'letter': letter, 'sheet': (' ' + letter) if letter else '',
               'n': j + 1, 'date': time.strftime('%Y-%m-%d'), 'engine': x.get('engine') or 'manual',
               'label': x.get('label') or letter}
        name = s['template'].format(**tok).strip().strip('/')
        name = '/'.join(sc.clean_stem(p) for p in name.split('/') if p and p not in ('.', '..'))
        names.append((x['id'], os.path.join(os.path.expanduser(root), name + '.png')))
    return names


# ---------------------------------------------------------------- esportazione

class Busy(Exception):
    pass


def agent_lock(timeout=30):
    # lo stesso lucchetto dell'agente: un giro alla volta su cut/ e done.tsv
    f = open(os.path.join(ROOT, '.scancut', 'lock'), 'w')
    t0 = time.time()
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            if time.time() - t0 > timeout:
                f.close()
                raise Busy('the scan agent is running, try again in a moment')
            time.sleep(0.5)


def export(rel, replace=True, log=print):
    # scrive i ritagli; un ritaglio vecchio con lo stesso nome non si sovrascrive:
    # se identico resta, se diverso va in studio-data/replaced/<data>/ (o, senza
    # replace, il nuovo prende " (2)")
    st = load_state(rel)
    rgb, icc, dpi, ppm = image(rel)
    sheets = {x['id']: x for x in st['sheets']}
    written = []
    lock = agent_lock()
    try:
        stamp = time.strftime('%Y%m%d-%H%M%S')
        for sid, out in out_names(rel, st):
            res = cut_sheet(rel, sheets[sid])
            if res is None:
                continue
            rgba, ang, rect = res
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if sc.same_png(out, rgba):
                written.append({'id': sid, 'path': out, 'status': 'identical'}); continue
            moved = None
            if os.path.exists(out) and replace:
                moved = os.path.join(DATA, 'replaced', stamp, os.path.relpath(out, ROOT) if out.startswith(ROOT) else os.path.basename(out))
                os.makedirs(os.path.dirname(moved), exist_ok=True)
                moved = sc.unique(moved)
                os.rename(out, moved)
            out = sc.unique(out)
            kw = {'dpi': (dpi, dpi)}
            if icc: kw['icc_profile'] = icc
            Image.fromarray(rgba, 'RGBA').save(out + '.part', 'PNG', compress_level=4, **kw)
            os.replace(out + '.part', out)
            written.append({'id': sid, 'path': out, 'status': 'written', 'size': list(rgba.shape[1::-1]),
                            'tilt': round(ang, 2), 'rect': round(rect, 3), 'moved_old': moved})
            sc.log(f'studio: {os.path.relpath(out, ROOT)}  {rgba.shape[1]}x{rgba.shape[0]}  tilt {ang:+.2f}'
                   + (f'  (old one moved to {os.path.relpath(moved, ROOT)})' if moved else ''))
        # l'agente non deve rifarla: la scansione e' fatta
        if rel.startswith('originals/') and written:
            sc.mark_done(rel[len('originals/'):], 'studio')
    finally:
        lock.close()
    st['exported'] = time.time()
    save_state(st)
    if settings().get('eagle'):
        eagle_add([w['path'] for w in written if w['status'] == 'written'], log)
    return written


def eagle_add(paths, log=print):
    # Eagle ascolta in locale sulla porta 41595
    import urllib.request
    if not paths:
        return
    s = settings()
    body = {'items': [{'path': p, 'name': os.path.splitext(os.path.basename(p))[0]} for p in paths]}
    if s.get('eagle_folder'):
        body['folderId'] = s['eagle_folder']
    try:
        req = urllib.request.Request('http://localhost:41595/api/item/addFromPaths',
                                     json.dumps(body).encode(), {'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        log(f'Eagle: not reached ({e})')
