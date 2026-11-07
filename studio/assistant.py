# l'assistente locale e la ricerca dello studio.
# L'aiuto (STUDIO.md, README, motori, i suggerimenti (i) dell'interfaccia) e' diviso in pezzi; una
# domanda trova i pezzi giusti per parole e, se c'e' un modello di embedding, per significato
# (vettori). Un modello piccolo su questo Mac risponde solo da quei pezzi. Parla con qualunque
# server compatibile OpenAI: Ollama (predefinito), LM Studio, llama.cpp, mlx_lm.server, Jan.

import os, re, json, math, time, hashlib, shutil, subprocess, urllib.request, urllib.error

from . import core

SKIP = ('Testing (for Claude)',)          # sezioni per chi sviluppa, non aiuto


# ---------------------------------------------------------------- i pezzi dell'aiuto

def _md_chunks(path, src):
    text = open(path, encoding='utf-8').read()
    out, title, buf = [], src, []

    def flush():
        body = '\n'.join(buf).strip()
        if body and not title.startswith(SKIP):
            # le sezioni lunghe a pezzi di ~1200 caratteri, per paragrafi
            part, n = [], 0
            for para in re.split(r'\n\s*\n', body):
                if part and n + len(para) > 1200:
                    out.append({'title': title, 'text': '\n\n'.join(part), 'src': src}); part, n = [], 0
                part.append(para); n += len(para)
            if part:
                out.append({'title': title, 'text': '\n\n'.join(part), 'src': src})

    for line in text.splitlines():
        m = re.match(r'^#{1,3}\s+(.*)', line)
        if m:
            flush(); title, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    flush()
    return out


def _tips():
    # i testi dei pulsanti (i) dell'interfaccia: const TIPS = { chiave: '...', ... } in app.js
    try:
        js = open(os.path.join(core.REPO, 'studio', 'static', 'app.js'), encoding='utf-8').read()
        block = js[js.index('const TIPS = {'):]
        block = block[:block.index('\n};')]
    except (OSError, ValueError):
        return []
    out = []
    for k, v in re.findall(r"^\s*(\w+):\s*'((?:[^'\\]|\\.)*)'", block, re.M):
        out.append({'title': 'Tip: ' + k, 'text': v.replace("\\'", "'"), 'src': 'interface'})
    return out


def chunks():
    out = []
    for fn, src in (('STUDIO.md', 'Studio guide'), ('README.md', 'Read me')):
        p = os.path.join(core.REPO, fn)
        if os.path.exists(p):
            out += _md_chunks(p, src)
    for e in core.engines():
        lines = [e.get('note') or '']
        for p in e.get('params') or []:
            lines.append(f'{p.get("label", p["id"])}' + (f' ({p["unit"]})' if p.get('unit') else '') + f': {p.get("hint", "")}')
            for c in p.get('choices') or []:
                if c.get('note'):
                    lines.append(f'  {c.get("label") or c["text"]}: {c["note"]}')
        out.append({'title': 'Engine: ' + e['name'], 'text': '\n'.join(l for l in lines if l.strip()), 'src': 'engines'})
    for a in core.addons():
        out.append({'title': 'Add-on: ' + a['name'], 'text': f'{a["line"]} Install: {a["cmd"]}', 'src': 'add-ons'})
    out += _tips()
    for c in out:
        c['id'] = hashlib.sha1((c['title'] + '\0' + c['text']).encode()).hexdigest()[:12]
    return out


# ---------------------------------------------------------------- ricerca per parole (BM25)

def _words(s):
    return re.findall(r'[a-z0-9àèéìòù]+', s.lower())


def keyword_scores(q, docs):
    qw = [w for w in _words(q) if len(w) > 1]
    if not qw:
        return [0.0] * len(docs)
    toks = [_words(d['title'] + ' ' + d['text']) for d in docs]
    avg = sum(map(len, toks)) / max(1, len(toks))
    out = []
    for t in toks:
        s = 0.0
        for w in set(qw):
            f = sum(1 for x in t if x == w or (len(w) > 3 and x.startswith(w)))
            if not f:
                continue
            df = sum(1 for tt in toks if w in tt)
            idf = math.log(1 + (len(toks) - df + 0.5) / (df + 0.5))
            s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(t) / avg))
        out.append(s)
    return out


