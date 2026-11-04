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
SAM3_WEIGHTS = os.path.expanduser('~/sam3.pt')   # letto da Ultralytics cosi' com'e'

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
        if os.path.isdir(p) and not f.startswith('.'):
            out.append({'rel': relpath(p), 'name': f, 'dir': True,
                        'count': sum(1 for g in os.listdir(p) if is_image(g))})
            continue
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
        p = abspath(rel)
        im = Image.open(p)
        a = None
        if im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info:
            a = np.asarray(im.convert('RGBA'))[..., 3].copy()
            if a.min() == 255:
                a = None
        # un ritaglio non e' largo come il letto dello scanner: la misura viene dal suo dpi
        d = (im.info.get('dpi') or (0, 0))[0] or 0
        known = d / 25.4 if d and (a is not None or is_recut(rel)) else None
        rgb, icc, dpi, ppm = sc.load(p, known)
        if len(_img_cache) >= 2:
            k0 = next(iter(_img_cache))
            _img_cache.pop(k0); _alpha.pop(k0, None)
        _img_cache[k] = (rgb, icc, dpi, ppm)
        _alpha[k] = a
        return _img_cache[k]


_alpha = {}


def alpha(rel):
    # la trasparenza che il file ha gia' (None per una scansione)
    image(rel)
    return _alpha.get(file_key(rel))


def is_recut(rel):
    # si ritaglia un ritaglio (cut/ o la cartella d'uscita): i pezzi nuovi gli vanno accanto
    out = settings()['out_root']
    out = out if os.path.isabs(os.path.expanduser(out)) else os.path.join(ROOT, out)
    p = abspath(rel)
    roots = [os.path.realpath(os.path.expanduser(out))] + [os.path.realpath(os.path.expanduser(v)) for v in settings()['batch_folders'].values()]
    return rel.startswith('cut/') or any(p.startswith(r + os.sep) for r in roots)


def fill_colour(rel):
    # il fondo finto per i motori, ben diverso dalla carta: cartoncino grigio dietro la
    # carta chiara (come consiglia scancut), coperchio bianco dietro quella scura
    rgb = image(rel)[0]
    a = alpha(rel)
    px = rgb[a > 128] if a is not None else rgb[rgb.shape[0] // 4: -rgb.shape[0] // 4, rgb.shape[1] // 4: -rgb.shape[1] // 4].reshape(-1, 3)
    L = np.median(px[::97].mean(1)) if len(px) else 255
    return (128, 128, 126) if L > 160 else (247, 247, 246)


def detect_rgb(rel):
    # per i motori: le zone gia' trasparenti diventano fondo (solo per cercare i bordi)
    rgb = image(rel)[0]
    a = alpha(rel)
    if a is None:
        return rgb
    f = a[..., None].astype(np.float32) / 255
    return (rgb * f + np.array(fill_colour(rel), np.float32) * (1 - f)).round().astype(np.uint8)


def has_alpha(rel):
    im = Image.open(abspath(rel))
    return im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info


def preview_path(rel, size):
    # anteprime: JPEG per le scansioni, PNG con la trasparenza per i ritagli
    alpha_ = has_alpha(rel)
    p = os.path.join(DATA, 'previews', f'{file_key(rel)}-{size}.' + ('png' if alpha_ else 'jpg'))
    if not os.path.exists(p):
        im = Image.open(abspath(rel))
        if alpha_:
            im = im.convert('RGBA')
        else:
            im.draft('RGB', (size, size))
            im = im.convert('RGB')
        im.thumbnail((size, size), Image.LANCZOS)
        tmp = p + '.part'
        im.save(tmp, 'PNG' if alpha_ else 'JPEG', **({'compress_level': 3} if alpha_ else {'quality': 88}))
        os.replace(tmp, p)
    return p


def info(rel):
    rgb, icc, dpi, ppm = image(rel)
    h, w = rgb.shape[:2]
    return {'rel': rel, 'w': w, 'h': h, 'dpi': round(dpi), 'ppm': ppm, 'alpha': alpha(rel) is not None,
            'mm': [round(w / ppm), round(h / ppm)], 'name': os.path.basename(rel)}


def tile(rel, x, y, w, h, out_w):
    rgb = image(rel)[0]
    H, W = rgb.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x + w)), min(H, int(y + h))
    crop = rgb[y0:y1, x0:x1]
    a = alpha(rel)
    if a is not None:
        crop = np.dstack([crop, a[y0:y1, x0:x1]])      # i ritagli: la trasparenza resta
    if crop.size == 0:
        crop = np.zeros((1, 1, 3), np.uint8)
    out_w = max(1, min(int(out_w), crop.shape[1] * 4))
    out_h = max(1, round(crop.shape[0] * out_w / max(crop.shape[1], 1)))
    interp = cv2.INTER_AREA if out_w < crop.shape[1] else cv2.INTER_NEAREST
    crop = cv2.resize(crop, (out_w, out_h), interpolation=interp)
    return crop, (x0, y0, x1, y1)


