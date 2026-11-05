# scansioni dimostrative inventate (per le immagini del README e le prove): fogli con disegni a
# penna fatti di linee di flusso, su cartoncino grigio o sul coperchio bianco. Niente disegni veri.
# uso: cd <cartella>/inbox && python3 -I tools/make_demo_scans.py
import numpy as np, cv2
from PIL import Image

DPI = 300
MM = DPI / 25.4
rng = np.random.default_rng(7)


def bed(colour):
    W, H = int(216 * MM), int(297 * MM)
    im = np.full((H, W, 3), colour, np.float32) + rng.normal(0, 1.6, (H, W, 3))
    return im


def flow_drawing(h, w, seed, ink=(38, 36, 44)):
    # linee di flusso su un campo di seni: sembra un disegno a penna, ma e' tutto calcolato
    r = np.random.default_rng(seed)
    k = r.uniform(0.004, 0.012, 4); ph = r.uniform(0, 6.28, 4)
    layer = np.zeros((h, w), np.float32)
    for _ in range(int(w * h / 9000)):
        x, y = r.uniform(0.12, 0.88) * w, r.uniform(0.12, 0.88) * h
        pts = []
        for _ in range(int(r.integers(40, 260))):
            a = np.sin(x * k[0] + ph[0]) * 2.2 + np.cos(y * k[1] + ph[1]) * 2.2 + np.sin((x + y) * k[2] + ph[2])
            x += np.cos(a) * 3; y += np.sin(a) * 3
            if not (0.08 * w < x < 0.92 * w and 0.08 * h < y < 0.92 * h):
                break
            pts.append((x, y))
        if len(pts) > 8:
            cv2.polylines(layer, [np.int32(np.array(pts) * 4)], False, 1.0, int(r.choice([2, 3, 4, 6])), cv2.LINE_AA, shift=2)
    for _ in range(int(r.integers(3, 7))):              # qualche cerchio pieno di tratteggio
        cx, cy, rad = r.uniform(.25, .75) * w, r.uniform(.25, .75) * h, r.uniform(.04, .1) * w
        cv2.circle(layer, (int(cx), int(cy)), int(rad), 1.0, 3, cv2.LINE_AA)
        for t in np.linspace(-rad, rad, int(rad / 9)):
            d = np.sqrt(max(rad * rad - t * t, 0))
            cv2.line(layer, (int(cx + t), int(cy - d)), (int(cx + t), int(cy + d)), 0.8, 1, cv2.LINE_AA)
    return np.clip(layer, 0, 1)[..., None] * (1 - np.array(ink, np.float32) / 255)


def sheet(im, cx, cy, wmm, hmm, ang, paper, seed, holes=0, ink=(38, 36, 44)):
    H, W = im.shape[:2]
    w, h = int(wmm * MM), int(hmm * MM)
    tex = np.full((h, w, 3), paper, np.float32) + rng.normal(0, 2.2, (h, w, 3))
    tex *= 1 - flow_drawing(h, w, seed, ink) * 0.92
    a = np.full((h, w), 255, np.uint8)
    for i in range(holes):                               # fori del raccoglitore
        cv2.circle(a, (int(12 * MM), int(h / 2 + (i - (holes - 1) / 2) * 80 * MM)), int(3 * MM), 0, -1, cv2.LINE_AA)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1)
    M[:, 2] += (cx * W - w / 2, cy * H - h / 2)
    warped = cv2.warpAffine(tex, M, (W, H), flags=cv2.INTER_LINEAR)
    m = cv2.warpAffine(a, M, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32) / 255
    shadow = cv2.GaussianBlur(cv2.dilate(m, np.ones((7, 7))), (0, 0), 3)
    im *= (1 - 0.18 * shadow * (1 - m))[..., None]
    im[:] = im * (1 - m[..., None]) + warped * m[..., None]


def save(im, name):
    Image.fromarray(np.clip(im, 0, 255).astype(np.uint8)).save(name, dpi=(DPI, DPI))
    print(name)


im = bed((126, 127, 125))
sheet(im, .5, .5, 160, 225, 2.5, (240, 234, 218), 1, holes=2)
save(im, 'sketchbook 1.png')

im = bed((126, 127, 125))
sheet(im, .27, .27, 92, 128, -3, (248, 248, 245), 2)
sheet(im, .73, .28, 90, 125, 1.5, (214, 228, 242), 3, ink=(20, 40, 90))
sheet(im, .5, .74, 150, 105, -1, (244, 226, 205), 4, ink=(90, 30, 25))
save(im, 'studies 1.png')

im = bed((246, 246, 244))
sheet(im, .5, .5, 140, 190, -4, (200, 220, 205), 5, ink=(25, 50, 35))
save(im, 'green 1.png')
