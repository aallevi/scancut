# il formato unico dei testi della libreria: Markdown. I lettori scrivono a modo loro (LightOnOCR le tabelle e
# l'enfasi in HTML); tutto passa di qui prima di essere salvato (Library.add_reading, Library.correct), cosi' la
# vista dello studio, il diario LaTeX/Markdown, pandoc (EasyPrint), la ricerca e i metadati del taglio leggono la
# stessa cosa. Quel che il lettore ha scritto davvero resta in reading.raw.

import re


def _cell(c):
    # il contenuto di una cella o di un pezzo HTML in Markdown in linea: a capo, grassetto, corsivo; il resto testo
    c = re.sub(r'<br\s*/?>', ' ', c, flags=re.I)
    c = re.sub(r'<(b|strong)\b[^>]*>(.*?)</\1>', r'**\2**', c, flags=re.I | re.S)
    c = re.sub(r'<(i|em)\b[^>]*>(.*?)</\1>', r'*\2*', c, flags=re.I | re.S)
    c = re.sub(r'</?[a-zA-Z][^>]*>', '', c)
    c = c.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
    return ' '.join(c.split())


def _table_md(m):
    rows = []
    for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>', m.group(0), re.I | re.S):
        cells = re.findall(r'<t([hd])\b([^>]*)>(.*?)</t[hd]>', tr, re.I | re.S)
        row = []
        for _, attrs, c in cells:
            span = re.search(r'colspan\s*=\s*["\']?(\d+)', attrs, re.I)
            row += [_cell(c).replace('|', '\\|')] + [''] * (int(span.group(1)) - 1 if span else 0)
        if row:
            rows.append(row)
    if not rows:
        return _cell(m.group(0))
    n = max(len(r) for r in rows)
    rows = [r + [''] * (n - len(r)) for r in rows]
    line = lambda r: '| ' + ' | '.join(r) + ' |'
    # la prima riga fa da intestazione (Markdown non ha tabelle senza): con <th> lo e' gia'
    return '\n\n' + '\n'.join([line(rows[0]), '|' + '---|' * n] + [line(r) for r in rows[1:]]) + '\n\n'


def html_to_md(text):
    # alcuni lettori (LightOnOCR) scrivono le tabelle e l'enfasi in HTML dentro il Markdown: in Markdown vero, cosi'
    # la vista dello studio, il diario LaTeX e pandoc (EasyPrint) le leggono come tabelle e non come tag
    if not text or '<' not in text:
        return text
    t = re.sub(r'<table\b.*?</table>', _table_md, text, flags=re.I | re.S)
    t = re.sub(r'<br\s*/?>', '  \n', t, flags=re.I)
    t = re.sub(r'<(b|strong)>(.*?)</\1>', r'**\2**', t, flags=re.I | re.S)
    t = re.sub(r'<(i|em)>(.*?)</\1>', r'*\2*', t, flags=re.I | re.S)
    t = re.sub(r'</?(?:p|div|span|u|sup|sub|thead|tbody|center|font)\b[^>]*>', '', t, flags=re.I)
    return re.sub(r'\n{3,}', '\n\n', t).strip()

