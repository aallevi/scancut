# esempio di motore personale: la cosa piu' semplice, una soglia fissa sulla luminosita'.
# Lo studio chiama segment(rgb, ppm, params) e vuole una lista di maschere, una per foglio.
# Si ricarica a ogni Detect: si cambia qui e si riprova. PARAMS (facoltativo) appare nel pannello.

import numpy as np, cv2

NAME = 'Example script: fixed threshold'
NOTE = 'A starting point for your own engines: paper lighter than a dark lid.'
PARAMS = [{'id': 'level', 'label': 'Level', 'type': 'number', 'default': 160, 'step': 5,
           'hint': 'Pixels lighter than this (0-255) count as paper.'}]


def segment(rgb, ppm, params):
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    m = (grey > float(params.get('level', 160))).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    return [lab == i for i in range(1, n) if st[i, 4] > 150 * ppm * ppm]
