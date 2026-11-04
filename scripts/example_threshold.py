# esempio di motore personale: soglia di Otsu sulla luminosita'.
# Lo studio chiama segment(rgb, ppm, params) e vuole una maschera per foglio.
# Si ricarica a ogni Detect: si cambia qui e si riprova.

import numpy as np, cv2

NAME = 'Example: Otsu threshold'
NOTE = 'Dark paper on the white lid. A starting point for your own engines.'


def segment(rgb, ppm, params):
    grey = cv2.cvtColor(cv2.GaussianBlur(rgb, (5, 5), 0), cv2.COLOR_RGB2GRAY)
    _, m = cv2.threshold(grey, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        if st[i, 4] > 150 * ppm * ppm:          # almeno 1.5 cm2
            out.append(lab == i)
    return out