# ---------------------------------------------------------------- motori

# tolleranza del taglio automatico: 1 = quella che sceglie da solo (ritagli identici all'agente)
TOL_PARAM = {'id': 'tol', 'label': 'Tolerance ×', 'type': 'number', 'default': 1.0, 'step': 0.05,
             'hint': 'How different from the lid a pixel must be to count as paper. 1 = what the automatic cut '
                     'picks by itself (cutouts identical to the agent\'s). Higher (1.2-1.5) takes away more lid '
                     'and shadow but can nibble pale paper edges; lower (0.7-0.9) keeps faint edges but may keep '
                     'some lid.'}

# frasi per SAM 3, scelte provandone 16 su scansioni vere e di prova (4 nov 2026):
# quanto la sagoma trovata coincide con la carta vera, quanto SAM e' sicuro, quanti oggetti sbagliati
SAM_PROMPTS = [
    {'text': 'sheet of paper', 'note': 'Default. Loose sheets on the lid or on grey card; solid on every test (overlap 0.81-0.98), no wrong objects.'},
    {'text': 'sketchbook page', 'note': 'The sharpest on loose sheets too (overlap 0.96-0.99) and very sure on sketchbooks; sometimes adds a strip of the spiral.'},
    {'text': 'piece of paper', 'note': 'Like "sheet of paper"; more confident on a single sheet on the white lid.'},
    {'text': 'page', 'note': 'A page of a bound book or sketchbook (0.90 on the spiral sketchbook). Finds nothing on loose sheets.'},
    {'text': 'spiral bound notebook', 'note': 'Spiral sketchbooks and notebooks: the best fit on yours (overlap 0.97, 97% sure).'},
    {'text': 'ring notebook', 'note': 'Ring-bound notebooks; almost as good as "spiral bound notebook" (0.95).'},
    {'text': 'drawing', 'note': 'The artwork itself, not the paper: for cutting a drawing out of its page. May split it in parts.'},
]


ISO = {'A3': (297, 420), 'A4': (210, 297), 'A5': (148, 210), 'A6': (105, 148), 'A7': (74, 105),
       'Letter': (215.9, 279.4), '10 x 15 cm': (100, 150), '13 x 18 cm': (130, 180)}


def corner_masks(shape, ppm, params):
    # il foglio messo nell'angolo del letto: un rettangolo del formato scelto, da quell'angolo
    H, W = shape
    w_mm, h_mm = ISO.get(params.get('format', 'A5'), ISO['A5'])
    if params.get('orientation', 'portrait') == 'landscape':
        w_mm, h_mm = h_mm, w_mm
    w, h = min(W, int(round(w_mm * ppm))), min(H, int(round(h_mm * ppm)))
    c = params.get('corner', 'bottom-left')
    x0 = 0 if 'left' in c else W - w
    y0 = H - h if 'bottom' in c else 0
    m = np.zeros((h, w), bool); m[:] = True
    return [(y0, x0, m, np.zeros_like(m), True)]


