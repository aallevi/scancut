# processo a parte per i modelli "togli lo sfondo" della famiglia BiRefNet (BiRefNet, lite, HR,
# RMBG-2.0): tutti si caricano allo stesso modo. Un modello alla volta, una richiesta JSON per riga.
#   {image, out, model, size}  -> in out (.npz) 'alpha': uint8 (H, W), quanto ogni pixel e' soggetto
# risposta: {ok: true} o {error}

import os, sys, json, traceback
import numpy as np


def main():
    out = os.fdopen(os.dup(1), 'w', buffering=1)       # transformers scrive su stdout
    sys.stdout = sys.stderr
    import torch, cv2
    from transformers import AutoModelForImageSegmentation
    dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
    cur = {}
    mean, std = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if req['model'] not in cur:
                cur.clear()
                import gc; gc.collect()
                if dev == 'mps':
                    torch.mps.empty_cache()
                m = AutoModelForImageSegmentation.from_pretrained(req['model'], trust_remote_code=True)
                cur[req['model']] = m.to(dev).eval()
            net = cur[req['model']]
            img = cv2.imread(req['image'], cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
            if img is None:
                raise ValueError('cannot read image')
            H, W = img.shape[:2]
            s = int(req.get('size', 1024))
            x = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (s, s), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
            x = torch.from_numpy(((x - mean) / std).transpose(2, 0, 1)[None]).to(dev)
            with torch.no_grad():
                p = net(x)[-1].sigmoid()[0, 0].float().cpu().numpy()
            a = cv2.resize(p, (W, H), interpolation=cv2.INTER_LINEAR)
            np.savez_compressed(req['out'], alpha=(a * 255).round().clip(0, 255).astype(np.uint8))
            print(json.dumps({'ok': True}), file=out, flush=True)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({'error': f'{type(e).__name__}: {e}'}), file=out, flush=True)


if __name__ == '__main__':
    main()
