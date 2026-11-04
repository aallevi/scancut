# processo a parte per SAM 3: carica il modello una volta, poi una richiesta JSON per riga.
# richiesta: {image, out, prompt, threshold, whole}  ->  risposta: {n, scores} o {error}
# Le maschere (n, H, W) vanno in out (.npz), alla risoluzione della scansione.
# I pesi: ~/sam3-hf (sam3.pt convertito nel formato transformers).

import sys, json, traceback
import numpy as np


def main(model_dir):
    import torch
    from PIL import Image
    from transformers import Sam3Model, Sam3Processor
    Image.MAX_IMAGE_PIXELS = None
    dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
    model = processor = None
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if model is None:
                processor = Sam3Processor.from_pretrained(model_dir)
                model = Sam3Model.from_pretrained(model_dir).to(dev).eval()
            im = Image.open(req['image']).convert('RGB')
            inputs = processor(images=im, text=req.get('prompt') or 'sheet of paper', return_tensors='pt').to(dev)
            with torch.inference_mode():
                outputs = model(**inputs)
            res = processor.post_process_instance_segmentation(
                outputs, threshold=float(req.get('threshold', 0.4)), mask_threshold=0.5,
                target_sizes=[im.size[::-1]])[0]
            masks = res['masks'].cpu().numpy().astype(bool)
            scores = res['scores'].cpu().numpy().tolist()
            if req.get('whole') and len(masks) > 1:
                # dentro un riquadro: un foglio solo, il piu' sicuro
                i = int(np.argmax(scores))
                masks, scores = masks[i:i + 1], scores[i:i + 1]
            np.savez_compressed(req['out'], masks=masks)
            print(json.dumps({'n': len(masks), 'scores': scores}), flush=True)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({'error': f'{type(e).__name__}: {e}'}), flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
