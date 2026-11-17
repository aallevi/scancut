# il testo letto si tiene com'e': quel che il lettore ha dato (Markdown, HTML, LaTeX, riquadri) in reading.plain,
# e tutta la sua uscita (riquadri dei blocchi, confidenze, pezzi) in reading.raw. Niente si converte salvando;
# chi mostra il testo (lo studio, il diario, pandoc) lo rende com'e', tabelle HTML comprese.

import re, threading
from collections import OrderedDict

_raw, _lock = OrderedDict(), threading.Lock()


def remember(plain, raw):
    # l'uscita intera di una lettura, ritrovata da chi la salva nella libreria (qualunque strada faccia il testo:
    # lavoro, foglio, riquadro, stato dello studio)
    if plain and raw:
        with _lock:
            _raw[plain] = raw
            _raw.move_to_end(plain)
            while len(_raw) > 200:
                _raw.popitem(last=False)


def raw_for(plain):
    with _lock:
        return _raw.get(plain)


# blocchi HTML che i lettori scrivono dentro il Markdown (LightOnOCR: tabelle, con celle unite e a capo)
HTML_TABLE = re.compile(r'<table\b.*?</table>', re.I | re.S)
_INLINE = [(re.compile(r'<sup>(.*?)</sup>', re.I | re.S), lambda m: '^' + m.group(1).replace(' ', '\\ ') + '^'),
           (re.compile(r'<sub>(.*?)</sub>', re.I | re.S), lambda m: '~' + m.group(1).replace(' ', '\\ ') + '~'),
           (re.compile(r'<u>(.*?)</u>', re.I | re.S), lambda m: '[' + m.group(1) + ']{.underline}'),
           (re.compile(r'<(b|strong)>(.*?)</\1>', re.I | re.S), lambda m: '**' + m.group(2) + '**'),
           (re.compile(r'<(i|em)>(.*?)</\1>', re.I | re.S), lambda m: '*' + m.group(2) + '*'),
           (re.compile(r'<br\s*/?>', re.I), lambda m: '\\\n')]


def inline_for_pandoc(text):
    # solo per rendere (mai salvato): l'HTML in linea nelle forme che il Markdown di pandoc conosce
    for rx, fn in _INLINE:
        text = rx.sub(fn, text)
    return text
