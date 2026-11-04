# scancut: ritaglia i fogli dalle scansioni che arrivano in ~/Scans/inbox
#
# inbox/sketchbook 3.png  ->  originals/sketchbook/sketchbook 3.png (spostata, l'inbox resta vuota)
#                     ->  cut/sketchbook/sketchbook 3 a.png, sketchbook 3 b.png ...
#                     (nessun foglio trovato -> un collegamento in failed/)
# Lo spostamento non sovrascrive mai: se il nome c'e' gia' si prende il numero libero,
# e il file lascia l'inbox solo quando sta al sicuro in originals/.
# Le scansioni gia' ritagliate stanno in .scancut/done.tsv (percorso dentro originals/);
# per rifarne una basta togliere la sua riga da li'.
#
# Il lotto e' il nome dato in Acquisizione Immagine senza il numero finale.
# Il fondo (coperchio bianco o cartoncino grigio) si legge dai bordi della scansione.

import os, re, sys, time, shutil, hashlib, fcntl, subprocess, traceback, warnings
import numpy as np, cv2
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter('ignore', RuntimeWarning)   # nanmedian su tratti vuoti

def set_root(root):
    # la radice si sceglie da riga di comando; lo studio (importandolo) la passa qui
    global ROOT, INBOX, CUT, ORIG, FAIL, DONE, LOG
    ROOT = os.path.expanduser(root)
    INBOX, CUT, ORIG, FAIL = (os.path.join(ROOT, d) for d in ('inbox', 'cut', 'originals', 'failed'))
    DONE = os.path.join(ROOT, '.scancut', 'done.tsv')   # scansioni gia' ritagliate
    LOG = os.path.join(ROOT, '.scancut', 'log.txt')


set_root(sys.argv[1] if __name__ == '__main__' and len(sys.argv) > 1 else '~/Scans')
EXT = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}
WORK = 4.0            # px/mm della copia ridotta su cui si cercano i tagli
STABLE_S = 4          # il file deve stare fermo tanto prima di toccarlo
MAX_RUN_S = 3 * 3600   # niente giri a orario: un lotto grosso va finito nello stesso giro


def log(msg):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + msg
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')


def odd(x):
    x = max(1, int(round(x)))
    return x if x % 2 else x + 1


def edge_dist(M):
    # distanza dal bordo del foglio; anche il bordo dell'immagine conta come bordo
    P = np.pad(M.astype(np.uint8), 1)
    return cv2.distanceTransform(P, cv2.DIST_L2, 5)[1:-1, 1:-1]


def disk(d):
    d = odd(d)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d))


# ---------------------------------------------------------------- lettura

def load(path, ppm_known=None):
    im = Image.open(path)
    icc = im.info.get('icc_profile')
    dpi = im.info.get('dpi', (0, 0))[0] or 0
    if im.mode in ('I;16', 'I;16B', 'I;16L', 'I'):
        # grigio a 16 bit: convert('RGB') di Pillow lo fa tutto bianco; per cercare i bordi
        # basta il byte alto (i pixel dei ritagli a 16 bit li prende lo studio dall'originale)
        g = (np.asarray(im).astype(np.uint32) >> 8).clip(0, 255).astype(np.uint8)
        rgb = np.dstack([g, g, g])
    else:
        rgb = np.asarray(im.convert('RGB'))
    h, w = rgb.shape[:2]
    # il letto di uno scanner A4 e' largo ~216 mm: se il dpi dichiarato
    # non torna con le dimensioni, si ricava da li'
    ppm = dpi / 25.4 if dpi else 0
    if ppm_known:                     # un pezzo della scansione: la misura e' gia' nota
        ppm = ppm_known
    elif not (150 <= w / ppm <= 240 if ppm else False):
        ppm = w / 216.0
    return rgb, icc, dpi or ppm * 25.4, ppm


W_LAB = np.array([1.0, 2.0, 2.0], np.float32)   # la tinta conta piu' della luce: il fondo e' neutro