def engines():
    out = [
        {'id': 'auto', 'name': 'Automatic (as the agent)', 'kind': 'builtin', 'available': True,
         'note': 'Classic cut; Apple Vision too when the paper is close to the lid colour.', 'params': [TOL_PARAM]},
        {'id': 'classic', 'name': 'Classic auto-cut (lid colour)', 'kind': 'builtin', 'available': True,
         'note': 'Finds the lid colour and removes it from the outside in, then the shadow. Keeps fibres and tears. Without the Apple Vision fallback.', 'params': [TOL_PARAM]},
        {'id': 'otsu', 'name': 'Otsu threshold', 'kind': 'builtin', 'available': True,
         'note': 'Splits light from dark at the best cut-off. Fast and solid when paper and lid differ in lightness, either way round (open lid, grey card).',
         'params': [
             {'id': 'polarity', 'label': 'Paper is', 'type': 'choice', 'default': 'auto',
              'choices': [{'text': 'auto', 'note': 'Decided from the border of the scan (it is lid).'},
                          {'text': 'lighter', 'note': 'Light paper on a dark lid or grey card.'},
                          {'text': 'darker', 'note': 'Dark or coloured paper on the white lid.'}],
              'hint': 'Whether the paper is lighter or darker than what is around it. Auto looks at the border of the scan, which is always lid or card.'},
             {'id': 'refine', 'label': 'Edge from real pixels', 'type': 'bool', 'default': True,
              'hint': 'Otsu puts the edge where the lightness crosses one value on a slightly blurred copy. With this on, the final edge is taken again from your scan: a magic wand against the lid right next to each point, within 2 mm. Sharper along soft shadows, keeps fibres.'}]},
        {'id': 'corner', 'name': 'Format from a corner', 'kind': 'builtin', 'available': True,
         'note': 'No detection: an exact A4, A5, A6 or A7 rectangle from the corner where you put the sheet. Instant, works in batch.',
         'params': [
             {'id': 'format', 'label': 'Format', 'type': 'choice', 'default': 'A5',
              'choices': [{'text': k, 'note': f'{v[0]:g} × {v[1]:g} mm'} for k, v in ISO.items()],
              'hint': 'The paper size. The cut is exactly this size, measured from the corner, using the scan resolution.'},
             {'id': 'orientation', 'label': 'Orientation', 'type': 'choice', 'default': 'portrait',
              'choices': [{'text': 'portrait', 'note': 'Taller than wide.'}, {'text': 'landscape', 'note': 'Wider than tall.'}],
              'hint': 'How the sheet lies on the scanner bed.'},
             {'id': 'corner', 'label': 'Corner', 'type': 'choice', 'default': 'bottom-left',
              'choices': [{'text': c, 'note': f'The sheet is pushed into the {c} corner of the scan.'} for c in ('bottom-left', 'top-left', 'bottom-right', 'top-right')],
              'hint': 'The corner of the scan (as you see it on screen) where the sheet sits.'}]},
        {'id': 'vision', 'name': 'Apple Vision', 'kind': 'ai', 'available': os.path.exists(sc.VISION),
         'note': 'Foreground instances from macOS. Smooth edges; for white on white.'},
        {'id': 'sam3', 'name': 'SAM 3 (Meta)', 'kind': 'ai', 'available': os.path.exists(SAM3_WEIGHTS),
         'note': 'Finds what the prompt names. Runs on the Apple GPU via Ultralytics.', 'params': [
             {'id': 'prompt', 'label': 'Prompt', 'type': 'text', 'default': 'sheet of paper', 'choices': SAM_PROMPTS,
              'hint': 'A short English noun phrase naming what to cut out. SAM 3 finds every object that matches. '
                      'The list holds the phrases that worked best on your kind of scans; you can type any other.'},
             {'id': 'threshold', 'label': 'Score', 'type': 'number', 'default': 0.4, 'step': 0.05,
              'hint': 'How sure SAM 3 must be (0 to 1) before it keeps an object. 0.4 is a good start. Lower '
                      '(0.2-0.3) finds faint or unusual sheets but also wrong things; higher (0.6+) keeps only '
                      'obvious ones. It never changes the edge, only which objects are kept.'},
             {'id': 'hires', 'label': 'Second pass', 'type': 'bool', 'default': True,
              'hint': 'SAM 3 looks at the scan at about 1008 px, so a 600 dpi edge is seen 7x too small. With this '
                      'on, it runs again on a crop around each object and sees the edge much closer. Costs about '
                      '1-2 s per sheet.'},
             {'id': 'refine', 'label': 'Edge from real pixels', 'type': 'bool', 'default': True,
              'hint': 'SAM decides what the object is; the final edge is then taken from your scan: a magic wand '
                      'against the lid right next to each point (works with an open lid too), only within 2 mm of '
                      'SAM\'s edge. Fibres and tears stay. Turn off only to see SAM\'s raw mask.'}]},
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
                # le impostazioni dello script (PARAMS = [...]) lette come dati, senza eseguirlo
                import ast
                for node in ast.parse(src).body:
                    if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == 'PARAMS' for t in node.targets):
                        meta['params'] = ast.literal_eval(node.value)
            except (OSError, SyntaxError, ValueError):
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
    work = detect_rgb(rel)
    copy = bool(box) or alpha(rel) is not None or is_recut(rel)
    if copy:
        # una copia su cui lavorare: solo il riquadro, e/o con il trasparente fatto bianco
        x0, y0, x1, y1 = [int(v) for v in box] if box else (0, 0, rgb.shape[1], rgb.shape[0])
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(rgb.shape[1], x1), min(rgb.shape[0], y1)
        sub = os.path.join(DATA, 'cache', f'.box-{os.getpid()}-{key}.png')
        piece = work[y0:y1, x0:x1]
        # un ritaglio arriva fino al bordo: intorno si mette 10 mm di fondo (fill_colour),
        # cosi' i motori vedono di nuovo un foglio sul fondo
        pad = int(10 * ppm) if is_recut(rel) else 0
        if pad:
            piece = cv2.copyMakeBorder(piece, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=fill_colour(rel))
        Image.fromarray(piece).save(sub, dpi=(dpi, dpi))
        off = (y0 - pad, x0 - pad)
    _engine_lock.acquire()
    try:
        if engine in ('auto', 'classic'):
            t = float(params.get('tol') or 1.0)
            sheets, *_ = sc.cut_scan(sub, ai=(engine == 'auto'), ppm=ppm if copy else None,
                                     tol=None if abs(t - 1.0) < 1e-6 else t)
            masks = [(y, x, *shape) for y, x, _, _, _, shape in sheets]
        elif engine == 'vision':
            srgb = np.asarray(Image.open(sub).convert('RGB')) if copy else rgb
            masks = [(y, x, *shape) for y, x, _, _, _, shape in sc.cut_scan_ai(sub, srgb, ppm)]
        elif engine == 'sam3':
            masks = sam3_masks(sub, ppm, params, whole=bool(box), off=off)
        elif engine == 'corner':
            masks = corner_masks(rgb.shape[:2], ppm, params)
            off = (0, 0)
        elif engine == 'otsu':
            from . import otsu
            srgb = np.asarray(Image.open(sub).convert('RGB')) if copy else rgb
            masks = []
            for m in otsu.segment(srgb, ppm, params):
                if params.get('refine', True):
                    m = refine_with_wand(srgb, m, ppm)
                masks.extend(_crop_mask(m, np.zeros_like(m), ppm))
        elif engine.startswith('script:'):
            masks = script_masks(engine[7:], sub, ppm, params)
        else:
            raise ValueError(f'unknown engine {engine}')
    finally:
        _engine_lock.release()
        if copy and os.path.exists(sub):
            os.remove(sub)
    masks = [_clip(y + off[0], x + off[1], m, h, e, rgb.shape[:2]) for y, x, m, h, e in masks]
    masks = [m for m in masks if m is not None]
    save_cache(key, _sheets_from_masks(masks, ppm), {'engine': engine, 'params': params, 'box': box,
                                                      'seconds': round(time.time() - t0, 1)})
    return key


