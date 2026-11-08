# i lettori di testo che girano in un server di modelli su questo Mac (Ollama, predefinito, o qualunque
# server compatibile OpenAI): GLM-OCR, Qwen3-VL. Scaricarli, accenderli, leggere, liberare la memoria.

import os, re, sys, json, glob, time, shutil, threading, subprocess, urllib.request, urllib.error

from . import core


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
        raise RuntimeError('the local model server is not running (Add-ons › Text (OCR))')
    parts = _strips(im)
    out = []
    for i, part in enumerate(parts):
        out.append(_ocr_one(part, model, prompt))
        if progress:
            progress(i + 1, len(parts))
    return '\n\n'.join(t for t in out if t)


# ---------------------------------------------------------------- lettori su MLX (GPU Apple), nel loro Python
# Unlimited-OCR: documenti stampati con la loro impaginazione (un riquadro per titolo, testo, figura).
# Il suo Python (mlx-vlm) sta una volta per Mac, fuori dallo studio: i pacchetti dello studio non cambiano.

MLX_MODELS = [
    {'id': 'unlimited-ocr', 'repo': 'mlx-community/Unlimited-OCR-8bit', 'name': 'Unlimited-OCR', 'mb': 3700, 'prompt': 'document parsing.',
     'line': 'Printed documents with their layout: a box for every title, text block and picture, so the side-by-side view places '
             'them where they are. Not for handwriting (use GLM-OCR). Runs on the Apple GPU, about 3 GB in memory.'},
]
MLX_IDLE_S = 600
_mlx, _mlx_used, _mlx_lock = None, 0.0, threading.Lock()


def mlx_env():
    return os.path.expanduser('~/Library/Application Support/Scan Studio/envs/mlx-vlm')


def mlx_python():
    p = os.path.join(mlx_env(), 'bin', 'python')
    return p if os.path.exists(p) else None


def hf_cached(repo):
    # il modello gia' nella cache di Hugging Face (anche scaricato da altri programmi: non si riscarica)
    hub = os.path.join(os.environ.get('HF_HOME') or os.path.expanduser('~/.cache/huggingface'), 'hub')
    d = os.path.join(hub, 'models--' + repo.replace('/', '--'), 'snapshots')
    return any(glob.glob(os.path.join(d, '*', '*.safetensors')))


def mlx_ready(mid):
    m = next(x for x in MLX_MODELS if x['id'] == mid)
    return bool(mlx_python()) and hf_cached(m['repo'])


def mlx_install_cmds(mid):
    # i passi dell'installazione (Add-ons): il Python suo (uv se c'e', piu' veloce), mlx-vlm, il modello
    m = next(x for x in MLX_MODELS if x['id'] == mid)
    env, uv = mlx_env(), shutil.which('uv') or next((p for p in (os.path.expanduser('~/.local/bin/uv'), '/opt/homebrew/bin/uv') if os.path.exists(p)), None)
    py = os.path.join(env, 'bin', 'python')
    cmds = []
    if not mlx_python():
        os.makedirs(os.path.dirname(env), exist_ok=True)
        cmds += [[uv, 'venv', '-q', '-p', '3.12', env], [uv, 'pip', 'install', '-q', '-p', py, 'mlx-vlm>=0.6.8', 'huggingface_hub']] if uv else \
                [[sys.executable, '-m', 'venv', env], [py, '-m', 'pip', 'install', '-q', 'mlx-vlm>=0.6.8', 'huggingface_hub']]
    if not hf_cached(m['repo']):
        cmds.append([py, '-c', 'import sys\nfrom huggingface_hub import snapshot_download\nprint("saved", snapshot_download(sys.argv[1]))', m['repo']])
    return cmds


def _mlx_watch():
    while True:
        time.sleep(30)
        if _mlx is not None and _mlx.poll() is None and time.time() - _mlx_used > MLX_IDLE_S:
            mlx_unload()


threading.Thread(target=_mlx_watch, daemon=True).start()


def mlx_unload():
    global _mlx
    with _mlx_lock:
        if _mlx is not None and _mlx.poll() is None:
            _mlx.stdin.close()
            try:
                _mlx.wait(10)
            except subprocess.TimeoutExpired:
                _mlx.kill()
        _mlx = None


def layout_to_md(raw):
    # "<|det|>title [x0, y0, x1, y1]<|/det|>testo" (coordinate su 0-999): titoli come #, figure come segno
    # che la vista affiancata riempie con i pixel veri, il resto paragrafi
    out, fig = [], 0
    for kind, box, body in re.findall(r'<\|det\|>\s*(\w+)\s*\[([\d,\s]+)\]\s*<\|/det\|>(.*?)(?=<\|det\||\Z)', raw, re.S):
        body = body.strip()
        b = [int(v) for v in box.replace(' ', '').split(',')[:4]]
        if kind in ('image', 'figure', 'picture'):
            fig += 1
            out.append(f'![image](image_{fig}.png){",".join(str(v) for v in b)}')
        elif kind in ('title', 'heading', 'header') and body:
            out.append('# ' + body.replace('\n', ' '))
        elif body:
            out.append(body)
    if not out:
        out = [re.sub(r'<\|/?det\|>', '', raw).strip()]
    return _unloop('\n\n'.join(out))


