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
# (anche una tabella che non si chiude: un lettore che si incanta finisce le parole prima di </table>)
HTML_TABLE = re.compile(r'<table\b.*?(?:</table>|\Z)', re.I | re.S)
_MATH = re.compile(r'(\$\$.+?\$\$|\$[^$\n]+?\$)', re.S)


def close_table(t):
    # una tabella interrotta (il lettore ha finito le parole): si chiude quel che e' aperto, cella, riga, tabella,
    # perche' il lettore HTML di pandoc la legga come tabella; un tag mozzato in fondo resta fuori
    if re.search(r'</table>\s*$', t, re.I):
        return t
    t = re.sub(r'<[^>]*$', '', t)
    cell = re.search(r'<(t[dh])\b[^>]*>(?:(?!</t[dh]>).)*$', t, re.I | re.S)
    if cell:
        t += f'</{cell.group(1).lower()}>'
    if len(re.findall(r'<tr\b', t, re.I)) > len(re.findall(r'</tr>', t, re.I)):
        t += '</tr>'
    return t + '</table>'


def literal_marks(text):
    # ^ ~ @ scritti dal lettore sono caratteri, non apici, pedici o citazioni di pandoc ("(^_^)" spariva):
    # si proteggono fuori dalle formule; poi l'HTML in linea diventa le forme di pandoc
    parts = _MATH.split(text)
    return ''.join(p if i % 2 else re.sub(r'([\^~@])', r'\\\1', p) for i, p in enumerate(parts))
_INLINE = [(re.compile(r'<sup>(.*?)</sup>', re.I | re.S), lambda m: '^' + m.group(1).replace(' ', '\\ ') + '^'),
           (re.compile(r'<sub>(.*?)</sub>', re.I | re.S), lambda m: '~' + m.group(1).replace(' ', '\\ ') + '~'),
           (re.compile(r'<u>(.*?)</u>', re.I | re.S), lambda m: '[' + m.group(1) + ']{.underline}'),
           (re.compile(r'<(b|strong)>(.*?)</\1>', re.I | re.S), lambda m: '**' + m.group(2) + '**'),
           (re.compile(r'<(i|em)>(.*?)</\1>', re.I | re.S), lambda m: '*' + m.group(2) + '*'),
           (re.compile(r'<br\s*/?>', re.I), lambda m: '\\\n')]


def inline_for_pandoc(text):
    # solo per rendere (mai salvato): l'HTML in linea nelle forme che il Markdown di pandoc conosce
    text = literal_marks(text)
    for rx, fn in _INLINE:
        text = rx.sub(fn, text)
    return text