def background(lab):
    # colore piu' comune fra i pixel poco colorati sul bordo (saltando i 3 px estremi)
    h, w = lab.shape[:2]
    b = 12
    ring = np.concatenate([lab[3:b, 3:w-3].reshape(-1, 3), lab[h-b:h-3, 3:w-3].reshape(-1, 3),
                           lab[3:h-3, 3:b].reshape(-1, 3), lab[3:h-3, w-b:w-3].reshape(-1, 3)])
    chroma = np.hypot(ring[:, 1] - 128, ring[:, 2] - 128)
    grey = ring[chroma < 10]
    if len(grey) < 200:
        grey = ring
    hist = np.bincount((grey[:, 0] // 4).astype(int), minlength=64)
    mode = hist.argmax() * 4 + 2
    near = grey[np.abs(grey[:, 0] - mode) < 8]
    col = np.median(near, axis=0)
    spread = np.percentile(np.linalg.norm((near - col) * W_LAB, axis=1), 90)
    return col, max(7.0, 1.5 * spread + 2)


# ---------------------------------------------------------------- tagli

NSEG = 8


def nanmed(X):
    # come np.nanmedian(X, -1), stessi numeri, ma senza la versione lenta per pochi valori
    S = np.sort(X, -1)                     # i NaN finiscono in fondo
    n = (~np.isnan(X)).sum(-1)
    lo = np.take_along_axis(S, np.maximum((n - 1) // 2, 0)[..., None], -1)[..., 0]
    hi = np.take_along_axis(S, np.maximum(n // 2, 0)[..., None], -1)[..., 0]
    out = np.where(n % 2 == 1, lo, (lo + hi) / X.dtype.type(2))
    return np.where(n > 0, out, X.dtype.type(np.nan))


def profiles(M, G, A, B, Lw, lp, axis):
    # per ogni riga (axis=1) o colonna (axis=0), divisa in NSEG tratti:
    # quanto e' "fessura" e che colore ha la carta in ogni tratto
    if axis == 0:
        M, G, A, B, Lw = M.T, G.T, A.T, B.T, Lw.T
    n, w = M.shape
    cols = np.where(M.any(0))[0]
    x0, x1 = cols[0], cols[-1] + 1
    cw = max(1, (x1 - x0) // NSEG)
    sl = slice(x0, x0 + cw * NSEG)
    seg = lambda X: X[:, sl].reshape(n, NSEG, cw)
    Ms = seg(M)
    clean = Ms & (seg(Lw) > lp - 25)          # niente matita nel colore della carta
    cnt = Ms.sum(2)
    gap = np.where(cnt > 0, (seg(G) * Ms).sum(2) / np.maximum(cnt, 1), np.nan)
    ca = nanmed(np.where(clean, seg(A), np.nan))
    cb = nanmed(np.where(clean, seg(B), np.nan))
    ext = M.sum(1)
    return ext, gap, ca, cb


def best_cut(M, G, A, B, Lw, lp):
    # linee di taglio candidate, la migliore prima: una fessura o un salto di colore
    # che deve esserci in quasi tutti i tratti della linea, non solo in media
    h, w = M.shape
    c = (w / 2.0, h / 2.0)
    m = int(3 * WORK)          # striscia minima 3 mm
    k0, k1 = 3, 10
    found = []
    # fitto vicino al dritto, piu' rado oltre: fino a 8 gradi
    for th in np.r_[np.arange(-8, -3, 1.0), np.arange(-3, 3.01, 0.5), np.arange(4, 8.01, 1.0)]:
        R = cv2.getRotationMatrix2D(c, th, 1.0)
        warp = lambda X, fl=cv2.INTER_LINEAR: cv2.warpAffine(X, R, (w, h), flags=fl, borderValue=0)
        Mr = warp(M.astype(np.uint8), cv2.INTER_NEAREST) > 0
        if Mr.sum() < 0.95 * M.sum():
            continue
        Gr, Ar, Br, Lr = warp(G), warp(A), warp(B), warp(Lw)
        for axis in (1, 0):
            ext, gap, ca, cb = profiles(Mr, Gr, Ar, Br, Lr, lp, axis)
            rows = np.where(ext > 0)[0]
            if len(rows) < 2 * m + 2 * k1 + 2:
                continue
            n = len(ext)
            win = np.lib.stride_tricks.sliding_window_view
            # colore sopra e sotto ogni riga, tratto per tratto
            above = np.full((n, NSEG, 2), np.nan); below = np.full((n, NSEG, 2), np.nan)
            ab = np.stack([ca, cb], 2)
            wv = nanmed(win(ab, k1 - k0, axis=0))        # finestre di righe
            idx = np.arange(n)
            ia, ib = idx - k1, idx + k0
            okr = (ia >= 0) & (ib + (k1 - k0) <= n)
            above[okr] = wv[ia[okr]]; below[okr] = wv[ib[okr]]
            jump = np.linalg.norm(above - below, axis=2)            # (n, NSEG)
            gp = np.fmax(np.fmax(gap, np.roll(gap, 1, 0)), np.roll(gap, -1, 0))
            # una fessura e' una riga piu' "fondo" della carta ai due lati
            gw = nanmed(win(gap, k1 - k0, axis=0))
            ga = np.full_like(gap, np.nan); gb = np.full_like(gap, np.nan)
            ga[okr] = gw[ia[okr]]; gb[okr] = gw[ib[okr]]
            gp = gp - np.fmax(ga, gb)
            ghit = gp >= 0.35
            hit = ghit | (jump >= 7)
            valid = np.isfinite(jump) | np.isfinite(gp)
            nv = valid.sum(1)
            frac = np.where(nv >= NSEG - 2, (hit & valid).sum(1) / np.maximum(nv, 1), 0)
            gfrac = (ghit & valid).sum(1) / np.maximum(nv, 1)
            strength = np.nanmean(np.fmax(np.nan_to_num(gp / 0.35), np.nan_to_num(jump / 7)), 1)
            # la linea deve attraversare tutto il foglio
            loc = nanmed(win(np.pad(ext.astype(float), 25, constant_values=np.nan), 51))
            span = ext >= 0.85 * loc
            lo, hi = rows[0] + m, rows[-1] - m
            for y in np.where((frac >= 0.75) & span)[0]:
                if lo <= y <= hi:
                    found.append((frac[y] + 0.01 * min(strength[y], 10), th, axis, y, (R, axis, y + 0.5), gfrac[y]))
            # collo: due fogli attaccati solo da un ponticello (fessura quasi chiusa in un punto).
            # La riga di carta si stringe a meno di un terzo rispetto ai fogli dei due lati
            k = int(10 * WORK)
            e = ext.astype(float)
            y0, y1 = max(lo, k), min(hi, n - k)
            if y1 < y0:
                continue
            # mediane dei due lati per tutte le righe insieme: e[y-k:y-2] e e[y+3:y+k]
            med_a = np.median(win(e[y0 - k:y1 - 2], k - 2), -1)
            med_b = np.median(win(e[y0 + 3:y1 + k], k - 3), -1)
            for y in range(y0, y1 + 1):
                side_a, side_b = med_a[y - y0], med_b[y - y0]
                if 0 < e[y] < 0.3 * min(side_a, side_b) and e[y] <= e[y - 1] and e[y] <= e[y + 1]:
                    found.append((2.0 - e[y] / min(side_a, side_b), th, axis, y, (R, axis, y + 0.5), 1.0))
    # una sola linea per ogni posto (le altre inclinazioni e le righe vicine sono doppioni)
    found.sort(key=lambda f: -f[0])
    best = []
    for f in found:
        if all(f[2] != b[2] or abs(f[3] - b[3]) > 6 * WORK for b in best):
            best.append(f)
    return [(f[0], f[4], f[5]) for f in best[:8]]


def outline_step(M, R, axis, t):
    # di quanto si sposta il contorno attraversando la linea: due fogli veri
    # quasi mai combaciano al quarto di millimetro, una fascia stampata si'
    h, w = M.shape
    Mr = cv2.warpAffine(M.astype(np.uint8), R, (w, h), flags=cv2.INTER_NEAREST) > 0
    if axis == 0:
        Mr = Mr.T
    y = int(t)
    has = Mr.any(1)
    first = np.where(has, Mr.argmax(1), np.nan)
    last = np.where(has, Mr.shape[1] - 1 - Mr[:, ::-1].argmax(1), np.nan)
    a, b = slice(max(0, y - 14), max(0, y - 4)), slice(y + 4, y + 14)
    with np.errstate(all='ignore'):
        return np.nanmax([abs(np.nanmedian(first[a]) - np.nanmedian(first[b])),
                          abs(np.nanmedian(last[a]) - np.nanmedian(last[b]))])


def side(R, axis, t, X, Y):
    # quale lato della linea di taglio (nel sistema ruotato) per le coordinate X, Y
    r = R[1] if axis == 1 else R[0]
    return r[0] * X + r[1] * Y + r[2] < t


def rectangularity(M):
    cnts, _ = cv2.findContours(M.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 0, 0
    cnt = max(cnts, key=cv2.contourArea)
    (_, _), (rw, rh), _ = cv2.minAreaRect(cnt)
    return M.sum() / max(rw * rh, 1), min(rw, rh)


def split(M, G, A, B, Lw, lp, min_area, depth=0):
    # ritorna una lista di pezzi, ognuno come lista di semipiani (R, axis, t, keep_less)
    if depth > 6:
        return [[]]
    h, w = M.shape
    Y, X = np.mgrid[0:h, 0:w]
    for s, (R, axis, t), gfrac in best_cut(M, G, A, B, Lw, lp):
        lt = side(R, axis, t, X, Y)
        parts = [M & lt, M & ~lt]
        ok = True
        thins = []
        for P in parts:
            rect, thin = rectangularity(P)
            thins.append(thin)
            if P.sum() < min_area or rect < 0.8 or thin < 3 * WORK:
                ok = False
        # solo salto di colore, niente fessura: puo' essere una fascia stampata
        # dello stesso foglio. Si taglia se il contorno fa uno scalino, o se
        # entrambi i pezzi sono grandi come fogli
        if ok and gfrac < 0.5:
            step = outline_step(M, R, axis, t)
            if not (step >= 2 or min(thins) >= 40 * WORK):
                ok = False
        if ok:
            break
    else:
        return [[]]
    out = []
    for keep, P in zip((True, False), parts):
        for sub in split(P, G, A, B, Lw, lp, min_area, depth + 1):
            out.append([(R, axis, t, keep)] + sub)
    return out


# ---------------------------------------------------------------- un foglio

def median_int(v):
    # come np.median(v) per valori interi 0..255 (il Lab viene da immagini a 8 bit):
    # contando quanti ce ne sono per valore, senza ordinare milioni di pixel
    vi = v.astype(np.intp)
    if v.size == 0 or vi.min() < 0 or vi.max() > 255 or not np.array_equal(vi, v):
        return np.median(v)
    cs = np.cumsum(np.bincount(vi, minlength=256))
    n = cs[-1]
    lo = v.dtype.type(np.searchsorted(cs, (n - 1) // 2, side='right'))
    hi = v.dtype.type(np.searchsorted(cs, n // 2, side='right'))
    return lo if n % 2 else (lo + hi) / v.dtype.type(2)


def paper_color(lab, M):
    px = lab[M]
    L = median_int(px[:, 0])
    px = px[px[:, 0] > L - 25]
    return np.array([median_int(px[:, c]) for c in range(3)], lab.dtype)


def finish(rgb, lab, d, T, piece, ppm, others, flags, scanedge, dw, Tw, forbid):
    # piece: maschera piena del foglio (crop). Buchi, bordo con la bacchetta, raddrizzo.
    # dw, Tw: distanza dal fondo quasi senza sfocatura (le fibre restano) e tolleranza.
    # forbid: gli altri fogli, che la bacchetta non deve prendere.
    bg = d < T
    Dp = np.median(d[piece & ~bg]) if (piece & ~bg).any() else T * 3
    # buchi del raccoglitore: chiazze tonde di fondo, di misura giusta, vicino a un bordo
    holes = np.zeros_like(piece)
    inner = cv2.morphologyEx((bg & piece).astype(np.uint8), cv2.MORPH_OPEN, disk(0.45 * ppm))
    n, lab_h, st, _ = cv2.connectedComponentsWithStats(inner, 8)
    if n > 1:
        dist = edge_dist(piece)
        a_lo, a_hi = 7 * ppm * ppm, 120 * ppm * ppm
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if not (a_lo <= a <= a_hi) or max(w, h) > 1.6 * min(w, h):
                continue
            if a / (w * h) < 0.62:            # un cerchio pieno fa ~0.785
                continue
            reg = lab_h[y:y+h, x:x+w] == i
            if dist[y:y+h, x:x+w][reg].min() > 30 * ppm:
                continue
            holes[y:y+h, x:x+w] |= reg
    holes = cv2.dilate(holes.astype(np.uint8), disk(0.3 * ppm)) > 0
    col_bg = others[0]
    dist = edge_dist(piece)
    core = piece & (dist > 6 * ppm) & ~bg
    own = paper_color(lab, core if core.sum() > 1000 else piece & ~bg)
    same = np.linalg.norm((own - others[0]) * W_LAB) < 1.6 * T
    if same:
        flags.append('same')              # carta quasi del colore del fondo: bordo incerto
    # bacchetta magica, contigua: via solo il fondo collegato al fuori, come in Photoshop.
    # Le fibre e gli strappi non hanno il colore del fondo e restano.
    if same:
        # carta vicina al fondo: la grana piu' chiara passerebbe per fondo e la bacchetta
        # entrerebbe nel foglio. Soglia a meta' fra il fondo e la carta
        dp = np.median(dw[core]) if core.sum() > 1000 else np.median(dw[piece & ~bg])
        Tw = min(Tw, max(5.0, 0.5 * dp))
    zone = cv2.dilate(piece.astype(np.uint8), disk(2.5 * ppm)).astype(bool) & ~forbid
    zone[[0, -1], :] = False; zone[:, [0, -1]] = False
    _, L = cv2.connectedComponents(((dw < Tw) | ~zone).astype(np.uint8), connectivity=4)
    m = zone & ~np.isin(L, np.unique(L[~zone]))
    # lembi del foglio accanto (di un altro colore) rimasti di qua dal taglio
    d_own = np.linalg.norm((lab - own) * W_LAB, axis=2)
    others = [o for o in others[1:] if np.linalg.norm((o - own) * W_LAB) > 12]
    if others:
        d_oth = np.min([np.linalg.norm((lab - o) * W_LAB, axis=2) for o in others], axis=0)
        m &= ~(~cv2.erode(piece.astype(np.uint8), disk(5 * ppm)).astype(bool)
               & (d_oth + 6 < d_own) & (lab[..., 0] > own[0] - 25))
    # contro il bordo della scansione resta solo cio' che ha il colore di questo foglio
    m &= ~(scanedge & (d_own > max(12, 0.5 * Dp)))
    # ombre: l'orlo del foglio fa ombra sul fondo. Sono pixel piu' scuri del fondo ma
    # della sua stessa tinta, nell'ultimo millimetro e mezzo, collegati al fuori.
    # Penna e carta colorata hanno un'altra tinta, la carta bianca e' piu' chiara: restano
    near = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 3) < 1.5 * ppm
    neutral = np.hypot(lab[..., 1] - col_bg[1], lab[..., 2] - col_bg[2]) < 6
    if same and own[0] < col_bg[0] and np.hypot(own[1] - col_bg[1], own[2] - col_bg[2]) < 6:
        # carta grigia o avorio, tinta del fondo ma piu' scura: "piu' scuro del fondo" e'
        # anche la carta. Dal fuori se ne va solo cio' che non sembra carta: piu' chiaro
        # (coperchio), piu' scuro (la riga d'ombra) e i 3 px intorno alla riga, dove il
        # coperchio risale verso il bianco con lo stesso grigio della carta
        Lr = cv2.cvtColor(cv2.GaussianBlur(rgb, (3, 3), 0), cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32)
        line = (Lr < own[0] - 10) & neutral & near
        ramp = cv2.dilate(line.astype(np.uint8), disk(7)).astype(bool)
        cand = near & neutral & ((Lr > own[0] + 5) | (Lr < own[0] - 10) | ramp)
        _, L = cv2.connectedComponents((cand | ~m).astype(np.uint8), connectivity=4)
        m &= ~np.isin(L, np.unique(L[~m]))
    else:
        shadow = (lab[..., 0] < col_bg[0] - 6) & neutral & near
        _, L = cv2.connectedComponents((shadow | ~m).astype(np.uint8), connectivity=4)
        m &= ~np.isin(L, np.unique(L[~m]))
    # come la seconda bacchetta: resta il foglio, le isolette sparse se ne vanno
    n, lab_m, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    if n < 2:
        return None
    m = lab_m == 1 + st[1:, 4].argmax()
    if m.sum() < 150 * ppm * ppm:
        return None
    holes = cv2.dilate(holes.astype(np.uint8), disk(0.35 * ppm)).astype(bool) & m
    # anche la sagoma e i buchi: lo studio li fa ritoccare a mano
    return cutout(rgb, m, holes, ppm, exact=True) + ((m, holes, True),)


def straight_side(prof, sign, ppm):
    # prof: per ogni riga (o colonna) dove comincia il foglio. Se i punti stanno su una
    # retta entro 0.35 mm il lato e' dritto: ritorna (a, b) di x = a + b*y, altrimenti None.
    # La retta va un filo dentro (oltre il 95% dei punti): niente fondo, niente tacche
    y = np.nonzero(prof >= 0)[0]
    if len(y) < 20 * ppm:
        return None
    x = prof[y].astype(np.float64)
    b, a = np.polyfit(y, x, 1)
    for _ in range(2):
        r = np.abs(x - (a + b * y))
        ok = r < 1.0 * ppm
        if ok.sum() < 10:
            return None
        b, a = np.polyfit(y[ok], x[ok], 1)
    r = np.abs(x - (a + b * y))
    if np.mean(r < 0.35 * ppm) < 0.9 or abs(b) > 0.02:
        return None
    a += np.percentile(sign * (x - (a + b * y)), 95) * sign
    return a, b


def soft(M, ppm):
    # bordo morbido come la bacchetta di Photoshop: la scaletta dei pixel si liscia
    # e il passaggio pieno -> trasparente dura circa un pixel e mezzo
    s = max(0.6, 0.12 * ppm)
    g = cv2.GaussianBlur(M.astype(np.float32), (0, 0), s)
    k = 1.0 / (1.5 * 0.4 / s)            # pendenza al bordo ~0.4/s per pixel
    return np.clip((g - 0.5) * k + 0.5, 0, 1)


def cutout(rgb, m, holes, ppm, exact=False):
    # m: sagoma piena del foglio, holes: buchi da lasciare trasparenti.
    # I pixel sono sempre quelli della scansione: cambia solo la trasparenza.
    # Raddrizza; poi con exact il bordo resta pixel per pixel quello della bacchetta,
    # altrimenti (Apple Vision) i lati dritti diventano rette e gli altri si lisciano.
    cnt = max(cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0],
              key=cv2.contourArea)
    (cx, cy), _, ang = cv2.minAreaRect(cnt)
    while ang > 45: ang -= 90
    while ang < -45: ang += 90
    rect, _ = rectangularity(m & ~holes)
    turn = 0.15 < abs(ang) and (abs(ang) < 10 or rect >= 0.9)
    pad = int((0.03 + 0.5 * np.sin(np.radians(abs(ang)))) * max(m.shape)) + 4
    padit = lambda a: cv2.copyMakeBorder(a, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    rgb, mf, hf = padit(rgb), padit(m.astype(np.float32)), padit(holes.astype(np.float32))
    if turn:
        Rm = cv2.getRotationMatrix2D((cx + pad, cy + pad), ang, 1.0)
        size = (rgb.shape[1], rgb.shape[0])
        rgb = cv2.warpAffine(rgb, Rm, size, flags=cv2.INTER_CUBIC)
        mf = cv2.warpAffine(mf, Rm, size, flags=cv2.INTER_LINEAR)
        hf = cv2.warpAffine(hf, Rm, size, flags=cv2.INTER_LINEAR)
    else:
        ang = 0.0
    M, Hm = mf > 0.5, hf > 0.5
    # i buchi del raccoglitore sono tondi: al posto della sagoma, l'ellisse che la ricalca
    if Hm.any():
        tondi = np.zeros(Hm.shape, np.uint8)
        for c in cv2.findContours(Hm.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]:
            if len(c) >= 5:
                cv2.ellipse(tondi, cv2.fitEllipse(c), 1, -1, cv2.LINE_8)
            else:
                cv2.drawContours(tondi, [c], -1, 1, cv2.FILLED)
        Hm = tondi > 0
    if exact:
        alpha = np.clip(mf, 0, 1) * (1 - soft(Hm, ppm))
        return crop_rgba(rgb, alpha), ang, rect
    h, w = M.shape
    ys, xs = np.nonzero(M)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    # per ogni lato, dove comincia il foglio riga per riga (solo l'80% centrale)
    rows, cols = M.any(1), M.any(0)
    first_x = np.where(rows, M.argmax(1), -1)
    last_x = np.where(rows, w - 1 - M[:, ::-1].argmax(1), -1)
    first_y = np.where(cols, M.argmax(0), -1)
    last_y = np.where(cols, h - 1 - M[::-1, :].argmax(0), -1)
    def mid(p, lo, hi):
        q = np.full_like(p, -1)
        a, b = lo + (hi - lo) // 10, hi - (hi - lo) // 10
        q[a:b] = p[a:b]
        return q
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    cover = np.ones((h, w), np.float32)
    for prof, lo, hi, pos, sign in ((first_x, y0, y1, X, 1), (last_x, y0, y1, X, -1),
                                    (first_y, x0, x1, Y, 1), (last_y, x0, x1, Y, -1)):
        line = straight_side(mid(prof, lo, hi), sign, ppm)
        if line is None:
            continue
        a, b = line
        along = Y if pos is X else X
        e = a + b * along                      # dove passa il lato
        dist = sign * (pos - e)                # >0 dentro il foglio
        cover = np.minimum(cover, np.clip(dist + 1.0, 0, 1))
    alpha = np.minimum(soft(M, ppm), cover) * (1 - soft(Hm, ppm))
    return crop_rgba(rgb, alpha), ang, rect


def crop_rgba(rgb, alpha):
    ys, xs = np.nonzero(alpha > 0.02)
    alpha = alpha[ys.min():ys.max()+1, xs.min():xs.max()+1]
    rgb = rgb[ys.min():ys.max()+1, xs.min():xs.max()+1]
    a8 = np.round(alpha * 255).astype(np.uint8)
    rgba = np.dstack([rgb, a8])
    rgba[a8 == 0, :3] = 0
    return rgba


# ---------------------------------------------------------------- coperchio aperto
# Con il coperchio aperto (un quaderno spesso) il fondo non ha un colore solo: la luce cala
# allontanandosi dal letto e il grigio va da chiaro a scuro. Per trovare i bordi si usa una
# copia "spianata"; i pixel dei ritagli restano quelli della scansione.

def bed_profiles(L, ppm):
    # luminosita' del fondo lungo i quattro lati (striscia di 3 mm, saltati i 3 px estremi),
    # lisciata su 30 mm di mediana: un foglio che tocca il bordo non sposta il profilo
    b = max(4, int(3 * ppm))
    k = odd(30 * ppm)
    def prof(strip, axis):
        v = np.median(strip, axis=axis).astype(np.float32)
        w = min(k, len(v) - (1 - len(v) % 2))
        if w < 3:
            return v
        pad = np.pad(v, w // 2, mode='edge')
        return np.median(np.lib.stride_tricks.sliding_window_view(pad, w), axis=1).astype(np.float32)
    top = prof(L[3:3 + b, :], 0); bot = prof(L[-3 - b:-3, :], 0)
    left = prof(L[:, 3:3 + b], 1); right = prof(L[:, -3 - b:-3], 1)
    return top, bot, left, right


def flatten_bed(rgb, ppm):
    # None se il fondo e' uniforme (coperchio chiuso, cartoncino): tutto come prima.
    # Altrimenti la copia spianata. Il fondo si stima dall'immagine stessa: tolta la carta
    # (soglia di Otsu, verso deciso dal bordo, allargata di 3 mm), la media dei pixel di fondo
    # nei ~12 mm intorno a ogni punto ("normalized convolution"): segue la luce che cala e la
    # zona scura vicino al quaderno. Le cose sottili e scure (gli anelli della spirale) non
    # spostano la media e restano "non fondo", come la carta.
    L = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[..., 0]
    top, bot, left, right = bed_profiles(L, ppm)
    allp = np.concatenate([top, bot, left, right])
    if allp.max() - allp.min() < 40:          # ~16 L*: sotto, e' il solito fondo uniforme
        return None
    H, W = L.shape
    f = 1.0 / ppm                              # si lavora a ~1 px per mm
    small = cv2.resize(L, (max(8, int(W * f)), max(8, int(H * f))), interpolation=cv2.INTER_AREA).astype(np.float32)
    t, _ = cv2.threshold(small.astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    paper = small > t if np.median(allp) < t else small <= t
    paper = cv2.dilate(paper.astype(np.uint8), disk(7)).astype(bool)
    w = (~paper).astype(np.float32)
    s = 12.0
    num = cv2.GaussianBlur(small * w, (0, 0), s)
    den = cv2.GaussianBlur(w, (0, 0), s)
    B = np.where(den > 0.02, num / np.maximum(den, 1e-6), np.median(small[~paper]) if (~paper).any() else 128)
    B = cv2.resize(B.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
    target = float(np.median(small[~paper])) if (~paper).any() else 128.0
    gain = (target / np.maximum(B, 4.0))[..., None]
    flat = np.clip(rgb.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    # le grandi zone scure (la copertina nera che spunta dietro la pagina, l'ombra del quaderno)
    # sono fondo; le piccole attaccate alla pagina (gli anelli della spirale) restano
    fl = cv2.resize(cv2.cvtColor(flat, cv2.COLOR_RGB2LAB)[..., 0], small.shape[::-1], interpolation=cv2.INTER_AREA)
    dark = (fl < 0.55 * target).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark, 8)
    big = np.zeros(dark.shape, bool)
    for i in range(1, n):
        if st[i, 4] > 300:                       # mm2 (si lavora a 1 px per mm)
            big |= lab == i
    if big.any():
        big = cv2.resize(big.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
        flat[big] = int(round(target))
    return flat


def cut_scan(path, ai=True, ppm=None, tol=None):
    # tol: fattore sulle tolleranze del fondo e della bacchetta (lo studio lo regola a mano)
    rgb, icc, dpi, ppm = load(path, ppm)
    orig = rgb
    flat = flatten_bed(rgb, ppm)
    if flat is not None:
        rgb = flat
    blur = cv2.GaussianBlur(rgb, (odd(0.5 * ppm), odd(0.5 * ppm)), 0)
    lab = cv2.cvtColor(blur, cv2.COLOR_RGB2LAB).astype(np.float32)
    col, T = background(lab)
    if tol:
        T *= tol
    d = np.linalg.norm((lab - col) * W_LAB, axis=2)
    bg = d < T
    # per la bacchetta: sfocatura di un pixel appena, toglie la grana ma non le fibre
    labw = cv2.cvtColor(cv2.GaussianBlur(rgb, (3, 3), 0), cv2.COLOR_RGB2LAB).astype(np.float32)
    colw, Tw = background(labw)
    if tol:
        Tw *= tol
    dw = np.linalg.norm((labw - colw) * W_LAB, axis=2)
    del labw
    # il fondo largo, senza fessure e righe di matita sottili
    # (fuori dalla scansione e' fondo: cosi' un filo di coperchio contro il bordo se ne va)
    k = int(2 * ppm)
    bgo = cv2.morphologyEx(np.pad(bg.astype(np.uint8), k, constant_values=1), cv2.MORPH_OPEN,
                           disk(1.1 * ppm))[k:-k, k:-k] > 0
    paper = cv2.morphologyEx((~bgo).astype(np.uint8), cv2.MORPH_OPEN, disk(0.8 * ppm))
    n, labs, st, _ = cv2.connectedComponentsWithStats(paper, 8)
    min_area = 150 * ppm * ppm
    sheets = []
    flags = []
    H, W = bg.shape
    # gli ultimi 2 mm della scansione: li' c'e' il telaio scuro dello scanner
    scanedge = np.ones((H, W), bool); scanedge[k:-k, k:-k] = False
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < min_area:
            continue
        mg = int(3 * ppm)
        x0, y0, x1, y1 = max(0, x-mg), max(0, y-mg), min(W, x+w+mg), min(H, y+h+mg)
        S = (labs[y0:y1, x0:x1] == i).astype(np.uint8)
        cnts, _ = cv2.findContours(S, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(S, cnts, -1, 1, cv2.FILLED)
        S = S.astype(bool)
        lab_c, d_c, rgb_c = lab[y0:y1, x0:x1], d[y0:y1, x0:x1], rgb[y0:y1, x0:x1]
        # copia ridotta per cercare dove si toccano due fogli
        f = WORK / ppm
        ws = (max(1, int(S.shape[1] * f)), max(1, int(S.shape[0] * f)))
        Sw = cv2.resize(S.astype(np.uint8), ws, interpolation=cv2.INTER_NEAREST) > 0
        # quanto ogni pixel e' fondo: 1 sotto la soglia, 0 oltre 2.5 volte
        # (le righe sottili color fondo, quadretti e matita su carta bianca, non contano)
        G = np.clip((2.5 * T - d_c) / (1.5 * T), 0, 1).astype(np.float32)
        G = cv2.morphologyEx(G, cv2.MORPH_OPEN, disk(0.45 * ppm))
        Gw = cv2.resize(G, ws, interpolation=cv2.INTER_AREA)
        smallrgb = cv2.resize(rgb_c, ws, interpolation=cv2.INTER_AREA)
        labw = cv2.cvtColor(cv2.medianBlur(smallrgb, 5), cv2.COLOR_RGB2LAB).astype(np.float32)
        Lw, Aw, Bw = labw[..., 0], labw[..., 1], labw[..., 2]
        lp = np.median(Lw[Sw])
        pieces = split(Sw, Gw, Aw, Bw, Lw, lp, min_area * f * f)
        Y, X = np.mgrid[0:S.shape[0], 0:S.shape[1]]
        Xw, Yw = X * f, Y * f
        masks = []
        for cons in pieces:
            P = S.copy()
            for R, axis, t, keep in cons:
                lt = side(R, axis, t, Xw, Yw)
                P &= lt if keep else ~lt
            if P.sum() >= min_area:
                masks.append(P)
        bgc = bg[y0:y1, x0:x1]
        cols = []
        for P in masks if len(masks) > 1 else []:   # servono solo per confrontare i fogli fra loro
            core = cv2.erode(P.astype(np.uint8), disk(6 * ppm)).astype(bool) & ~bgc
            cols.append(paper_color(lab_c, core if core.sum() > 1000 else P & ~bgc))
        for k, P in enumerate(masks):
            others = [col] + [c for j, c in enumerate(cols) if j != k]
            nflags = len(flags)
            ys, xs = np.where(P)
            bx0, by0, bx1, by1 = max(0, xs.min()-mg), max(0, ys.min()-mg), xs.max()+mg+1, ys.max()+mg+1
            # gli altri fogli: altri pezzi di carta della scansione e le altre parti di questo
            forbid = (labs[y0:y1, x0:x1] > 0) & (labs[y0:y1, x0:x1] != i)
            for j, Q in enumerate(masks):
                if j != k:
                    forbid |= Q
            sl = (slice(by0, by1), slice(bx0, bx1))
            res = finish(rgb_c[sl], lab_c[sl], d_c[sl], T, P[sl], ppm, others, flags,
                         scanedge[y0:y1, x0:x1][sl], dw[y0:y1, x0:x1][sl], Tw, forbid[sl])
            if res is None:
                continue
            rgba, ang, rect, shape = res
            # color fondo e tutto storto: e' l'ombra del cartoncino, non un foglio
            if len(flags) > nflags and rect < 0.8:
                continue
            sheets.append((y0 + by0, x0 + bx0, rgba, ang, rect, shape))
    # in ordine di lettura: dall'alto, poi da sinistra
    band = 40 * ppm
    sheets.sort(key=lambda s: (int(s[0] // band), s[1]))
    # carta quasi del colore del fondo, o niente trovato: si prova anche Apple Vision
    # e si tiene il risultato che somiglia di piu' a dei fogli
    if flat is not None:
        # coperchio aperto: le sagome vengono dalla copia spianata, i pixel dalla scansione.
        # Una striscia sottile lungo il bordo del letto (il fondo che sfuma) non e' un foglio
        sheets = [(y, x, *cutout(orig[y:y + m.shape[0], x:x + m.shape[1]], m, h, ppm, exact=e), (m, h, e))
                  for y, x, _, _, _, (m, h, e) in sheets if rectangularity(m)[1] >= 20 * ppm]
    if ai and (flags or not sheets):
        ai = cut_scan_ai(path, orig, ppm)
        if score(ai) > score(sheets):
            return ai, icc, dpi, (col, T), True
    return sheets, icc, dpi, (col, T), False


def score(sheets):
    if not sheets:
        return -1
    return min(s[4] for s in sheets) - 0.03 * (len(sheets) - 1)


# ---------------------------------------------------------------- AI (bianco su bianco)
# Quando la carta ha il colore del fondo il bordo non si vede: lo trova Vision di Apple
# (vision_mask, in locale), un oggetto per foglio. Niente buchi trasparenti.
VISION = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vision_mask')


def ai_labels(path, shape):
    out = os.path.join(ROOT, '.scancut', f'.mask-{os.getpid()}.png')
    try:
        r = subprocess.run([VISION, path, out], capture_output=True, text=True, timeout=120)
        if not os.path.exists(out):
            return None
        lab = np.asarray(Image.open(out))
        return lab if lab.shape == shape else None
    finally:
        if os.path.exists(out):
            os.remove(out)


def cut_scan_ai(path, rgb, ppm):
    labs_v = ai_labels(path, rgb.shape[:2])
    if labs_v is None:
        return []
    sheets = []
    H, W = labs_v.shape
    for k in range(1, int(labs_v.max()) + 1):
        hard = cv2.morphologyEx((labs_v == k).astype(np.uint8), cv2.MORPH_OPEN, disk(0.8 * ppm))
        n, labs, st, _ = cv2.connectedComponentsWithStats(hard, 8)
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if a < 150 * ppm * ppm:
                continue
            mg = int(3 * ppm)
            x0, y0, x1, y1 = max(0, x-mg), max(0, y-mg), min(W, x+w+mg), min(H, y+h+mg)
            m = (labs[y0:y1, x0:x1] == i).astype(np.uint8)
            cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(m, cnts, -1, 1, cv2.FILLED)
            m = cv2.erode(m, disk(0.35 * ppm)).astype(bool)
            holes = np.zeros_like(m)
            rgba, ang, rect = cutout(rgb[y0:y1, x0:x1], m, holes, ppm)
            sheets.append((y0, x0, rgba, ang, rect, (m, holes, False)))
    sheets.sort(key=lambda s: (int(s[0] // (40 * ppm)), s[1]))
    return sheets


# ---------------------------------------------------------------- cartelle

TEMP = ('.part', '.tmp', '.download', '.crdownload', '.partial')   # file ancora in arrivo


def clean_stem(stem):
    # niente caratteri di controllo (romperebbero done.tsv), spazi doppi, punti in testa
    stem = re.sub(r'[\x00-\x1f\x7f]+', ' ', stem)
    stem = re.sub(r'\s+', ' ', stem).strip().lstrip('.').strip()
    return stem or 'scan'


def split_name(stem):
    # "sketchbook 3", "sketchbook_3", "sketchbook-3", "sketchbook3", "sketchbook 3 (2)" -> ("sketchbook", 3);
    # dopo un punto il numero non conta: "sketchbook 04.05.14" e' un lotto intero
    stem = re.sub(r'\s*\(\d+\)$', '', stem)
    m = re.match(r'^(.*\S)[ _-]+(\d+)$', stem) or re.match(r'^(.*[^\d\s._-])(\d+)$', stem)
    if m and m.group(1).strip(' ._-'):
        return m.group(1).strip(' ._-'), int(m.group(2))
    return (stem.strip(' ._-') or 'unsorted'), None


def free_stem(od, batch, stem, ext):
    # Acquisizione Immagine riparte da capo a ogni apertura: se il nome c'e' gia'
    # fra gli originali, si prende il numero libero dopo l'ultimo del lotto
    if not os.path.lexists(os.path.join(od, stem + ext)):
        return stem
    nums = [split_name(os.path.splitext(f)[0])[1] or 0 for f in os.listdir(od)]
    n = max(nums + [0]) + 1
    while os.path.lexists(os.path.join(od, f'{batch} {n}{ext}')):
        n += 1
    return f'{batch} {n}'


def unique(path):
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(path):
        path = f'{base} ({i}){ext}'; i += 1
    return path


def same_png(path, rgba):
    # c'e' gia' un ritaglio identico con questo nome? (un giro rifatto non fa doppioni)
    try:
        return os.path.exists(path) and np.array_equal(np.asarray(Image.open(path)), rgba)
    except Exception:
        return False


def notify(msg):
    try:
        msg = msg.replace('\\', '').replace('"', "'")
        subprocess.run(['osascript', '-e', f'display notification "{msg}" with title "Scans"'],
                       timeout=10, capture_output=True)
    except Exception:
        pass


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def twin(path, od):
    # la stessa scansione, byte per byte, e' gia' fra gli originali del lotto?
    size = os.path.getsize(path)
    h = None
    for f in os.listdir(od):
        q = os.path.join(od, f)
        if f.startswith('.') or not os.path.isfile(q) or os.path.getsize(q) != size:
            continue
        h = h or sha(path)
        if sha(q) == h:
            return q
    return None


def take(path):
    # sposta una scansione dall'inbox in originals/<lotto>/ senza mai sovrascrivere;
    # il file lascia l'inbox solo quando la sua copia e' al sicuro
    name = os.path.basename(path)
    stem, ext = os.path.splitext(name)
    stem, ext = clean_stem(stem), ext.lower()
    batch, _ = split_name(stem)
    od = os.path.join(ORIG, batch); os.makedirs(od, exist_ok=True)
    same = twin(path, od)
    if same:
        os.remove(path)
        log(f'{name}: identical to originals/{batch}/{os.path.basename(same)}, removed from inbox')
        return None
    for _ in range(1000):
        new = free_stem(od, batch, stem, ext)
        dst = os.path.join(od, new + ext)
        try:
            os.link(path, dst)            # stesso disco: un nome in piu', niente copia
        except FileExistsError:
            continue                      # occupato nel frattempo: si riprova
        except OSError:                   # altro disco (o niente hard link): copia verificata
            tmp = dst + '.part'
            shutil.copy2(path, tmp)
            if sha(tmp) != sha(path):
                os.remove(tmp)
                raise IOError('copy differs from the original')
            if os.path.lexists(dst):
                os.remove(tmp); continue
            os.rename(tmp, dst)
        break
    else:
        raise IOError('no free name found')
    if not (os.path.samefile(path, dst) or os.path.getsize(dst) == os.path.getsize(path)):
        raise IOError('copy in originals looks wrong, scan left in inbox')
    os.remove(path)
    rel = os.path.relpath(dst, ORIG)
    log(f'{name} -> originals/{rel}' + ('' if new + ext == name else '  (renamed: name already used or odd)'))
    return dst


# registro delle scansioni gia' ritagliate, per percorso dentro originals/
def read_done():
    done = {}
    if os.path.exists(DONE):
        for line in open(DONE):
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 4:
                done.setdefault(parts[0], set()).add((parts[1], parts[2]))
    return done


def is_done(done, rel, p):
    # stesso percorso ma file diverso (un nome riusato dopo aver svuotato originals/): da rifare
    st = os.stat(p)
    return (str(st.st_size), str(int(st.st_mtime))) in done.get(rel, ())


def mark_done(rel, result):
    try:
        st = os.stat(os.path.join(ORIG, rel))
    except OSError:
        return                            # spostato via durante il ritaglio
    with open(DONE, 'a') as f:
        f.write(f'{rel}\t{st.st_size}\t{int(st.st_mtime)}\t{result}\n')


def to_failed(path, why):
    # in failed/ va solo un collegamento all'originale
    name = os.path.basename(path)
    link = os.path.join(FAIL, name)
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(path, link)
    log(f'{name}: {why} -> failed/')


def process(keep):
    name = os.path.basename(keep)
    stem, ext = os.path.splitext(name)
    batch = os.path.basename(os.path.dirname(keep))
    t0 = time.time()
    if ext.lower() not in EXT:
        to_failed(keep, f'not an image I can cut ({ext or "no extension"}), kept in originals')
        return batch, 0
    try:
        sheets, icc, dpi, (col, T), ai = cut_scan(keep)
    except Exception:
        log(f'ERROR {name}\n' + traceback.format_exc())
        to_failed(keep, 'error')
        return batch, -1
    if not sheets:
        to_failed(keep, 'no sheet found, not even by the AI')
        return batch, 0
    if not os.path.exists(keep):
        log(f'{name}: moved away from originals while being cut, cutouts not saved')
        return batch, -1
    od = os.path.join(CUT, batch); os.makedirs(od, exist_ok=True)
    for j, (_, _, rgba, ang, rect, _) in enumerate(sheets):
        suffix = '' if len(sheets) == 1 else ' ' + 'abcdefghijklmnopqrstuvwxyz'[j % 26]
        out = os.path.join(od, stem + suffix + '.png')
        if same_png(out, rgba):
            log(f'  {os.path.relpath(out, ROOT)}  already there, identical'); continue
        out = unique(out)
        tmp = out + '.part'
        kw = {'dpi': (dpi, dpi)}
        if icc: kw['icc_profile'] = icc
        Image.fromarray(rgba, 'RGBA').save(tmp, 'PNG', compress_level=4, **kw)
        os.replace(tmp, out)
        note = '' if rect >= 0.9 else f'  CHECK: shape {rect:.2f} rectangular, sheets may overlap'
        log(f'  {os.path.relpath(out, ROOT)}  {rgba.shape[1]}x{rgba.shape[0]}  tilt {ang:+.2f}{note}')
    log(f'{name}: {len(sheets)} sheet(s) in {time.time()-t0:.1f}s' + ('  (Apple Vision: paper same color as background)' if ai else ''))
    if ai and any(s[4] < 0.85 for s in sheets):
        to_failed(keep, 'cut by Apple Vision but the shape looks wrong, check it (grey card behind helps)')
    return batch, len(sheets)


def arriving():
    # tutto cio' che sta nell'inbox (tranne file nascosti e scaricamenti a meta')
    out = []
    for f in sorted(os.listdir(INBOX)):
        p = os.path.join(INBOX, f)
        if f.startswith('.') or f.lower().endswith(TEMP) or os.path.islink(p) or not os.path.isfile(p):
            continue
        out.append((p, os.stat(p)))
    return out


def uncut(done):
    # originali non ancora ritagliati: anche quelli rimasti a meta' da un giro interrotto
    out = []
    for b in sorted(os.listdir(ORIG)):
        bd = os.path.join(ORIG, b)
        if b.startswith('.') or not os.path.isdir(bd):
            continue
        for f in sorted(os.listdir(bd)):
            p = os.path.join(bd, f)
            rel = os.path.join(b, f)
            if f.startswith('.') or f.endswith('.part') or not os.path.isfile(p) or is_done(done, rel, p):
                continue
            if re.search(r'[\t\n\r]', rel) or time.time() - os.path.getmtime(p) < STABLE_S:
                continue
            out.append((p, rel))
    return out


def main():
    for d in (INBOX, CUT, ORIG, FAIL):
        os.makedirs(d, exist_ok=True)
    # un giro alla volta: se ne sta gia' girando un altro, ci pensa lui
    lock = open(os.path.join(ROOT, '.scancut', 'lock'), 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    start = time.time()
    seen, stuck = {}, set()
    summary = {}
    while time.time() - start < MAX_RUN_S:
        progressed, waiting = False, False
        for p, st in arriving():
            sig = (st.st_size, st.st_mtime)
            if (p, sig) in stuck:
                continue
            # aspetta che Acquisizione Immagine abbia finito di scrivere
            if seen.get(p, (None, 0))[0] != sig:
                seen[p] = (sig, time.time()); waiting = True; continue
            if time.time() - seen[p][1] < STABLE_S or time.time() - st.st_mtime < STABLE_S:
                waiting = True; continue
            try:
                take(p)
            except Exception:
                log(f'ERROR moving {os.path.basename(p)}, left in inbox\n' + traceback.format_exc())
                stuck.add((p, sig))
                notify(f'{os.path.basename(p)} could not be moved, it is still in the inbox')
            seen.pop(p, None)
            progressed = True
        # ritaglio automatico spento (dallo studio): le scansioni si sistemano e basta
        for keep, rel in ([] if os.path.exists(os.path.join(ROOT, '.scancut', 'autocut-off')) else uncut(read_done())):
            try:
                batch, n = process(keep)
            except Exception:
                log(f'ERROR {rel}\n' + traceback.format_exc())
                batch, n = os.path.dirname(rel), -1
            mark_done(rel, 'ok' if n > 0 else 'failed')
            b = summary.setdefault(batch, [0, 0, 0])
            b[0] += 1
            if n > 0: b[1] += n
            else: b[2] += 1
            progressed = True
        if not progressed and not waiting:
            break
        if not progressed:
            time.sleep(1.5)
    if summary:
        parts = []
        for b, (s, n, bad) in summary.items():
            parts.append(f'{b}: {s} scan{"s" if s != 1 else ""}, {n} sheet{"s" if n != 1 else ""}'
                         + (f', {bad} to check in failed' if bad else ''))
        notify(' · '.join(parts))


if __name__ == '__main__':
    main()