def ocr_mlx(path, mid, progress=None):
    global _mlx, _mlx_used
    from PIL import Image
    m = next(x for x in MLX_MODELS if x['id'] == mid)
    if not mlx_ready(mid):
        raise RuntimeError(f'{m["name"]} is not installed (Add-ons › Text (OCR))')
    im = Image.open(path)
    if im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info:
        bg = Image.new('RGB', im.size, (255, 255, 255))           # il trasparente diventa bianco (solo per leggere)
        bg.paste(im.convert('RGBA'), mask=im.convert('RGBA').split()[3]); im = bg
    im = im.convert('RGB')
    if max(im.size) > 2048:
        k = 2048 / max(im.size); im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    tmp = os.path.join(core.DATA, 'cache', f'.mlx-{os.getpid()}-{threading.get_ident()}.png')
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    im.save(tmp)
    try:
        with _mlx_lock:
            _mlx_used = time.time()
            if _mlx is None or _mlx.poll() is not None:
                _mlx = subprocess.Popen([mlx_python(), '-I', os.path.join(core.REPO, 'studio', 'mlx_ocr_worker.py')],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
                                        env=dict(os.environ, HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false'))
            _mlx.stdin.write(json.dumps({'image': tmp, 'model': m['repo'], 'prompt': m['prompt']}) + '\n'); _mlx.stdin.flush()
            line = _mlx.stdout.readline()
        _mlx_used = time.time()
    finally:
        os.remove(tmp)
    if not line:
        raise RuntimeError(f'{m["name"]} stopped (see the server log)')
    res = json.loads(line)
    if 'error' in res:
        raise RuntimeError(f'{m["name"]}: {res["error"]}')
    if progress:
        progress(1, 1)
    return layout_to_md(res['text'])


def addon_rows():
    # le righe della pagina Add-ons: il server dei modelli e i lettori
    up = server_up()
    st = {'up': up, 'url': base_url(), 'ollama': bool(shutil.which('ollama')), 'is_ollama': is_ollama(), 'models': models() if up else []}
    have = set(st['models'])
    inst = lambda m: m in have or any(x.split(':')[0] == m and x.endswith(':latest') for x in have) or any(x == m + ':latest' for x in have)
    ocr = core.settings().get('ocr_engine') or 'vision'
    rows = [{'id': 'ollama', 'name': 'Model server', 'group': 'Text (OCR)', 'ok': st['up'],
             'line': ('Running at ' + st['url'] + '.') if st['up'] else
                     'Ollama (or any OpenAI-compatible server; address in Settings) runs the downloaded readers on this Mac.',
             'cmd': 'brew install ollama   ·   or the app from ollama.com/download', 'link': 'https://ollama.com/download',
             'blocked': None if (core.brew() or st['ollama']) else 'Install the Ollama app from ollama.com/download'}]
    rows.append({'id': 'ocr:vision', 'name': 'Apple Vision', 'group': 'Text (OCR)', 'ok': os.path.exists(core.OCR),
                 'line': 'Built into macOS, instant. Printed text and neat handwriting; no layout.', 'cmd': 'studio/ocr (Apple Vision helpers)',
                 'use': {'ocr_engine': 'vision'}, 'inuse': ocr == 'vision'})
    for m in OCR_MODELS:
        rows.append({'id': 'pull:' + m['model'], 'name': m['name'], 'group': 'Text (OCR)', 'ok': inst(m['model']),
                     'line': f'{m["line"]} About {m["mb"] / 1000:.1f} GB.', 'cmd': f'ollama pull {m["model"]}',
                     'blocked': None if st['up'] and st['is_ollama'] else 'Needs the model server (Ollama) above',
                     'use': {'ocr_engine': 'ollama:' + m['model']}, 'inuse': ocr == 'ollama:' + m['model']})
    for m in MLX_MODELS:
        rows.append({'id': 'mlx:' + m['id'], 'name': m['name'], 'group': 'Text (OCR)', 'ok': mlx_ready(m['id']),
                     'line': f'{m["line"]} About {m["mb"] / 1000:.1f} GB (not downloaded again if already on this Mac).',
                     'cmd': f'its own Python with mlx-vlm · hf download {m["repo"]}', 'link': f'https://huggingface.co/{m["repo"]}',
                     'path': mlx_env() if mlx_python() else None, 'blocked': None,
                     'use': {'ocr_engine': 'mlx:' + m['id']}, 'inuse': ocr == 'mlx:' + m['id']})
    return rows


def unload_ocr():
    # libera subito la memoria del modello che legge (come "Unload SAM 3")
    mlx_unload()
    eng = core.settings().get('ocr_engine') or ''
    if eng.startswith('ollama:') and is_ollama() and server_up():
        try:
            urllib.request.urlopen(urllib.request.Request(ollama_root() + '/api/generate', json.dumps(
                {'model': eng[7:], 'keep_alive': 0}).encode(), {'Content-Type': 'application/json'}), timeout=20).read()
        except Exception:
            pass