# ---------------------------------------------------------------- il server del modello

def base_url():
    return (core.settings().get('llm_url') or 'http://localhost:11434/v1').rstrip('/')


def _req(path, body=None, timeout=10, stream=False):
    r = urllib.request.Request(base_url() + path, json.dumps(body).encode() if body is not None else None,
                               {'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(r, timeout=timeout)
    return resp if stream else json.load(resp)


def is_ollama():
    return ':11434' in base_url()


def ollama_root():
    return re.sub(r'/v1$', '', base_url())


def server_up():
    try:
        _req('/models', timeout=2)
        return True
    except Exception:
        return False


def start_ollama():
    # Ollama installato ma non acceso: si accende (resta finche' resta lo studio)
    exe = shutil.which('ollama')
    if not exe or not is_ollama() or server_up():
        return server_up()
    subprocess.Popen([exe, 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=False)
    for _ in range(30):
        time.sleep(0.5)
        if server_up():
            return True
    return False


def models():
    try:
        return sorted(m['id'] for m in _req('/models', timeout=3).get('data', []))
    except Exception:
        return []


# chi risponde e chi fa i vettori, se l'utente non ha scelto: il primo installato di queste liste
ANSWER_PREF = ['gemma3:4b-it-qat', 'gemma3:4b', 'qwen3:4b', 'llama3.2:3b', 'phi4-mini', 'gemma3:1b', 'qwen2.5:1.5b', 'llama3.2:1b']
EMBED_HINTS = ('embed', 'bge', 'e5-', 'gte', 'minilm')
SUGGEST = {'answer': 'gemma3:4b', 'embed': 'embeddinggemma'}


def pick(kind):
    s = core.settings()
    chosen = s.get('llm_model' if kind == 'answer' else 'embed_model')
    ms = models()
    if chosen:
        return chosen if not ms or chosen in ms or any(m.startswith(chosen) for m in ms) else None
    if kind == 'embed':
        return next((m for m in ms if any(h in m.lower() for h in EMBED_HINTS)), None)
    chat = [m for m in ms if not any(h in m.lower() for h in EMBED_HINTS)]
    return next((p for p in ANSWER_PREF if p in chat), None) or next((m for p in ANSWER_PREF for m in chat if m.startswith(p.split(':')[0])), None) \
        or (chat[0] if chat else None)


def status():
    up = server_up() or (bool(shutil.which('ollama')) and is_ollama() and start_ollama())
    return {'url': base_url(), 'up': up, 'ollama': bool(shutil.which('ollama')), 'is_ollama': is_ollama(),
            'models': models() if up else [], 'answer': pick('answer') if up else None,
            'embed': pick('embed') if up else None, 'suggest': SUGGEST}


# ---------------------------------------------------------------- vettori (embedding)

def _index_path():
    return os.path.join(core.DATA, 'help-index.json')


def embed(texts, model):
    r = _req('/embeddings', {'model': model, 'input': texts}, timeout=120)
    return [d['embedding'] for d in sorted(r['data'], key=lambda d: d['index'])]


def vectors(docs, model):
    # i vettori dei pezzi, ricalcolati solo per i pezzi cambiati
    try:
        idx = json.load(open(_index_path()))
    except (OSError, ValueError):
        idx = {}
    if idx.get('model') != model:
        idx = {'model': model, 'vec': {}}
    todo = [d for d in docs if d['id'] not in idx['vec']]
    for i in range(0, len(todo), 32):
        part = todo[i:i + 32]
        for d, v in zip(part, embed([d['title'] + '\n' + d['text'] for d in part], model)):
            idx['vec'][d['id']] = v
    if todo:
        idx['vec'] = {d['id']: idx['vec'][d['id']] for d in docs}
        tmp = _index_path() + '.part'
        json.dump(idx, open(tmp, 'w'))
        os.replace(tmp, _index_path())
    return [idx['vec'][d['id']] for d in docs]


def _cos(a, b):
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def find(q, k=6):
    # i pezzi d'aiuto per una domanda: parole, piu' significato se c'e' un modello di embedding
    docs = chunks()
    kw = keyword_scores(q, docs)
    top = max(kw) or 1.0
    score = [s / top for s in kw]
    how = 'words'
    model = pick('embed') if server_up() else None
    if model:
        try:
            vs = vectors(docs, model)
            qv = embed([q], model)[0]
            score = [0.4 * s + 0.6 * max(0.0, _cos(qv, v)) for s, v in zip(score, vs)]
            how = 'words + meaning'
        except Exception:
            pass
    order = sorted(range(len(docs)), key=lambda i: -score[i])
    return [dict(docs[i], score=round(score[i], 3)) for i in order[:k] if score[i] > 0], how


# ---------------------------------------------------------------- la risposta

SYSTEM = ('You are the help assistant inside Scan Studio, a Mac app that cuts scanned drawings out of '
          'their background. Answer the user\'s question using ONLY the help sections given. Be short and '
          'concrete, 1 to 4 sentences: name the menu, button, tool or shortcut. If the sections do not contain the answer, say '
          'so and suggest Ask Claude. Never invent features.')


def answer(q, history=None, on_text=None):
    if not server_up() and not start_ollama():
        raise RuntimeError('no local model server: install Ollama (Add-ons) or set the server address in Settings')
    model = pick('answer')
    if not model:
        raise RuntimeError('no answering model installed: download one in Add-ons › Local assistant')
    hits, how = find(q)
    ctx = '\n\n'.join(f'[{i + 1}] {h["title"]} ({h["src"]})\n{h["text"]}' for i, h in enumerate(hits))
    msgs = [{'role': 'system', 'content': SYSTEM}] + (history or [])[-6:] + \
           [{'role': 'user', 'content': f'Help sections:\n{ctx}\n\nQuestion: {q}'}]
    resp = _req('/chat/completions', {'model': model, 'messages': msgs, 'stream': True, 'temperature': 0.2}, timeout=300, stream=True)
    text = ''
    for line in resp:
        line = line.decode('utf-8', 'replace').strip()
        if not line.startswith('data:') or line == 'data: [DONE]':
            continue
        try:
            delta = json.loads(line[5:])['choices'][0].get('delta', {}).get('content') or ''
        except (ValueError, KeyError, IndexError):
            continue
        text += delta
        if on_text:
            on_text(text)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()     # modelli che "pensano" ad alta voce
    return {'text': text, 'model': model, 'how': how, 'sources': [{'title': h['title'], 'src': h['src']} for h in hits]}


def pull(model, progress=None):
    # scarica un modello in Ollama (API sua): avanzamento vero, byte scaricati su byte totali
    r = urllib.request.Request(ollama_root() + '/api/pull', json.dumps({'model': model, 'stream': True}).encode(),
                               {'Content-Type': 'application/json'})
    last, parts = '', {}
    for line in urllib.request.urlopen(r, timeout=3600):
        ev = json.loads(line)
        if ev.get('error'):
            raise RuntimeError(ev['error'])
        st = ev.get('status', '')
        if ev.get('total') and ev.get('digest'):
            # il modello arriva a pezzi (pesi, modello del testo, licenza...): l'avanzamento e' sul totale
            parts[ev['digest']] = (ev.get('completed', 0), ev['total'])
        if progress and parts:
            done, tot = sum(c for c, _ in parts.values()), sum(t for _, t in parts.values())
            progress('downloading' if st.startswith('pulling') else st, done / tot * 100)
        elif progress and st != last:
            progress(st, None)
        last = st
    return True


# ---------------------------------------------------------------- la ricerca dello studio

def search(q, limit=8):
    # scansioni e ritagli per nome (tutte le cartelle), etichette e testo letto (OCR), argomenti d'aiuto
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
    sd = os.path.join(core.DATA, 'state')
    for f in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        try:
            st = json.load(open(os.path.join(sd, f)))
        except (OSError, ValueError):
            continue
        for sh in st.get('sheets', []):
            hay = ((sh.get('label') or '') + '\n' + (sh.get('ocr') or '')).lower()
            if all(w in hay for w in words):
                i = hay.find(words[0])
                out['text'].append({'rel': st['rel'], 'sheet': sh['id'], 'label': sh.get('label') or '',
                                    'snippet': hay[max(0, i - 40): i + 80].replace('\n', ' ')})
        if len(out['text']) >= limit:
            break
    hits, _ = find(q, k=5) if len(q) > 2 else ([], '')
    out['help'] = [{'title': h['title'], 'src': h['src'], 'snippet': h['text'][:140]} for h in hits if h['score'] > 0.15]
    return out


# ---------------------------------------------------------------- testo (OCR) con un modello che vede
# GLM-OCR o Qwen3-VL in Ollama leggono anche la scrittura a mano e tengono la forma (Markdown).
# Solo lettura: i pixel del ritaglio non cambiano.

OCR_MODELS = [
    {'model': 'glm-ocr', 'name': 'GLM-OCR', 'mb': 1800, 'line': 'Recommended. Small document model: handwriting and print, keeps headings, lists and tables (Markdown).'},
    {'model': 'qwen3-vl:8b', 'name': 'Qwen3-VL 8B', 'mb': 6100, 'line': 'For difficult handwriting. Larger and slower (about 6 GB in memory).'},
]
OCR_PROMPT = ('Transcribe all the text in this image exactly as written, including handwriting. The text may mix '
              'several languages, even inside one sentence: keep every word in its own language and spelling, never '
              'translate or correct. Keep the layout as Markdown: line breaks, headings, lists, tables. Write [?] for '
              'words you cannot read. Output only the text.')


def _strips(im, max_ratio=0.7):
    # una pagina alta a strisce, tagliate dove fra le righe non c'e' inchiostro (niente righe spezzate)
    import numpy as np
    w, h = im.size
    n = max(1, int(np.ceil(h / (w * max_ratio))))
    if n == 1:
        return [im]
    g = np.asarray(im.convert('L'), np.float32)
    ink = (g < g.mean() - 40).sum(1).astype(np.float32)          # pixel scuri per riga
    cuts, step = [0], h / n
    for k in range(1, n):
        c, win = int(k * step), int(0.12 * step)
        lo, hi = max(cuts[-1] + 1, c - win), min(h - 1, c + win)
        cuts.append(lo + int(np.argmin(ink[lo:hi])) if hi > lo else c)
    cuts.append(h)
    return [im.crop((0, a, w, b)) for a, b in zip(cuts, cuts[1:]) if b - a > 8]


def _unloop(text):
    # un modello che si incanta ripete lo stesso pezzetto all'infinito: resta una volta sola
    text = re.sub(r'(.{1,12}?)\1{12,}', r'\1 […]', text, flags=re.S)
    out, last = [], None
    for line in text.splitlines():
        if line.strip() and line == last:
            continue
        out.append(line); last = line
    return '\n'.join(out)


def _ocr_one(im, model, prompt):
    import base64, io
    b = io.BytesIO(); im.save(b, 'PNG')
    b64 = base64.b64encode(b.getvalue()).decode()
    if is_ollama():
        # API propria di Ollama: contesto largo per immagine + testo, risposta limitata, niente ripetizioni
        r = urllib.request.urlopen(urllib.request.Request(ollama_root() + '/api/chat', json.dumps({
            'model': model, 'stream': False, 'messages': [{'role': 'user', 'content': prompt, 'images': [b64]}],
            'keep_alive': '10m',                       # come SAM: resta pronto 10 minuti, poi si libera la memoria
            'options': {'temperature': 0, 'num_ctx': 16384, 'num_predict': 1400, 'repeat_penalty': 1.15}}).encode(),
            {'Content-Type': 'application/json'}), timeout=900)
        text = json.load(r)['message']['content'] or ''
    else:
        r = _req('/chat/completions', {'model': model, 'temperature': 0, 'max_tokens': 1400, 'frequency_penalty': 0.3,
                                      'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt},
                                      {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b64}}]}]}, timeout=900)
        text = r['choices'][0]['message']['content'] or ''
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S)
    text = re.sub(r'^```(?:markdown)?\s*|\s*```$', '', text.strip())
    return _unloop(text.strip())