def _clip(y, x, m, h, e, shape):
    # una sagoma che esce dall'immagine (il margine aggiunto) si taglia ai bordi
    H, W = shape
    a, b = max(0, -y), max(0, -x)
    c, d = min(m.shape[0], H - y), min(m.shape[1], W - x)
    if c <= a or d <= b:
        return None
    return (y + a, x + b, m[a:c, b:d], h[a:c, b:d], e)


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
_sam_used = 0.0
SAM_IDLE_S = 600          # dopo 10 minuti senza richieste il modello si scarica (3.4 GB)


def sam3_unload():
    global _sam
    with _lock:
        if _sam is not None and _sam.poll() is None:
            _sam.stdin.close()
            try:
                _sam.wait(10)
            except subprocess.TimeoutExpired:
                _sam.kill()
        _sam = None


def _sam_watch():
    while True:
        time.sleep(30)
        if _sam is not None and _sam.poll() is None and time.time() - _sam_used > SAM_IDLE_S:
            sam3_unload()


threading.Thread(target=_sam_watch, daemon=True).start()


def sam3_proc():
    # parte solo alla prima richiesta SAM, non all'avvio
    global _sam, _sam_used
    _sam_used = time.time()
    if _sam is None or _sam.poll() is not None:
        _sam = subprocess.Popen([sys.executable, '-I', os.path.join(REPO, 'studio', 'sam3_worker.py'), SAM3_WEIGHTS],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    return _sam


def sam3_call(req):
    # una richiesta al processo SAM; le maschere tornano (n, H, W) alla risoluzione dell'immagine
    global _sam_used
    out = os.path.join(DATA, 'cache', f'.sam-{os.getpid()}-{threading.get_ident()}.npz')
    req = dict(req, out=out)
    with _lock:
        p = sam3_proc()
        p.stdin.write(json.dumps(req) + '\n'); p.stdin.flush()
        line = p.stdout.readline()
    _sam_used = time.time()
    if not line:
        raise RuntimeError('SAM 3 worker stopped (see errors in the terminal)')
    res = json.loads(line)
    if 'error' in res:
        raise RuntimeError('SAM 3: ' + res['error'])
    z = np.load(out)
    masks = z['masks']
    os.remove(out)
    return masks, res.get('scores', [])


def sam3_masks(path, ppm, params, whole=False, off=(0, 0)):
    # 1) SAM sull'immagine intera: testo, oppure clic +/- e riquadro (params mode='prompt').
    # 2) per ogni oggetto, di nuovo su un ritaglio intorno: SAM lavora a ~1008 px, sul
    #    ritaglio vede il bordo molto piu' da vicino.
    # 3) il bordo finale lo decidono i pixel veri (bacchetta sul fondo locale, entro 2 mm).
    rgb = np.asarray(Image.open(path).convert('RGB'))
    H, W = rgb.shape[:2]
    oy, ox = off
    full, scores = sam3_call({'mode': 'text', 'image': path, 'prompt': params.get('prompt') or 'sheet of paper',
                              'threshold': float(params.get('threshold', 0.4)), 'whole': whole})
    if params.get('points'):
        # clic: + tiene l'oggetto sotto il clic, - lo esclude. (I clic "interattivi" di SAM 3 in
        # Ultralytics su queste scansioni si spandono su tutto il letto: si usa la ricerca per testo,
        # che e' il suo punto forte, e il clic sceglie fra gli oggetti trovati)
        pts = [(int(x - ox), int(y - oy), l) for (x, y), l in zip(params['points'], params.get('labels') or [1] * len(params['points']))]
        def piece(m, x, y):
            if not (0 <= x < W and 0 <= y < H) or not m[y, x]:
                return None
            n, lab_, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
            return lab_ == lab_[y, x]
        keep = []
        for m in full:
            pos = [piece(m, x, y) for x, y, l in pts if l == 1]
            pos = [q for q in pos if q is not None]
            if pos and not any(m[y, x] for x, y, l in pts if l == 0 and 0 <= x < W and 0 <= y < H):
                keep.append(np.logical_or.reduce(pos))
        # piu' oggetti sotto lo stesso clic (uno dentro l'altro): il piu' piccolo
        full = sorted(keep, key=lambda m: m.sum())[:1]
    masks = []
    for m in full:
        if not m.any():
            continue
        if params.get('hires', True):
            m = sam3_second_pass(path, rgb, m, ppm, params)
        if params.get('refine', True):
            m = refine_with_wand(rgb, m, ppm)
        masks.extend(_crop_mask(m, np.zeros_like(m), ppm))
    return masks


def sam3_second_pass(path, rgb, m, ppm, params):
    H, W = rgb.shape[:2]
    ys, xs = np.nonzero(m)
    mg = int(8 * ppm)
    x0, y0, x1, y1 = max(0, xs.min() - mg), max(0, ys.min() - mg), min(W, xs.max() + mg + 1), min(H, ys.max() + mg + 1)
    if (x1 - x0) * (y1 - y0) > 0.8 * W * H:
        return m                                   # gia' quasi tutta l'immagine: niente da guadagnare
    crop = os.path.join(DATA, 'cache', f'.samcrop-{os.getpid()}-{threading.get_ident()}.png')
    Image.fromarray(rgb[y0:y1, x0:x1]).save(crop)
    try:
        # la stessa frase sul ritaglio; si tiene l'oggetto che coincide di piu' con il primo
        sub, _ = sam3_call({'mode': 'text', 'image': crop, 'prompt': params.get('prompt') or 'sheet of paper',
                            'threshold': float(params.get('threshold', 0.4))})
    finally:
        os.remove(crop)
    if not len(sub):
        return m
    mc = m[y0:y1, x0:x1]
    best = max(sub, key=lambda q: (q & mc).sum() / max((q | mc).sum(), 1))
    if not best.any():
        return m
    out = np.zeros_like(m)
    out[y0:y1, x0:x1] = best
    # se la seconda passata cambia di molto la forma, si tiene la prima
    inter = (out & m).sum() / max((out | m).sum(), 1)
    return out if inter > 0.9 else m


def local_background(lab, m, ppm):
    # il fondo vicino al foglio: l'anello fra 1.5 e 5 mm fuori dalla sagoma, sfocato, e per
    # ogni pixel il colore del punto d'anello piu' vicino (coperchio aperto: il fondo sfuma)
    outer = cv2.dilate(m.astype(np.uint8), sc.disk(5 * ppm)).astype(bool)
    inner = cv2.dilate(m.astype(np.uint8), sc.disk(1.5 * ppm)).astype(bool)
    ring = outer & ~inner
    if ring.sum() < 100:
        return None, None
    _, lbl = cv2.distanceTransformWithLabels((~ring).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ry, rx = np.nonzero(ring)
    # le etichette dei pixel d'anello seguono l'ordine di scansione (riga per riga)
    order = np.zeros(lbl.max() + 1, np.int64)
    order[lbl[ry, rx]] = np.arange(len(ry))
    smooth = cv2.blur(lab, (sc.odd(2 * ppm), sc.odd(2 * ppm)))
    field = smooth[ry, rx][order[lbl]]
    spread = np.linalg.norm((lab[ry, rx] - smooth[ry, rx]) * sc.W_LAB, axis=1)
    return field, max(7.0, 1.5 * np.percentile(spread, 90) + 2)


def refine_with_wand(rgb, m, ppm):
    # SAM da' la zona giusta; il bordo vero si prende dalla bacchetta, solo entro 2 mm dal
    # bordo di SAM, contro il fondo di quel punto (non un colore solo per tutta la scansione)
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (3, 3), 0), cv2.COLOR_RGB2LAB).astype(np.float32)
    field, T = local_background(lab, m, ppm)
    if field is None:
        return m
    d = np.linalg.norm((lab - field) * sc.W_LAB, axis=2)
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
    return keep if 0.9 < keep.sum() / max(m.sum(), 1) < 1.1 else m


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
        # niente si butta: lo stato di prima va nella storia (le ultime 15), e i fogli fatti a
        # mano (poligono, lazo, bacchetta, uniti) restano anche dopo un nuovo rilevamento
        if st['sheets']:
            hist = st.setdefault('history', [])
            hist.insert(0, {'time': time.time(), 'engine': st.get('engine'), 'sheets': st['sheets']})
            del hist[15:]
        st['sheets'] = [x for x in st['sheets'] if not x.get('src')]
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
        if o.get('kind') == 'sheets':
            # fogli uniti: ogni pezzo con la sua sagoma (e i suoi buchi), come prima dell'unione
            R = np.zeros(shape, bool)
            for i, sub in enumerate(o['sheets']):
                sy, sx, SM, SH, se = sheet_mask(rel, sub)
                a0, b0 = max(bx0, sx), max(by0, sy)
                a1, b1 = min(bx1, sx + SM.shape[1]), min(by1, sy + SM.shape[0])
                if a1 > a0 and b1 > b0:
                    R[b0 - by0:b1 - by0, a0 - bx0:a1 - bx0] |= SM[b0 - sy:b1 - sy, a0 - sx:a1 - sx]
                    Hh[b0 - by0:b1 - by0, a0 - bx0:a1 - bx0] |= SH[b0 - sy:b1 - sy, a0 - sx:a1 - sx]
                if i == 0:
                    exact = se
        elif o.get('kind') == 'wand':
            R = wand_region(rel, o['seed'], o['tol'], o.get('contig', True))[by0:by1, bx0:bx1]
        else:
            R = _raster(o['pts'], shape, off, o.get('kind', 'poly'), o.get('r', 0))
        M = M | R if o['op'] == 'add' else (M & R) if o['op'] == 'int' else M & ~R
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


