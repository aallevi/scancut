# le trascrizioni come LaTeX, per nvim e la stampa: una rappresentazione della libreria, mai una copia
# da modificare (si corregge nello studio e la cartella si riscrive). Senza preambolo: ogni oggetto e' un
# file da \input; i comandi \scanstudio... hanno un aspetto di partenza in scanstudio.sty, che la propria
# configurazione puo' ridefinire.

import os, re, json, time

from .. import core

STY = r"""% scanstudio.sty: aspetto di partenza delle trascrizioni di Scan Studio (si puo' ridefinire tutto)
\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{scanstudio}[2026/11/07 Scan Studio transcriptions]
\RequirePackage{graphicx}
\providecommand{\scanstudiolink}[1]{}%
% \scanstudioentry{titolo}{data}{serie}{link}
\providecommand{\scanstudioentry}[4]{\section*{#1}\noindent\textit{#2\ifx&#3&\else\ \textperiodcentered\ #3\fi}\par\medskip}
% \scanstudiopart{lettera}{nome}{file del taglio, o vuoto}{link}  ...  \endscanstudiopart
\providecommand{\scanstudioshowcuts}{0}
\newenvironment{scanstudiopart}[4]{\par\noindent\textbf{#1}\ifx&#2&\else\ #2\fi\par\setlength{\parindent}{0pt}
  \ifnum\scanstudioshowcuts=1 \ifx&#3&\else\IfFileExists{#3}{\includegraphics[width=.35\linewidth]{#3}\par}{}\fi\fi}{\par\medskip}
\newenvironment{scanstudioarea}[1]{\par\noindent\textit{#1}\par}{\par}
"""

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


def write(lib, out_dir):
    # tutta la cartella del diario: un file per oggetto con testo, journal.tex, scanstudio.sty
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime('%Y-%m-%dT%H:%M:%S')
    files = []
    for it in lib.db.execute("SELECT i.*, s.name AS series FROM item i LEFT JOIN series s ON s.id = i.series_id WHERE i.trashed_at IS NULL ORDER BY i.date, i.title"):
        parts = []
        tops = lib.db.execute("SELECT * FROM region WHERE item_id = ? AND parent_id IS NULL AND kind = 'sheet' AND removed_at IS NULL "
                              "AND asset_id IN (SELECT asset_id FROM item_asset WHERE item_id = ? AND role != 'cutout') ORDER BY position", (it['id'], it['id'])).fetchall()
        # la stessa lettera del taglio (a, b, c… fra le parti incluse), cosi' testo e file si ritrovano
        inc = [r['id'] for r in tops if r['export_on']]
        letter = lambda r: ('abcdefghijklmnopqrstuvwxyz'[inc.index(r['id']) % 26] if len(inc) > 1 else '') if r['id'] in inc else '–'
        for r in tops:
            ts = lambda rid: lib.db.execute('SELECT * FROM current_text WHERE region_id = ? ORDER BY created_at DESC LIMIT 1', (rid,)).fetchone()
            main = ts(r['id'])
            areas = [(a, ts(a['id'])) for a in lib.db.execute('SELECT * FROM region WHERE parent_id = ? AND removed_at IS NULL ORDER BY position', (r['id'],))]
            areas = [(a, t) for a, t in areas if t and t['plain'].strip()]
            if not ((main and main['plain'].strip()) or areas):
                continue
            cut = lib.db.execute('SELECT path FROM cut WHERE region_id = ? ORDER BY id DESC LIMIT 1', (r['id'],)).fetchone()
            body = [md_to_tex(main['plain'])] if main and main['plain'].strip() else []
            for k, (a, t) in enumerate(areas):
                body.append(f'\\begin{{scanstudioarea}}{{area {k + 1}}}\n{md_to_tex(t["plain"])}\n\\end{{scanstudioarea}}')
            parts.append(f'\\begin{{scanstudiopart}}{{{letter(r)}}}{{{esc(r["label"] or "")}}}{{{(cut["path"] if cut and os.path.exists(cut["path"]) else "")}}}'
                         f'{{scanstudio://region/{r["uuid"]}}}\n' + '\n'.join(body) + '\n\\end{scanstudiopart}')
        whole = [t for t in lib.db.execute('SELECT * FROM current_text WHERE region_id IS NULL AND asset_id IN (SELECT asset_id FROM item_asset WHERE item_id = ?)', (it['id'],))
                 if t['plain'].strip()]
        if whole:
            parts.insert(0, md_to_tex(whole[-1]['plain']))
        if not parts:
            continue
        name = f'{it["date"] or "undated"} {safe_name(it["title"] or "")}.tex'
        head = (f'% Scan Studio · read-only representation of the library, written {stamp}\n'
                f'% Correct the text in Scan Studio: this file is rewritten.\n% scanstudio://item/{it["uuid"]}\n')
        tex = head + f'\\scanstudioentry{{{esc(it["title"] or "")}}}{{{esc(it["date"] or "")}}}{{{esc(it["series"] or "")}}}{{scanstudio://item/{it["uuid"]}}}\n\n' + '\n\n'.join(parts) + '\n'
        p = os.path.join(out_dir, name)
        if not os.path.exists(p) or open(p, encoding='utf-8').read().split('\n', 1)[1:] != tex.split('\n', 1)[1:]:
            with open(p + '.part', 'w', encoding='utf-8') as f:
                f.write(tex)
            os.replace(p + '.part', p)
        files.append(name)
    # file di oggetti spariti: via dalla cartella (e' una rappresentazione)
    for f in os.listdir(out_dir):
        if f.endswith('.tex') and f not in files and f != 'journal.tex':
            first = open(os.path.join(out_dir, f), encoding='utf-8').readline()
            if first.startswith('% Scan Studio'):
                os.remove(os.path.join(out_dir, f))
    master = ('% Scan Studio journal: every transcription, by date. Read-only, rewritten by Scan Studio.\n'
              '% In your document: \\usepackage{scanstudio} (or your own definitions), then \\input{journal}.\n'
              + ''.join(f'\\input{{{os.path.splitext(f)[0]}}}\n' for f in sorted(files)))
    with open(os.path.join(out_dir, 'journal.tex'), 'w', encoding='utf-8') as f:
        f.write(master)
    sty = os.path.join(out_dir, 'scanstudio.sty')
    if not os.path.exists(sty):                          # la propria versione non si sovrascrive
        with open(sty, 'w', encoding='utf-8') as f:
            f.write(STY)
    lib.log('journal', 'library', lib.meta('uuid'), dir=out_dir, files=len(files))
    return {'dir': out_dir, 'files': len(files)}
