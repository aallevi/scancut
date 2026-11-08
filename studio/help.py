# l'aiuto dello studio (come la finestra Aiuto di Affinity): capitoli in studio/help/*.md, divisi in
# sezioni; un indice a sinistra, l'articolo a destra, la ricerca per parole. E la ricerca dello studio
# (sorgenti e tagli per nome, parti per nome e testo, argomenti d'aiuto) per la casella in alto.

import os, re, math

from . import core

HELP_DIR = os.path.join(os.path.dirname(__file__), 'help')


def chapters():
    # [{id, title, sections: [{id, title, md}]}], nell'ordine dei file
    out = []
    for f in sorted(os.listdir(HELP_DIR)):
        if not f.endswith('.md'):
            continue
        text = open(os.path.join(HELP_DIR, f), encoding='utf-8').read()
        cid = re.sub(r'^\d+[a-z]?-', '', f[:-3])
        title, secs, cur = cid, [], {'id': cid, 'title': '', 'md': []}
        for line in text.splitlines():
            m = re.match(r'^(#{1,2})\s+(.*)', line)
            if m and m.group(1) == '#':
                title = m.group(2).strip()
            elif m:
                secs.append(cur)
                cur = {'id': cid + '/' + re.sub(r'[^a-z0-9]+', '-', m.group(2).lower()).strip('-'), 'title': m.group(2).strip(), 'md': []}
            else:
                cur['md'].append(line)
        secs.append(cur)
        secs = [dict(s, md='\n'.join(s['md']).strip()) for s in secs]
        out.append({'id': cid, 'title': title, 'sections': [s for s in secs if s['md'] or s['title']]})
    return out


def _words(s):
    return re.findall(r'[a-z0-9àèéìòù]+', s.lower())


# parole che non dicono niente della domanda (come, cosa, il...): con loro vince il testo piu' corto
STOP = set('a an and are as at be but by can could do does doing did for from has have how i if in into is it its me my '
           'of on or so than that the then there these this to was what when where which who why will with would you your '
           'come cosa che il lo la le gli un una per con di da del della e non si'.split())


def keyword_scores(q, docs):
    # BM25 sui testi (titolo compreso); il titolo conta di piu'
    qw = [w for w in _words(q) if len(w) > 1 and w not in STOP]
    if not qw:
        return [0.0] * len(docs)
    toks = [_words(d['title'] + ' ' + d['title'] + ' ' + d['text']) for d in docs]
    avg = sum(map(len, toks)) / max(1, len(toks))
    out = []
    for t in toks:
        s = 0.0
        for w in set(qw):
            f = sum(1 for x in t if x == w or (len(w) > 3 and x.startswith(w)))
            if not f:
                continue
            df = sum(1 for tt in toks if any(x == w or (len(w) > 3 and x.startswith(w)) for x in tt))
            idf = math.log(1 + (len(toks) - df + 0.5) / (df + 0.5))
            s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(t) / avg))
        out.append(s)
    return out


def _plain(md):
    # il testo senza segni di Markdown (per gli estratti dei risultati)
    t = re.sub(r'^\|?[-| :]+\|?$', ' ', md, flags=re.M)
    t = re.sub(r'[*_`#>|]+', ' ', t)
    t = re.sub(r'^\s*(-|\d+\.)\s+', '', t, flags=re.M)
    return re.sub(r'\s+', ' ', t).strip()


def find(q, k=8):
    # le sezioni d'aiuto per una ricerca: [{chapter, id, title, snippet, text, score}]
    docs = [{'chapter': c['title'], 'id': s['id'], 'title': s['title'] or c['title'], 'text': s['md']}
            for c in chapters() for s in c['sections']]
    sc = keyword_scores(q, docs)
    top = max(sc) if sc and max(sc) > 0 else 1.0
    order = sorted(range(len(docs)), key=lambda i: -sc[i])
    out = []
    for i in order[:k]:
        if sc[i] <= 0:
            break
        d = docs[i]
        w = next((w for w in _words(q) if w not in STOP and w in d['text'].lower()), '')
        j = d['text'].lower().find(w) if w else 0
        plain = _plain(d['text'])
        j = plain.lower().find(w) if w else 0
        out.append(dict(d, score=round(sc[i] / top, 3), snippet=plain[max(0, j - 50): j + 110].strip()))
    return out


def search(q, limit=8):
    # la casella in alto: sorgenti e tagli per nome (tutte le cartelle), parti per nome e testo, aiuto
    words = _words(q)
    out = {'files': [], 'text': [], 'help': []}
    if not words:
        return out
    for top in ('originals', 'cut', 'failed', 'inbox'):
        d = os.path.join(core.ROOT, top)
        for base, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith('.')]
            for f in files:
                if core.is_image(f) and all(w in f.lower() for w in words):
                    out['files'].append({'rel': os.path.relpath(os.path.join(base, f), core.ROOT), 'name': f})
            if len(out['files']) >= limit * 3:
                break
    out['files'] = sorted(out['files'], key=lambda x: (not x['rel'].startswith('originals'), x['name'].lower()))[:limit]
    # etichette e testi: dalla libreria (le parti delle fonti e i loro testi, con le correzioni)
    from .library import bridge
    lib = bridge.library(create=False)
    if lib:
        rows = lib.db.execute(
            "SELECT r.label, json_extract(r.source, '$.studio_rel') AS rel, json_extract(r.source, '$.studio_id') AS sid, "
            "COALESCE((SELECT plain FROM current_text t WHERE t.region_id = r.id ORDER BY created_at DESC LIMIT 1), '') AS txt "
            "FROM region r WHERE r.parent_id IS NULL AND r.kind = 'sheet' AND r.removed_at IS NULL").fetchall()
        for r in rows:
            hay = ((r['label'] or '') + '\n' + (r['txt'] or '')).lower()
            if r['rel'] and all(w in hay for w in words):
                i = hay.find(words[0])
                out['text'].append({'rel': r['rel'], 'sheet': r['sid'], 'label': r['label'] or '',
                                    'snippet': hay[max(0, i - 40): i + 80].replace('\n', ' ')})
                if len(out['text']) >= limit:
                    break
    if len(q) > 2:
        out['help'] = [{'id': h['id'], 'title': h['title'], 'chapter': h['chapter'], 'snippet': h['snippet']} for h in find(q, k=5) if h['score'] > 0.2]
    return out