# ---------------------------------------------------------------- strumenti di misura

_bg_cache = {}


def bg_model(rel):
    # il fondo come lo vede la bacchetta del taglio (copia sfocata 3x3)
    k = file_key(rel)
    if k not in _bg_cache:
        lab = cv2.cvtColor(cv2.GaussianBlur(detect_rgb(rel), (3, 3), 0), cv2.COLOR_RGB2LAB).astype(np.float32)
        col, T = sc.background(lab)
        if len(_bg_cache) > 4:
            _bg_cache.pop(next(iter(_bg_cache)))
        _bg_cache[k] = (lab, col, T)
    return _bg_cache[k]


def lab_real(v):
    # Lab di OpenCV a 8 bit (0-255) -> L* 0-100, a* b* intorno a 0
    return [round(float(v[0]) * 100 / 255, 1), round(float(v[1]) - 128, 1), round(float(v[2]) - 128, 1)]


def pixel(rel, x, y, r=0):
    rgb = image(rel)[0]
    H, W = rgb.shape[:2]
    x, y = int(x), int(y)
    if not (0 <= x < W and 0 <= y < H):
        return None
    sl = np.s_[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
    lab, col, T = bg_model(rel)
    v = rgb[sl].reshape(-1, 3).mean(0)
    lv = cv2.cvtColor(rgb[sl], cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32).mean(0)
    d = float(np.linalg.norm((lab[sl].reshape(-1, 3).mean(0) - col) * sc.W_LAB))
    a = alpha(rel)
    return {'x': x, 'y': y, 'r': r, 'rgb': [round(float(c), 1) for c in v], 'lab': lab_real(lv),
            'bg_lab': lab_real(col), 'bg_dist': round(d, 1), 'bg_tol': round(float(T), 1), 'is_bg': d < T,
            'alpha': None if a is None else int(a[y, x])}


def histogram(rel, sheet=None):
    rgb = image(rel)[0]
    sel = None
    if sheet:
        y0, x0, M, _, _ = sheet_mask_cached(rel, sheet)
        sel = (np.s_[y0:y0 + M.shape[0], x0:x0 + M.shape[1]], M)
    px = rgb[sel[0]][sel[1]] if sel else rgb.reshape(-1, 3)
    a = alpha(rel)
    if a is not None and not sel:
        px = px[a.reshape(-1) > 0]
    L = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB)[:, 0, 0]
    out = {c: np.bincount(px[:, i], minlength=256).tolist() for i, c in enumerate('rgb')}
    out['l'] = np.bincount(L, minlength=256).tolist()
    _, col, T = bg_model(rel)
    out['bg_l'] = float(col[0])
    out['n'] = int(len(px))
    return out


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
    a = alpha(rel)
    if a is not None:
        # la trasparenza che il file aveva resta: stessa sagoma, stesso raddrizzo, stesso
        # taglio applicati al suo canale alfa, e vale il piu' trasparente dei due
        ac = np.repeat(a[y0:y0 + M.shape[0], x0:x0 + M.shape[1], None], 3, 2)
        old = sc.cutout(ac, M, Hh, ppm, exact=exact)[0][..., 0]
        rgba[..., 3] = np.minimum(rgba[..., 3], old)
        rgba[rgba[..., 3] == 0, :3] = 0
    q = (int(sheet.get('rot', 0)) // 90) % 4          # gradi in senso orario, a passi di 90: senza perdita
    if q:
        rgba = np.ascontiguousarray(np.rot90(rgba, k=-q))
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
    'scan_device': '', 'scan_res': 600, 'scan_mode': 'Color', 'scan_batch': 'scan',
    'export_format': 'png',            # png | jxl (JPEG XL senza perdita, con la trasparenza)
    'export_existing': 'new_copy',     # new_copy: un ritaglio diverso col nome gia' preso diventa "(2)"; replace: il vecchio in replaced/
    'export_subfolder': 'extra',       # "Export to subfolder": i ritagli in <cartella>/<questo>/
    'frame_sets': {},                  # nome -> [[sinistra, alto, larghezza, altezza] mm, ...]
}


