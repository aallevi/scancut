# processo a parte per SAM 3: carica il modello una volta, poi una richiesta JSON per riga.
# Come DigitalSreeni Image Annotator: Ultralytics legge ~/sam3.pt cosi' com'e', niente conversione.
#   {mode: 'text', image, out, prompt, threshold, whole}      -> tutti gli oggetti della frase
#   {mode: 'prompt', image, out, points, labels, boxes}       -> l'oggetto indicato (clic +/-, riquadro)
# risposta: {n, scores} o {error}; le maschere (n, H, W) in out (.npz), alla risoluzione dell'immagine.

import os, sys, json, traceback
import numpy as np


def main(weights):
    # Ultralytics scrive su stdout: le risposte vanno su un canale tutto loro
    out = os.fdopen(os.dup(1), 'w', buffering=1)
    sys.stdout = sys.stderr
    import torch, cv2
    from ultralytics.models.sam import SAM3SemanticPredictor, SAM3Predictor
    dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
    pred = {}

    def get(kind, conf):
        # il modello si costruisce alla prima richiesta di quel tipo e poi resta
        if kind not in pred:
            cls = SAM3SemanticPredictor if kind == 'text' else SAM3Predictor
            pred[kind] = cls(overrides=dict(model=weights, task='segment', conf=conf, device=dev,
                                            save=False, verbose=False))
        p = pred[kind]
        p.args.conf = conf
        return p

    for line in sys.stdin:
        try:
            req = json.loads(line)
            img = cv2.imread(req['image'], cv2.IMREAD_COLOR)      # BGR, come vuole Ultralytics
            if img is None:
                raise ValueError('cannot read image')
            mode = req.get('mode', 'text')
            p = get(mode, float(req.get('threshold', 0.4)))
            p.set_image(img)
            if mode == 'text':
                res = p(text=[req.get('prompt') or 'sheet of paper'])
            else:
                kw = {}
                if req.get('points'):
                    kw['points'] = [req['points']]; kw['labels'] = [req.get('labels') or [1] * len(req['points'])]
                if req.get('boxes'):
                    kw['bboxes'] = req['boxes']
                res = p(**kw)
            r = res[0] if isinstance(res, (list, tuple)) else res
            H, W = img.shape[:2]
            if r.masks is None:
                masks, scores = np.zeros((0, H, W), bool), []
            else:
                masks = r.masks.data.cpu().numpy() > 0.5
                if masks.shape[1:] != (H, W):
                    masks = np.stack([cv2.resize(m.astype(np.uint8), (W, H), interpolation=cv2.INTER_LINEAR) > 0 for m in masks])
                scores = r.boxes.conf.cpu().numpy().tolist() if r.boxes is not None else [1.0] * len(masks)
            if req.get('whole') and len(masks) > 1:
                # dentro un riquadro: un foglio solo, il piu' sicuro
                i = int(np.argmax(scores))
                masks, scores = masks[i:i + 1], scores[i:i + 1]
            np.savez_compressed(req['out'], masks=masks)
            print(json.dumps({'n': len(masks), 'scores': scores}), file=out, flush=True)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({'error': f'{type(e).__name__}: {e}'}), file=out, flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