def ocr_image(path, model, progress=None):
    from PIL import Image
    im = Image.open(path)
    if im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info:
        bg = Image.new('RGB', im.size, (255, 255, 255))           # il trasparente diventa bianco (solo per leggere)
        bg.paste(im.convert('RGBA'), mask=im.convert('RGBA').split()[3]); im = bg
    im = im.convert('RGB')
    if im.width > 1600:
        im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
    prompt = 'Text Recognition:' if model.startswith('glm-ocr') else OCR_PROMPT
    if not server_up() and not start_ollama():
        raise RuntimeError('the local model server is not running (Add-ons › Local assistant)')
    parts = _strips(im)
    out = []
    for i, part in enumerate(parts):
        out.append(_ocr_one(part, model, prompt))
        if progress:
            progress(i + 1, len(parts))
    return '\n\n'.join(t for t in out if t)


def addon_rows():
    # le righe della pagina Add-ons: il server dei modelli, chi risponde, i vettori, l'OCR
    st = status()
    have = set(st['models'])
    inst = lambda m: m in have or any(x.split(':')[0] == m and x.endswith(':latest') for x in have) or any(x == m + ':latest' for x in have)
    ocr = core.settings().get('ocr_engine') or 'vision'
    rows = [{'id': 'ollama', 'name': 'Model server', 'group': 'Local assistant', 'ok': st['up'],
             'line': ('Running at ' + st['url'] + '.') if st['up'] else
                     'Ollama (or LM Studio, llama.cpp, any OpenAI-compatible server; address in Settings) runs the small models on this Mac.',
             'cmd': 'brew install ollama   ·   or the app from ollama.com/download', 'link': 'https://ollama.com/download',
             'blocked': None if (core.brew() or st['ollama']) else 'Install the Ollama app from ollama.com/download'}]
    if st['up'] and st['is_ollama']:
        rows += [
            {'id': 'pull:' + SUGGEST['answer'], 'name': 'Answering model', 'group': 'Local assistant',
             'ok': bool(st['answer']), 'line': (f'Using {st["answer"]}.' if st['answer'] else f'{SUGGEST["answer"]}, about 3 GB: answers Help questions.'),
             'cmd': f'ollama pull {SUGGEST["answer"]}'},
            {'id': 'pull:' + SUGGEST['embed'], 'name': 'Search by meaning', 'group': 'Local assistant',
             'ok': bool(st['embed']), 'line': (f'Using {st["embed"]}.' if st['embed'] else f'{SUGGEST["embed"]}, about 600 MB: finds help by meaning, not only by words.'),
             'cmd': f'ollama pull {SUGGEST["embed"]}'},
        ]
    rows.append({'id': 'ocr:vision', 'name': 'Apple Vision', 'group': 'Text (OCR)', 'ok': os.path.exists(core.OCR),
                 'line': 'Built into macOS, instant. Printed text and neat handwriting; no layout.', 'cmd': 'studio/ocr (Apple Vision helpers)',
                 'use': {'ocr_engine': 'vision'}, 'inuse': ocr == 'vision'})
    for m in OCR_MODELS:
        rows.append({'id': 'pull:' + m['model'], 'name': m['name'], 'group': 'Text (OCR)', 'ok': inst(m['model']),
                     'line': f'{m["line"]} About {m["mb"] / 1000:.1f} GB.', 'cmd': f'ollama pull {m["model"]}',
                     'blocked': None if st['up'] and st['is_ollama'] else 'Needs the model server (Ollama) above',
                     'use': {'ocr_engine': 'ollama:' + m['model']}, 'inuse': ocr == 'ollama:' + m['model']})
    return rows


def unload_ocr():
    # libera subito la memoria del modello che legge (come "Unload SAM 3")
    eng = core.settings().get('ocr_engine') or ''
    if eng.startswith('ollama:') and is_ollama() and server_up():
        try:
            urllib.request.urlopen(urllib.request.Request(ollama_root() + '/api/generate', json.dumps(
                {'model': eng[7:], 'keep_alive': 0}).encode(), {'Content-Type': 'application/json'}), timeout=20).read()
        except Exception:
            pass