def autocut():
    return not os.path.exists(os.path.join(ROOT, '.scancut', 'autocut-off'))


def set_autocut(on):
    f = os.path.join(ROOT, '.scancut', 'autocut-off')
    if on and os.path.exists(f):
        os.remove(f)
    elif not on:
        open(f, 'w').write('the agent files new scans into originals/ but does not cut them (Scan Studio > Settings)\n')


def settings():
    p = os.path.join(DATA, 'settings.json')
    s = dict(DEFAULT_SETTINGS)
    s['autocut'] = autocut()
    if os.path.exists(p):
        try:
            s.update(json.load(open(p)))
        except ValueError:
            pass
    return s


def save_settings(new):
    s = settings()
    if 'autocut' in new:
        set_autocut(bool(new['autocut']))
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


def recut_folder(rel):
    p = abspath(rel)
    stem = os.path.splitext(os.path.basename(p))[0]
    d = os.path.dirname(p)
    return d if os.path.basename(d) == stem else os.path.join(d, stem)


def out_names(rel, st=None):
    st = st or load_state(rel)
    s = settings()
    on = [x for x in st['sheets'] if x.get('on', True)]
    stem = sc.clean_stem(os.path.splitext(os.path.basename(rel))[0])
    if is_recut(rel):
        # "sketchbook 3 a.png" -> sketchbook 3 a/sketchbook 3 a.png (com'era) + sketchbook 3 a a.png, b.png ...
        d = recut_folder(rel)
        ext = '.jxl' if s.get('export_format') == 'jxl' else '.png'
        return [(x['id'], os.path.join(d, f'{stem} {"abcdefghijklmnopqrstuvwxyz"[j % 26]}'
                                          + (f' {sc.clean_stem(x["label"])}' if x.get('label') else '') + ext))
                for j, x in enumerate(on)]
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
    return [(i, os.path.splitext(n)[0] + '.jxl') for i, n in names] if s.get('export_format') == 'jxl' else names


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


