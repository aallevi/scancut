# lettore di testo su MLX (GPU Apple), in un processo suo e nel suo Python (envs/mlx-vlm): Unlimited-OCR.
# Una richiesta per riga su stdin ({"image", "model", "prompt", "max_tokens"}), una risposta per riga su
# stdout ({"text"} o {"error"}). Il modello resta caricato finche' il processo vive.
import sys, json

# le risposte su un canale tutto loro: quel che le librerie stampano (caricando il modello) va nel registro
_out, sys.stdout = sys.stdout, sys.stderr
_loaded = {}


def model(repo):
    if repo not in _loaded:
        from mlx_vlm import load
        _loaded.clear()
        _loaded[repo] = load(repo)
    return _loaded[repo]


def read(req):
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template
    m, proc = model(req['model'])
    prompt = apply_chat_template(proc, m.config, req.get('prompt') or 'document parsing.', num_images=1)
    kw = dict(image=[req['image']], max_tokens=int(req.get('max_tokens') or 2000), temperature=0.0, verbose=False)
    try:
        r = generate(m, proc, prompt, repetition_penalty=1.05, **kw)
    except TypeError:
        r = generate(m, proc, prompt, **kw)
    return getattr(r, 'text', r)


for line in sys.stdin:
    try:
        print(json.dumps({'text': read(json.loads(line))}), file=_out, flush=True)
    except Exception as e:
        print(json.dumps({'error': f'{type(e).__name__}: {e}'}), file=_out, flush=True)
