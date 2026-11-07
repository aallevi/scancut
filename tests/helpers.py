# cose comuni alle prove: una radice di prova vuota e scansioni finte, piccole (100 dpi)
# per andare veloci. Mai la radice vera (~/Scans).
import os, sys, shutil, tempfile
import numpy as np, cv2
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import scancut as sc  # noqa: E402

DPI = 100


def scratch_root():
    r = tempfile.mkdtemp(prefix='scancut-test-')
    for d in ('inbox', '.scancut'):
        os.makedirs(os.path.join(r, d))
    return r


def remove_root(r):
    shutil.rmtree(r, ignore_errors=True)


def fake_scan(path, bg=(128, 128, 126), sheets=((0.5, 0.5, 150, 200, 2, (250, 250, 248)),), seed=1, bits=8):
    # un letto A4 con fogli rettangolari (cx, cy in frazioni; w, h in mm; angolo; colore)
    rng = np.random.default_rng(seed)
    W, H = int(216 / 25.4 * DPI), int(297 / 25.4 * DPI)
    im = np.full((H, W, 3), bg, np.float32) + rng.normal(0, 1.5, (H, W, 3))
    for cx, cy, w, h, ang, col in sheets:
        m = np.zeros((H, W), np.uint8)
        box = cv2.boxPoints(((cx * W, cy * H), (w * DPI / 25.4, h * DPI / 25.4), ang)).astype(np.int32)
        cv2.fillPoly(m, [box], 1)
        im[m > 0] = np.array(col, np.float32) + rng.normal(0, 2, ((m > 0).sum(), 3))
        c = box.mean(0).astype(int)
        cv2.line(im, (int(c[0]) - 80, int(c[1]) - 60), (int(c[0]) + 70, int(c[1]) + 90), (60, 60, 70), 3)
    im = np.clip(im, 0, 255)
    if bits == 16:
        a = (im * 257).astype(np.uint16)
        cv2.imwrite(path, cv2.cvtColor(a, cv2.COLOR_RGB2BGR))      # TIFF a 48 bit, come lo scanner
        return path
    if bits == 'gray16':
        cv2.imwrite(path, (im.mean(2) * 257).astype(np.uint16))      # 16 bit grigio
        return path
    Image.fromarray(im.astype(np.uint8)).save(path, dpi=(DPI, DPI))
    return path


def run_agent(root):
    # un giro dell'agente nella radice di prova, senza aspettare i 4 s di file fermo
    sc.set_root(root)
    old = sc.STABLE_S, sc.notify
    sc.STABLE_S, sc.notify = 0, (lambda msg: None)
    try:
        sc.main()
    finally:
        sc.STABLE_S, sc.notify = old


def files(root, top):
    d = os.path.join(root, top)
    return sorted(os.path.relpath(os.path.join(a, f), d) for a, _, fs in os.walk(d) for f in fs)
