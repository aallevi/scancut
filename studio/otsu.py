# motore "Otsu threshold": soglia di Otsu sulla luminosita' (nato come esempio di script).
# segment(rgb, ppm, params) -> una maschera per foglio; il bordo finale lo rifa' core
# (refine_with_wand, "Edge from real pixels") se l'opzione e' accesa.
#
# Funziona nei due sensi: carta scura sul coperchio bianco, o carta chiara su fondo scuro
# (coperchio aperto, cartoncino grigio). Il verso lo decide il bordo della scansione: e' fondo.

import numpy as np, cv2

PARAMS = [
    {'id': 'polarity', 'label': 'Paper is', 'type': 'choice', 'default': 'auto',
     'choices': [{'text': 'auto', 'note': 'Decided from the border of the scan (it is lid).'},
                 {'text': 'lighter', 'note': 'Light paper on a dark lid or grey card.'},
                 {'text': 'darker', 'note': 'Dark or coloured paper on the white lid.'}],
     'hint': 'Whether the paper is lighter or darker than what is around it. Auto looks at the border of the '
             'scan, which is always lid or card.'},
]


def segment(rgb, ppm, params):
    grey = cv2.cvtColor(cv2.GaussianBlur(rgb, (5, 5), 0), cv2.COLOR_RGB2GRAY)
    t, _ = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    pol = params.get('polarity', 'auto')
    if pol == 'auto':
        b = int(3 * ppm)
        border = np.concatenate([grey[:b].ravel(), grey[-b:].ravel(), grey[:, :b].ravel(), grey[:, -b:].ravel()])
        pol = 'lighter' if np.median(border) < t else 'darker'
    m = (grey > t) if pol == 'lighter' else (grey <= t)
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    taken = np.zeros(m.shape, bool)
    # dal pezzo piu' grande: le isole bianche chiuse dalle linee del disegno stanno dentro un
    # foglio gia' trovato e non sono fogli a parte
    for i in sorted(range(1, n), key=lambda i: -st[i, 4]):
        if st[i, 4] < 150 * ppm * ppm:           # almeno 1.5 cm2
            continue
        piece = (lab == i).astype(np.uint8)
        if taken[piece > 0].mean() > 0.5:
            continue
        # la soglia buca la carta dove c'e' l'inchiostro: si riempie dentro il contorno esterno
        cnts, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(piece, cnts, -1, 1, cv2.FILLED)
        taken |= piece > 0
        out.append(piece > 0)
    return out
