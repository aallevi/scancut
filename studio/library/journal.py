# le trascrizioni per nvim e la stampa: un file per taglio, Markdown (come le note del wiki) o LaTeX (un documento
# semplice che si compila da solo e che pandoc legge nei propri modelli). Una rappresentazione della libreria, mai
# una copia da modificare: si corregge nello studio e la cartella si riscrive.

import os, re, json, time, subprocess, hashlib

from .. import core

_ESC = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '$': r'\$', '&': r'\&', '#': r'\#', '^': r'\^{}', '_': r'\_',
        '%': r'\%', '~': r'\textasciitilde{}'}


def esc(t):
    return ''.join(_ESC.get(c, c) for c in t)


def inline(t):
    t = esc(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', t)
    return re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\\emph{\1}', t)


def md_to_tex(text):
    # quel che l'OCR da' in Markdown (titoli, elenchi), in LaTeX semplice; il resto paragrafi
    out, items = [], None
    for line in (text or '').splitlines():
        m = re.match(r'^\s*([-*•○]|\d+[.)])\s+(.*)', line)
        if m:
            if items is None:
                items = 'enumerate' if m.group(1)[0].isdigit() else 'itemize'
                out.append(f'\\begin{{{items}}}')
            out.append(r'\item ' + inline(m.group(2)))
            continue
        if items:
            out.append(f'\\end{{{items}}}'); items = None
        h = re.match(r'^(#{1,4})\s+(.*)', line)
        if h:
            out.append(r'\paragraph{' + inline(h.group(2)) + '}')
        elif line.strip():
            out.append(inline(line.rstrip()) + r'\\')
        else:
            out.append('')
    if items:
        out.append(f'\\end{{{items}}}')
    return '\n'.join(out).replace('\\\\\n\n', '\n\n').rstrip('\\')


def safe_name(s):
    return re.sub(r'[^\w\- .]+', '', s, flags=re.U).strip() or 'untitled'


def _texts(lib, rid):
    t = lib.db.execute('SELECT plain FROM current_text WHERE region_id = ? ORDER BY created_at DESC, reading_id DESC LIMIT 1', (rid,)).fetchone()
    return t['plain'] if t and t['plain'].strip() else ''


def collect(lib):
    # una voce per taglio (una parte con testo, o un taglio con zone sue), e una per il testo intero di una fonte.
    # Il nome e' quello del file del taglio (vendrdro 4 a), cosi' testo e immagine si ritrovano.
    entries, by_cut = [], {}
    for it in lib.db.execute("SELECT i.*, s.name AS series FROM item i LEFT JOIN series s ON s.id = i.series_id "
                             "WHERE i.trashed_at IS NULL AND i.kind != 'piece' ORDER BY i.date, i.title"):
        tops = lib.db.execute("SELECT * FROM region WHERE item_id = ? AND parent_id IS NULL AND kind IN ('sheet', 'text') AND removed_at IS NULL "
                              "AND asset_id IN (SELECT asset_id FROM item_asset WHERE item_id = ? AND role != 'cutout') ORDER BY position", (it['id'], it['id'])).fetchall()
        inc = [r['id'] for r in tops if r['export_on'] and r['kind'] == 'sheet']
        letter = lambda r: ('abcdefghijklmnopqrstuvwxyz'[inc.index(r['id']) % 26] if len(inc) > 1 else '') if r['id'] in inc else ''
        base = {'source': it['title'] or '', 'date': it['date'] or '', 'series': it['series'] or '', 'item': it['uuid']}
        for r in tops:
            areas = [(f'area {k + 1}', _texts(lib, a['id'])) for k, a in enumerate(
                lib.db.execute('SELECT id FROM region WHERE parent_id = ? AND removed_at IS NULL ORDER BY position', (r['id'],)))]
            cut = lib.db.execute("SELECT path FROM cut WHERE region_id = ? AND path NOT LIKE '%/studio-data/%' ORDER BY id DESC LIMIT 1", (r['id'],)).fetchone()
            cut = cut['path'] if cut and os.path.exists(cut['path']) else ''
            name = os.path.splitext(os.path.basename(cut))[0] if cut else ' '.join(x for x in (it['title'] or '', letter(r), r['label'] or '') if x)
            e = dict(base, name=name, letter=letter(r), label=r['label'] or ('text' if r['kind'] == 'text' else ''), uuid=r['uuid'], cut=cut,
                     text=_texts(lib, r['id']), areas=[a for a in areas if a[1]])
            entries.append(e)
            if cut:
                by_cut[cut] = e
        whole = [t for t in lib.db.execute('SELECT * FROM current_text WHERE region_id IS NULL AND asset_id IN (SELECT asset_id FROM item_asset WHERE item_id = ? AND role != \'cutout\')', (it['id'],))
                 if t['plain'].strip()]
        if whole:
            entries.append(dict(base, name=f'{it["title"] or "untitled"} (whole page)', letter='', label='whole page', uuid=it['uuid'], cut='',
                                text=whole[-1]['plain'], areas=[]))
    # le zone fatte sul taglio stesso (un taglio con parti sue): vanno nel file di quel taglio
    for pc in lib.db.execute("SELECT i.id, a.path FROM item i JOIN item_asset ia ON ia.item_id = i.id JOIN asset a ON a.id = ia.asset_id "
                             "WHERE i.kind = 'piece' AND i.trashed_at IS NULL").fetchall():
        e = by_cut.get(pc['path'])
        if not e:
            continue
        for k, r in enumerate(lib.db.execute("SELECT id FROM region WHERE item_id = ? AND removed_at IS NULL ORDER BY position", (pc['id'],))):
            t = _texts(lib, r['id'])
            if t:
                e['areas'].append((f'on the cut {k + 1}', t))
    return [e for e in entries if e['text'] or e['areas']]


def _tex_lines(text):
    # il testo come e' stato letto: le righe restano righe, i paragrafi paragrafi
    return md_to_tex(text)


TEX_HEAD = r"""\documentclass[12pt,a4paper]{article}
\usepackage{iftex}
\ifPDFTeX\usepackage[utf8]{inputenc}\usepackage[T1]{fontenc}\else\usepackage{fontspec}\fi
\usepackage[margin=3cm]{geometry}
\usepackage{graphicx,longtable,booktabs,array,calc,amsmath,amssymb,multirow,soul}
\usepackage[normalem]{ulem}
\usepackage{hyperref}
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\pandocbounded}[1]{#1}
\makeatletter\@ifundefined{c@none}{\newcounter{none}}{}\makeatother
\setlength{\parindent}{0pt}\setlength{\parskip}{.6em}
\pagestyle{plain}
"""


FIG = re.compile(r'^[ \t]*!\[[^\]\n]*\]\([^)\n]*\)[ \t]*(\d+)[ \t]*,[ \t]*(\d+)[ \t]*,[ \t]*(\d+)[ \t]*,[ \t]*(\d+)[ \t]*$', re.M)
PRINT_PX = 2400                  # lato lungo delle figure: ~20 cm a 300 dpi, abbastanza per la stampa; mai ingrandite


def figures(e, out_dir, texts):
    # le figure che il lettore ha segnato (riquadri su 0-1000 del taglio letto): pixel veri ritagliati dal taglio,
    # rimpiccioliti se servono per la stampa, PNG con la trasparenza, in figures/. Ritorna {(testo, n): nome}.
    from PIL import Image
    boxes = [(ti, k, tuple(map(int, m.groups()))) for ti, t in enumerate(texts) for k, m in enumerate(FIG.finditer(t or ''))]
    if not boxes or not e['cut'] or not os.path.exists(e['cut']):
        return {}
    src, tmp = e['cut'], None
    if src.lower().endswith('.jxl'):
        tmp = os.path.join(out_dir, f'.fig-{os.getpid()}.png')
        if subprocess.run(['djxl', src, tmp, '--quiet'], capture_output=True, timeout=600).returncode:
            return {}
        src = tmp
    names = {}
    try:
        im = Image.open(src)
        im.load()
        if im.mode not in ('RGB', 'RGBA'):
            im = im.convert('RGBA' if 'A' in im.mode or 'transparency' in im.info else 'RGB')
        W, H = im.size
        os.makedirs(os.path.join(out_dir, 'figures'), exist_ok=True)
        for n, (ti, k, (a, b, c, d)) in enumerate(boxes, 1):
            box = (round(min(a, c) / 1000 * W), round(min(b, d) / 1000 * H), round(max(a, c) / 1000 * W), round(max(b, d) / 1000 * H))
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                continue
            fig = im.crop(box)
            if max(fig.size) > PRINT_PX:
                fig.thumbnail((PRINT_PX, PRINT_PX), Image.LANCZOS)
            name = f'{e["date"] or "undated"} {safe_name(e["name"])} figure {n}.png'
            p = os.path.join(out_dir, 'figures', name)
            import io
            buf = io.BytesIO(); fig.save(buf, 'PNG', optimize=True)
            if not os.path.exists(p) or open(p, 'rb').read() != buf.getvalue():
                with open(p + '.part', 'wb') as f:
                    f.write(buf.getvalue())
                os.replace(p + '.part', p)
            names[(ti, k)] = name
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    return names


MATH = re.compile(r'\\\((.+?)\\\)|\\\[(.+?)\\\]', re.S)


def math_md(text):
    # le formule come le scrivono i lettori (\( x \) e \[ x \], alla LaTeX) nei dollari di Markdown: pandoc le legge
    # solo cosi'; altrimenti stampa la parentesi e il comando crudo ("( \frac{d}{dx} )" in cima a vendrdro 8)
    return MATH.sub(lambda m: f'${m.group(1).strip()}$' if m.group(1) is not None else f'$${m.group(2).strip()}$$', text or '')


def _with_figures(text, ti, names, md):
    # la riga della figura diventa un segnaposto (LaTeX) o un'immagine Markdown con il file ritagliato
    k = [-1]

    def sub(m):
        k[0] += 1
        n = names.get((ti, k[0]))
        if not n:
            return ''
        return f'![](figures/{n})' if md else f'SCANSTUDIOFIGURE{hashlib.md5(n.encode()).hexdigest()}'
    return FIG.sub(sub, math_md(text))


def _pandoc(text, src, dst, *extra):
    try:
        r = subprocess.run(['pandoc', '-f', src, '-t', dst, '--wrap=preserve', *extra], input=text, capture_output=True, text=True, timeout=60)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _html_tables(text, dst):
    # le tabelle HTML dei lettori (celle unite, a capo, apici) lette da pandoc come HTML: tutto quel che dicono
    # arriva nel diario (LaTeX con multirow, Markdown a griglia). Segnaposto, poi al loro posto
    from .textfmt import HTML_TABLE, close_table
    found = {}

    def sub(m):
        out = _pandoc(close_table(m.group(0)), 'html', dst)
        if out is None:
            return m.group(0)
        k = f'SCANSTUDIOTABLE{hashlib.md5(m.group(0).encode()).hexdigest()}'
        found[k] = out
        return f'\n\n{k}\n\n'
    return HTML_TABLE.sub(sub, text), found


def pandoc_tex(text):
    # il testo del lettore in LaTeX con pandoc (titoli, elenchi, tabelle anche HTML, enfasi, apici, formule);
    # le righe restano righe
    from .textfmt import inline_for_pandoc
    t, tables = _html_tables(text, 'latex')
    out = _pandoc(inline_for_pandoc(t), 'markdown+hard_line_breaks-raw_tex-raw_html-auto_identifiers-citations-example_lists-fancy_lists', 'latex', '--shift-heading-level-by=1')
    if out is None:
        return md_to_tex(text)                            # senza pandoc: la conversione semplice di prima
    for k, v in tables.items():
        out = out.replace(k, v)
    # i titoli del testo stanno sotto quello del taglio, senza numeri (come lui)
    return re.sub(r'\\((?:sub)*section|paragraph)\{', r'\\\1*{', out)


def md_text(text):
    # per il diario Markdown (nvim, EasyPrint con pandoc): le tabelle HTML come tabelle a griglia di pandoc, che
    # tengono le celle unite, e l'HTML in linea nelle sue forme; il resto com'e'
    from .textfmt import inline_for_pandoc
    t, tables = _html_tables(text, 'markdown')
    t = inline_for_pandoc(t)
    for k, v in tables.items():
        t = t.replace(k, v)
    return re.sub(r'\n{3,}', '\n\n', t)


def _figure_tex(n):
    return (r'\begin{center}\includegraphics[width=\linewidth,height=.6\textheight,keepaspectratio]{figures/' + n + r'}\end{center}')


def as_tex(e, stamp, names=None):
    # un documento intero e semplice: si compila da solo (lualatex o pdflatex), pandoc lo legge nei propri
    # modelli (EasyPrint), journal.tex li raccoglie tutti con docmute. Solo comandi standard.
    names = names or {}
    title = esc(e['name'])
    sub = ' · '.join(esc(x) for x in (e['date'], e['series'], f'from {e["source"]}' if e['source'] and e['source'] != e['name'] else '') if x)
    body = [f'\\section*{{{title}}}', f'\\emph{{{sub}}}' if sub else '', '']
    figs = {f'SCANSTUDIOFIGURE{hashlib.md5(n.encode()).hexdigest()}': n for n in names.values()}

    def conv(t, ti):
        out = pandoc_tex(_with_figures(t, ti, names, False))
        for k, n in figs.items():
            out = out.replace(k, _figure_tex(n))
        return out
    if e['text']:
        body += [conv(e['text'], 0), '']
    for i, (head, t) in enumerate(e['areas'], 1):
        body += [f'\\subsection*{{{esc(head)}}}', conv(t, i), '']
    return (f'% Scan Studio · read-only, written {stamp}. Correct the text in Scan Studio: this file is rewritten.\n'
            f'% scanstudio://region/{e["uuid"]} · source scanstudio://item/{e["item"]}\n'
            + TEX_HEAD + '\\begin{document}\n' + '\n'.join(body).rstrip() + '\n\\end{document}\n')


def _yaml(v):
    return '"' + str(v).replace('\\', '\\\\').replace('"', '\\"') + '"'


def as_md(e, stamp, names=None):
    # come le note del wiki: front matter con title, date e id (l'uuid della parte, che non cambia), poi il testo
    head = ['---', f'title: {_yaml(e["name"])}', f'date: {e["date"]}', f'id: {e["uuid"]}']
    if e['series']:
        head.append(f'series: {_yaml(e["series"])}')
    if e['source'] and e['source'] != e['name']:
        head.append(f'from: {_yaml(e["source"])}')
    # solo indirizzi della libreria, nessun percorso di file: il testo e' testo, le cartelle non contano
    head += [f'source: scanstudio://item/{e["item"]}', f'part: scanstudio://region/{e["uuid"]}']
    head += ['readonly: true', f'# Scan Studio · read-only, written {stamp}. Correct the text in Scan Studio: this file is rewritten.', '---', '']
    names = names or {}
    body = [md_text(_with_figures(e['text'], 0, names, True)).strip(), ''] if e['text'] else []
    for i, (h, t) in enumerate(e['areas'], 1):
        body += [f'## {h}', '', md_text(_with_figures(t, i, names, True)).strip(), '']
    return '\n'.join(head + body).rstrip() + '\n'


def write(lib, out_dir, fmt='md'):
    # tutta la cartella: un file per taglio con testo (e per il testo intero di una fonte); per LaTeX anche journal.tex
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime('%Y-%m-%dT%H:%M:%S')
    ext = '.tex' if fmt == 'tex' else '.md'
    files, figs_kept = [], set()
    same = lambda a, b: [l for l in a.splitlines() if 'written 2' not in l] == [l for l in b.splitlines() if 'written 2' not in l]
    for e in collect(lib):
        names = figures(e, out_dir, [e['text']] + [t for _, t in e['areas']])
        figs_kept.update(names.values())
        text = (as_tex if fmt == 'tex' else as_md)(e, stamp, names)
        name = f'{e["date"] or "undated"} {safe_name(e["name"])}{ext}'
        k = 2
        while name in files:                                  # due voci con lo stesso nome: la seconda prende un numero
            name = f'{e["date"] or "undated"} {safe_name(e["name"])} ({k}){ext}'; k += 1
        p = os.path.join(out_dir, name)
        if not os.path.exists(p) or not same(open(p, encoding='utf-8').read(), text):
            if os.path.exists(p):
                os.chmod(p, 0o644)
            with open(p + '.part', 'w', encoding='utf-8') as f:
                f.write(text)
            os.chmod(p + '.part', 0o444)                 # in sola lettura anche per nvim: ci si prende, non ci si scrive
            os.replace(p + '.part', p)
        files.append(name)
    # file spariti (o del formato di prima, un file per fonte): via dalla cartella, solo i nostri
    for f in os.listdir(out_dir):
        fp = os.path.join(out_dir, f)
        if f.endswith(('.md', '.tex', '.sty')) and f not in files and f != 'journal.tex' and os.path.isfile(fp):
            head = open(fp, encoding='utf-8').read(2000)
            if head.startswith('% Scan Studio') or head.startswith('% scanstudio.sty') or '# Scan Studio · read-only' in head:
                os.chmod(fp, 0o644)
                os.remove(fp)
    fd = os.path.join(out_dir, 'figures')                # figure di testi che non le hanno piu': via (sono una rappresentazione)
    if os.path.isdir(fd):
        for f in os.listdir(fd):
            if f.endswith('.png') and ' figure ' in f and f not in figs_kept:
                os.remove(os.path.join(fd, f))
        if not os.listdir(fd):
            os.rmdir(fd)
    if fmt == 'tex':
        master = ('% Scan Studio journal: every transcription, one file per cut, by date. Read-only, rewritten by Scan Studio.\n'
                  '% Compile this file (lualatex or pdflatex), or \\input any single file into your own document with docmute.\n'
                  + TEX_HEAD + '\\usepackage{docmute}\n\\begin{document}\n'
                  + ''.join(f'\\input{{{os.path.splitext(f)[0]}}}\n' for f in sorted(files)) + '\\end{document}\n')
        with open(os.path.join(out_dir, 'journal.tex'), 'w', encoding='utf-8') as f:
            f.write(master)
    lib.log('journal', 'library', lib.meta('uuid'), dir=out_dir, files=len(files), format=fmt)
    return {'dir': out_dir, 'files': len(files), 'format': fmt}