def write_cutout(rgba, out, fmt, dpi, icc):
    # PNG, o JPEG XL senza perdita (cjxl -d 0, con la trasparenza). Il JXL si rilegge e si
    # confronta pixel per pixel: se non e' identico, si tiene il PNG
    kw = {'dpi': (dpi, dpi)}
    if icc:
        kw['icc_profile'] = icc
    if fmt == 'jxl' and shutil.which('cjxl'):
        png = out + '.src.png'
        Image.fromarray(rgba, 'RGBA').save(png, 'PNG', compress_level=1, **kw)
        try:
            subprocess.run(['cjxl', png, out + '.part', '-d', '0', '-e', '7', '--quiet'], check=True, capture_output=True, timeout=600)
            back = out + '.check.png'
            subprocess.run(['djxl', out + '.part', back, '--quiet'], check=True, capture_output=True, timeout=600)
            same = np.array_equal(np.asarray(Image.open(back).convert('RGBA')), rgba)
            os.remove(back)
            if not same:
                raise RuntimeError('JPEG XL round trip differs')
            os.replace(out + '.part', out)
            return out
        except Exception:
            for f in (out + '.part',):
                if os.path.exists(f):
                    os.remove(f)
            out = os.path.splitext(out)[0] + '.png'
        finally:
            if os.path.exists(png):
                os.remove(png)
    Image.fromarray(rgba, 'RGBA').save(out + '.part', 'PNG', compress_level=4, **kw)
    os.replace(out + '.part', out)
    return out


