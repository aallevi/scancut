# PNG a 16 bit (grigio, grigio+alfa, RGB, RGBA): Pillow non li scrive. Con la misura (pHYs)
# e il profilo colore (iCCP) dentro il file, come i PNG a 8 bit dello studio.
import struct, zlib
import numpy as np


def _chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def write(path, arr, dpi=None, icc=None, level=6):
    a = np.asarray(arr)
    if a.dtype != np.uint16:
        raise ValueError('png16 wants uint16')
    if a.ndim == 2:
        a = a[..., None]
    h, w, c = a.shape
    ctype = {1: 0, 2: 4, 3: 2, 4: 6}[c]
    raw = a.reshape(h, w * c).astype('>u2').view(np.uint8).reshape(h, w * c * 2)
    # filtro "Up" su ogni riga: la differenza dalla riga sopra comprime molto meglio una scansione
    up = raw.copy()
    up[1:] = raw[1:] - raw[:-1]
    rows = np.empty((h, 1 + raw.shape[1]), np.uint8)
    rows[:, 0] = 2
    rows[:, 1:] = up
    out = [b'\x89PNG\r\n\x1a\n', _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 16, ctype, 0, 0, 0))]
    if icc:
        out.append(_chunk(b'iCCP', b'ICC profile\x00\x00' + zlib.compress(icc)))
    if dpi:
        ppm = int(round(float(dpi) / 0.0254))
        out.append(_chunk(b'pHYs', struct.pack('>IIB', ppm, ppm, 1)))
    out.append(_chunk(b'IDAT', zlib.compress(rows.tobytes(), level)))
    out.append(_chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(b''.join(out))


def read(path):
    # per i confronti: OpenCV legge i PNG a 16 bit (in ordine BGR/BGRA)
    import cv2
    m = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if m is None:
        return None
    if m.ndim == 3 and m.shape[2] == 3:
        m = cv2.cvtColor(m, cv2.COLOR_BGR2RGB)
    elif m.ndim == 3 and m.shape[2] == 4:
        m = cv2.cvtColor(m, cv2.COLOR_BGRA2RGBA)
    return m