def same_cutout(path, rgba):
    if not os.path.exists(path):
        return False
    if path.endswith('.jxl'):
        back = path + '.cmp.png'
        try:
            subprocess.run(['djxl', path, back, '--quiet'], check=True, capture_output=True, timeout=600)
            return np.array_equal(np.asarray(Image.open(back).convert('RGBA')), rgba)
        except Exception:
            return False
        finally:
            if os.path.exists(back):
                os.remove(back)
    return sc.same_png(path, rgba)


def export(rel, replace=None, log=print, subfolder=None):
    # scrive i ritagli. Un ritaglio con lo stesso nome non si sovrascrive mai: se identico
    # resta; se diverso, il nuovo prende " (2)" (o, con export_existing=replace, il vecchio
    # va in studio-data/replaced/). subfolder: i ritagli in una sottocartella della loro.
    s_ = settings()
    if replace is None:
        replace = s_.get('export_existing') == 'replace'
    fmt = s_.get('export_format', 'png')
    st = load_state(rel)
    rgb, icc, dpi, ppm = image(rel)
    sheets = {x['id']: x for x in st['sheets']}
    written = []
    recut = is_recut(rel)
    replace = replace and not recut      # accanto a un ritaglio: i pezzi vecchi restano, i nuovi prendono (2)
    lock = agent_lock()
    try:
        stamp = time.strftime('%Y%m%d-%H%M%S')
        for sid, out in out_names(rel, st):
            res = cut_sheet(rel, sheets[sid])
            if res is None:
                continue
            rgba, ang, rect = res
            if subfolder:
                out = os.path.join(os.path.dirname(out), sc.clean_stem(subfolder), os.path.basename(out))
            if fmt == 'jxl':
                out = os.path.splitext(out)[0] + '.jxl'
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if same_cutout(out, rgba):
                written.append({'id': sid, 'path': out, 'status': 'identical'}); continue
            moved = None
            if os.path.exists(out) and replace:
                moved = os.path.join(DATA, 'replaced', stamp, os.path.relpath(out, ROOT) if out.startswith(ROOT) else os.path.basename(out))
                os.makedirs(os.path.dirname(moved), exist_ok=True)
                moved = sc.unique(moved)
                os.rename(out, moved)
            out = write_cutout(rgba, sc.unique(out), fmt, dpi, icc)
            written.append({'id': sid, 'path': out, 'status': 'written', 'size': list(rgba.shape[1::-1]),
                            'tilt': round(ang, 2), 'rect': round(rect, 3), 'moved_old': moved})
            sc.log(f'studio: {os.path.relpath(out, ROOT)}  {rgba.shape[1]}x{rgba.shape[0]}  tilt {ang:+.2f}'
                   + (f'  (old one moved to {os.path.relpath(moved, ROOT)})' if moved else ''))
        # l'agente non deve rifarla: la scansione e' fatta
        if rel.startswith('originals/') and written:
            sc.mark_done(rel[len('originals/'):], 'studio')
        # un ritaglio ritagliato entra nella sua cartella, accanto ai pezzi nuovi (mai cancellato)
        new_rel = None
        if recut and any(w['status'] == 'written' for w in written):
            src = abspath(rel)
            d = recut_folder(rel)
            if os.path.dirname(src) != d:
                dst = sc.unique(os.path.join(d, os.path.basename(src)))
                os.link(src, dst)
                if not os.path.samefile(src, dst):
                    raise IOError('could not move the previous cutout into its folder')
                os.remove(src)
                new_rel = relpath(dst)
                written.append({'id': None, 'path': dst, 'status': 'moved', 'rel': new_rel})
                sc.log(f'studio: {rel} -> {new_rel} (kept, next to its new pieces)')
    finally:
        lock.close()
    st['exported'] = time.time()
    if new_rel:
        # lo stato segue il file
        old = state_path(rel)
        st['rel'] = new_rel
        st['version'] = load_state(new_rel).get('version', 0)
        save_state(st)
        if os.path.exists(old):
            os.remove(old)
    else:
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
