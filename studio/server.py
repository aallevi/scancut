# server locale dello studio: l'interfaccia (static/) e un'API JSON che usano
# anche i lavori senza finestra e Claude. Solo 127.0.0.1.

import os, io, sys, json, time, threading, traceback, subprocess, uuid, queue, urllib.parse, shutil
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import numpy as np, cv2
from PIL import Image

from . import core, scanner

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
PORT = 8765


# ---------------------------------------------------------------- lavori in coda

class Jobs:
    def __init__(self):
        self.jobs, self.q = {}, queue.Queue()
        self.claude_session = None
        threading.Thread(target=self.loop, daemon=True).start()

    def add(self, kind, **args):
        # passi veri per la barra: un batch con export conta rilevamento ed export di ogni scansione
        n = len(args.get('rels', [])) or 1
        j = {'id': uuid.uuid4().hex[:8], 'kind': kind, 'args': args, 'status': 'queued', 'done': 0,
             'total': n * (2 if kind == 'batch' and args.get('export') else 1), 'log': [], 'created': time.time(),
             'result': None, 'current': ''}
        self.jobs[j['id']] = j
        self.q.put(j['id'])
        return j

    def public(self, j):
        # il token di Hugging Face non esce mai dal server
        return {k: ({a: v for a, v in j['args'].items() if a != 'token'} if k == 'args' else v) for k, v in j.items() if k != 'proc'}

    def loop(self):
        while True:
            j = self.jobs[self.q.get()]
            if j['status'] == 'cancelled':
                continue
            j['status'] = 'running'; j['started'] = time.time()
            say = lambda m: j['log'].append(m)
            try:
                getattr(self, 'do_' + j['kind'])(j, say)
                if j['status'] == 'running':
                    j['status'] = 'done'
            except Exception as e:
                say(f'ERROR {type(e).__name__}: {e}')
                traceback.print_exc()
                j['status'] = 'failed'
            j['finished'] = time.time()

    def do_batch(self, j, say):
        a = j['args']
        for rel in a['rels']:
            if j['status'] == 'cancelled':
                break
            start = j['done']
            try:
                j['current'] = os.path.basename(rel) + ' · detect'
                st, meta = core.detect(rel, a.get('engine', 'auto'), a.get('params') or {})
                n = len(st['sheets'])
                say(f'{rel}: {n} sheet(s) with {a.get("engine", "auto")} in {meta.get("seconds")}s')
                j['done'] += 1
                if a.get('export') and n:
                    j['current'] = os.path.basename(rel) + ' · export'
                    for w in core.export(rel, log=say):
                        say(f'  {w["status"]}: {os.path.relpath(w["path"], core.ROOT)}')
            except Exception as e:
                say(f'{rel}: ERROR {e}')
            j['done'] = start + (2 if a.get('export') else 1)

    def do_preview(self, j, say):
        # anteprima del letto intero, veloce (75 dpi): per scegliere le aree
        # con un'area: la stessa anteprima solo li', a 300 dpi, per piazzare l'area con precisione
        dev, area = j['args']['dev'], j['args'].get('area')
        d = os.path.join(core.DATA, 'scanner'); os.makedirs(d, exist_ok=True)
        tif = os.path.join(d, 'preview.tif')
        def prog(p): j['pct'] = p
        scanner.scan(dev, tif, 300 if area else 75, 'Color', area=tuple(area[:4]) if area else None,
                     progress=prog, cancelled=lambda: j['status'] == 'cancelled')
        Image.open(tif).convert('RGB').save(os.path.join(d, 'preview-area.png' if area else 'preview.png'))
        if area:
            with open(os.path.join(d, 'preview-area.json'), 'w') as f:
                json.dump({'area': area[:4]}, f)
        os.remove(tif)
        j['done'] = 1
        say('preview ready')

    def do_scan(self, j, say):
        # una scansione per area, nell'inbox: l'agente le sposta in originals/ e le ritaglia
        a = j['args']
        areas = a.get('areas') or [None]
        batch = core.sc.clean_stem(a.get('batch') or 'scan')
        for k, area in enumerate(areas):
            if j['status'] == 'cancelled':
                break
            out = next_scan_name(batch)
            def prog(p, k=k): j['pct'] = (k + p / 100) / len(areas) * 100
            own = area[4] if area and len(area) > 4 and isinstance(area[4], dict) else {}
            res, mode = int(own.get('res') or a['res']), own.get('mode') or a['mode']      # le impostazioni dell'area, se ne ha
            say(f'scanning {os.path.basename(out)} at {res} dpi, {mode}' + (f', area {area[2]:.0f} x {area[3]:.0f} mm' if area else ', whole bed'))
            scanner.scan(a['dev'], out, res, mode, area=tuple(area[:4]) if area else None,
                         progress=prog, cancelled=lambda: j['status'] == 'cancelled')
            say(f'  -> inbox/{os.path.basename(out)}')
            j['done'] += 1
        core.save_settings({'scan_device': a['dev'], 'scan_res': int(a['res']), 'scan_mode': a['mode'], 'scan_batch': batch})

    def do_install(self, j, say):
        # i componenti aggiuntivi (pagina Add-ons): Homebrew, pip, swiftc, o il modello da Hugging Face.
        # Niente sudo; solo comandi fissi, il nome arriva da una lista chiusa
        what = j['args'].get('what', 'sane')
        repo = core.REPO
        if what in ('sane', 'exiftool', 'jxl'):
            cmds = [[core.brew() or 'brew', 'install', {'sane': 'sane-backends', 'exiftool': 'exiftool', 'jxl': 'jpeg-xl'}[what]]]
        elif what == 'ultralytics':
            cmds = [[sys.executable, '-m', 'pip', 'install', '--upgrade', 'ultralytics']]
        elif what == 'helpers':
            cmds = [['swiftc', '-O', os.path.join(repo, 'vision_mask.swift'), '-o', os.path.join(repo, 'vision_mask')],
                    ['swiftc', '-O', os.path.join(repo, 'studio', 'ocr.swift'), '-o', os.path.join(repo, 'studio', 'ocr')]]
        elif what == 'sam3':
            os.makedirs(core.models_dir(), exist_ok=True)
            code = ('import sys\n'
                    'from huggingface_hub import hf_hub_download\n'
                    'p = hf_hub_download("facebook/sam3", "sam3.pt", local_dir=sys.argv[1])\n'
                    'print("saved", p)\n')
            cmds = ([] if core.has_module('huggingface_hub') else [[sys.executable, '-m', 'pip', 'install', 'huggingface_hub']]) + \
                   [[sys.executable, '-c', code, core.models_dir()]]
        elif what.startswith('matte:'):
            m = next(x for x in core.MATTE_MODELS if x['id'] == what[6:])
            code = ('import sys\n'
                    'from huggingface_hub import snapshot_download\n'
                    'p = snapshot_download(sys.argv[1], local_dir=sys.argv[2], allow_patterns=["*.py", "*.json", "*.safetensors"])\n'
                    'print("saved", p)\n')
            need = [n for n in ('huggingface_hub', 'kornia', 'timm') if not core.has_module(n)]
            cmds = ([[sys.executable, '-m', 'pip', 'install'] + need] if need else []) + \
                   [[sys.executable, '-c', code, m['repo'], core.matte_dir(m['id'])]]
        else:
            raise ValueError(f'unknown add-on {what}')
        env = dict(os.environ, PATH=os.environ.get('PATH', '') + ':/opt/homebrew/bin:/usr/local/bin', HF_HUB_DISABLE_PROGRESS_BARS='1')
        if j['args'].get('token'):
            env['HF_TOKEN'] = j['args']['token']           # nell'ambiente, non sulla riga di comando
        for cmd in cmds:
            say('$ ' + ' '.join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd[:4])) + (' …' if len(cmd) > 4 else ''))
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            j['proc'] = p
            out = []
            for line in p.stdout:
                out.append(line.rstrip()); say(line.rstrip())
            if p.wait() != 0:
                if (what == 'sam3' or what.startswith('matte:')) and any(k in ' '.join(out) for k in ('401', '403', 'Gated', 'gated', 'awaiting', 'authenticated')):
                    page = 'facebook/sam3' if what == 'sam3' else next(x['repo'] for x in core.MATTE_MODELS if x['id'] == what[6:])
                    raise RuntimeError(f'Hugging Face refused: request access on huggingface.co/{page}, '
                                       'wait for the approval, then paste a read token (or run “hf auth login”).')
                raise RuntimeError(f'{os.path.basename(cmd[0])} failed (exit {p.returncode})')
        j['done'] = 1

    def do_ocr(self, j, say):
        # il testo dei ritagli scelti, uno alla volta (la barra avanza davvero), nei loro metadati
        j['result'] = []
        for rel in j['args']['rels']:
            if j['status'] == 'cancelled':
                break
            j['current'] = os.path.basename(rel)
            try:
                j['result'] += core.ocr_files([rel], log=say)
            except Exception as e:
                say(f'{rel}: ERROR {e}')
            j['done'] += 1

    def do_export(self, j, say):
        for rel in j['args']['rels']:
            if j['status'] == 'cancelled':
                break
            j['current'] = os.path.basename(rel)
            for w in core.export(rel, log=say):
                say(f'{w["status"]}: {os.path.relpath(w["path"], core.ROOT)}')
            j['done'] += 1

    def do_claude(self, j, say):
        # Claude Code senza finestra, nella cartella del progetto (legge CLAUDE.md e STUDIO.md)
        a = j['args']
        s = core.settings()
        ctx = (f'[Scan Studio] You are inside the user\'s Scan Studio. Scans root: {core.ROOT}. '
               f'Studio API: http://127.0.0.1:{PORT} (see STUDIO.md). '
               + (f'Current scan: {a["rel"]} (edit state: {core.state_path(a["rel"])}). ' if a.get('rel') else '')
               + 'Keep answers short; the reply is shown in a small panel.\n\n')
        exe = shutil.which('claude')
        if not exe:
            raise RuntimeError('Claude Code not found: install it (claude.com/claude-code), then reopen the studio')
        cmd = [exe, '-p', ctx + a['message'], '--output-format', 'stream-json', '--verbose',
               '--allowedTools', s['claude_tools']]
        if a.get('resume') and self.claude_session:
            cmd += ['--resume', self.claude_session]
        p = subprocess.Popen(cmd, cwd=core.REPO, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        j['proc'] = p
        for line in p.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                say(line.rstrip()); continue
            if ev.get('type') == 'assistant':
                for c in ev.get('message', {}).get('content', []):
                    if c.get('type') == 'text' and c['text'].strip():
                        say(c['text'])
                    elif c.get('type') == 'tool_use':
                        say(f'⚙ {c.get("name")}: {json.dumps(c.get("input"))[:160]}')
            elif ev.get('type') == 'result':
                self.claude_session = ev.get('session_id') or self.claude_session
                j['result'] = ev.get('result')
        p.wait()
        j.pop('proc', None)


JOBS = None


def next_scan_name(batch):
    # "<lotto> <numero>.tif", il primo numero libero fra inbox e originals/<lotto>
    used = [0]
    for d in (os.path.join(core.ROOT, 'inbox'), os.path.join(core.ROOT, 'originals', batch)):
        if os.path.isdir(d):
            for f in os.listdir(d):
                b, n = core.sc.split_name(core.sc.clean_stem(os.path.splitext(f.replace('.part', ''))[0]))
                if b == batch and n:
                    used.append(n)
    os.makedirs(os.path.join(core.ROOT, 'inbox'), exist_ok=True)
    return os.path.join(core.ROOT, 'inbox', f'{batch} {max(used) + 1}.tif')
LAST_SEEN = [0.0]       # ultima richiesta dalla finestra (per chiudersi quando non c'e' piu')


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = 'ScanStudio/1'

    def log_message(self, fmt, *a):
        pass

    def guard(self):
        if not self.path.startswith('/api/ping'):     # il Dock chiede se c'e' una finestra: non conta
            LAST_SEEN[0] = time.time()
        # niente richieste da altri siti: host locale, e per le POST un'intestazione propria
        host = (self.headers.get('Host') or '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost'):
            self.send_error(403); return False
        if self.command == 'POST' and self.headers.get('X-Studio') != '1':
            self.send_error(403); return False
        return True

    def send(self, body, ctype='application/json', code=200, cache=False):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'max-age=86400' if cache else 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def img(self, arr, fmt='JPEG', **kw):
        b = io.BytesIO()
        Image.fromarray(arr).save(b, fmt, **kw)
        self.send(b.getvalue(), 'image/jpeg' if fmt == 'JPEG' else 'image/png')

    def do_GET(self):
        if not self.guard():
            return
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path.startswith('/api/'):
                return self.api_get(u.path[5:], q)
            f = os.path.normpath(os.path.join(STATIC, u.path.lstrip('/') or 'index.html'))
            if not f.startswith(STATIC) or not os.path.isfile(f):
                return self.send_error(404)
            ct = {'.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript',
                  '.svg': 'image/svg+xml', '.png': 'image/png'}.get(os.path.splitext(f)[1], 'application/octet-stream')
            self.send(open(f, 'rb').read(), ct)
        except Exception as e:
            traceback.print_exc()
            self.send({'error': f'{type(e).__name__}: {e}'}, code=500)

    def do_POST(self):
        if not self.guard():
            return
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(n) or b'{}')
            return self.api_post(u.path[5:], body)
        except core.Busy as e:
            self.send({'error': str(e)}, code=409)
        except Exception as e:
            traceback.print_exc()
            self.send({'error': f'{type(e).__name__}: {e}'}, code=500)

    # ------------------------------------------------------------ GET
    def api_get(self, path, q):
        rel = q.get('rel')
        if rel:
            core.abspath(rel)          # fuori dalla radice: errore
        if path == 'ping':
            return self.send({'idle': round(time.time() - LAST_SEEN[0], 1) if LAST_SEEN[0] else 9999, 'version': core.VERSION})
        if path == 'addons':
            return self.send(core.addons())
        if path == 'tree':
            return self.send({'root': core.ROOT, 'tree': core.tree()})
        if path == 'list':
            return self.send(core.listing(q.get('dir', 'originals')))
        if path == 'thumb':
            p = core.preview_path(rel, int(q.get('size', 256)))
            return self.send(open(p, 'rb').read(), 'image/png' if p.endswith('.png') else 'image/jpeg', cache=True)
        if path == 'preview':
            p = core.preview_path(rel, 2400)
            return self.send(open(p, 'rb').read(), 'image/png' if p.endswith('.png') else 'image/jpeg', cache=True)
        if path == 'info':
            return self.send(core.info(rel))
        if path == 'tile':
            crop, box = core.tile(rel, float(q['x']), float(q['y']), float(q['w']), float(q['h']), float(q['out']))
            b = io.BytesIO()
            png = crop.ndim == 3 and crop.shape[2] == 4
            Image.fromarray(crop).save(b, 'PNG' if png else 'JPEG', **({'compress_level': 1} if png else {'quality': 92}))
            self.send_response(200)
            self.send_header('Content-Type', 'image/png' if png else 'image/jpeg')
            self.send_header('X-Box', ','.join(map(str, box)))
            self.send_header('Content-Length', str(b.tell()))
            self.end_headers(); self.wfile.write(b.getvalue()); return
        if path == 'masktile':
            # da vicino: la maschera vera (cio' che verra' tolto, scurito), stessa geometria di tile
            st = core.load_state(rel)
            info = core.info(rel)
            x0, y0 = max(0, int(float(q['x']))), max(0, int(float(q['y'])))
            x1, y1 = min(info['w'], int(float(q['x']) + float(q['w']))), min(info['h'], int(float(q['y']) + float(q['h'])))
            keep = np.zeros((max(1, y1 - y0), max(1, x1 - x0)), bool)
            for sh in st['sheets']:
                if sh.get('on', True) is False:
                    continue
                sy, sx, M, Hh, _ = core.sheet_mask_cached(rel, sh)
                M = M & ~Hh
                a0, b0 = max(x0, sx), max(y0, sy)
                a1, b1 = min(x1, sx + M.shape[1]), min(y1, sy + M.shape[0])
                if a1 > a0 and b1 > b0:
                    keep[b0 - y0:b1 - y0, a0 - x0:a1 - x0] |= M[b0 - sy:b1 - sy, a0 - sx:a1 - sx]
            out_w = max(1, min(int(float(q['out'])), keep.shape[1] * 4))
            out_h = max(1, round(keep.shape[0] * out_w / keep.shape[1]))
            k = cv2.resize(keep.astype(np.uint8), (out_w, out_h), interpolation=cv2.INTER_NEAREST)
            rgba = np.zeros((out_h, out_w, 4), np.uint8)
            rgba[..., :3] = (20, 30, 45)
            rgba[..., 3] = np.where(k > 0, 0, 120)
            b = io.BytesIO(); Image.fromarray(rgba, 'RGBA').save(b, 'PNG', compress_level=1)
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('X-Box', f'{x0},{y0},{x1},{y1}')
            self.send_header('Content-Length', str(b.tell()))
            self.end_headers(); self.wfile.write(b.getvalue()); return
        if path == 'bgtol':
            return self.send({'tol': core.bg_tol(rel)})
        if path == 'remembered':
            return self.send(core.remembered(rel))
        if path == 'engines':
            return self.send(core.engines())
        if path == 'state':
            st = core.load_state(rel)
            st['names'] = {sid: os.path.relpath(p, core.ROOT) if p.startswith(core.ROOT) else p
                           for sid, p in core.out_names(rel, st)}
            return self.send(st)
        if path == 'settings':
            return self.send(core.settings())
        if path == 'jobs':
            return self.send([JOBS.public(j) for j in sorted(JOBS.jobs.values(), key=lambda j: -j['created'])][:50])
        if path == 'job':
            j = JOBS.jobs.get(q.get('id'))
            return self.send(JOBS.public(j)) if j else self.send({'error': 'no such job'}, code=404)
        if path == 'cutout':
            # anteprima del ritaglio (come verra' salvato) per un foglio dello stato
            st = core.load_state(rel)
            sh = next(s for s in st['sheets'] if s['id'] == q['id'])
            res = core.cut_sheet(rel, sh)
            if res is None:
                return self.send({'error': 'empty sheet'}, code=404)
            rgba = res[0]
            mx = int(q.get('max', 1600))
            f = min(1.0, mx / max(rgba.shape[:2]))
            if f < 1:
                rgba = cv2.resize(rgba, (round(rgba.shape[1] * f), round(rgba.shape[0] * f)), interpolation=cv2.INTER_AREA)
            return self.img(rgba, 'PNG', compress_level=1)
        if path == 'pixel':
            return self.send(core.pixel(rel, float(q['x']), float(q['y']), int(q.get('r', 0))) or {})
        if path == 'histogram':
            sh = None
            if q.get('id'):
                sh = next((x for x in core.load_state(rel)['sheets'] if x['id'] == q['id']), None)
            return self.send(core.histogram(rel, sh))
        if path == 'scanners':
            if not scanner.available():
                return self.send({'available': False, 'devices': []})
            devs = scanner.devices(refresh=q.get('refresh') == '1')
            for d in devs:
                d['options'] = scanner.options(d['id'], refresh=q.get('refresh') == '1')
            return self.send({'available': True, 'devices': devs})
        if path == 'scanner_preview_area':
            p = os.path.join(core.DATA, 'scanner', 'preview-area.png')
            if q.get('meta'):
                m = os.path.join(core.DATA, 'scanner', 'preview-area.json')
                return self.send(json.load(open(m)) if os.path.exists(m) else {})
            if not os.path.exists(p):
                return self.send({'error': 'no area preview'}, code=404)
            return self.send(open(p, 'rb').read(), 'image/png')
        if path == 'scanner_preview':
            p = os.path.join(core.DATA, 'scanner', 'preview.png')
            if not os.path.exists(p):
                return self.send({'error': 'no preview yet'}, code=404)
            return self.send(open(p, 'rb').read(), 'image/png')
        if path == 'next_scan_name':
            return self.send({'name': os.path.basename(next_scan_name(core.sc.clean_stem(q.get('batch') or 'scan')))})
        self.send_error(404)

    # ------------------------------------------------------------ POST
    def api_post(self, path, b):
        rel = b.get('rel') or (b.get('state') or {}).get('rel')
        if rel:
            core.abspath(rel)
        rel = b.get('rel')
        if path == 'detect':
            st, meta = core.detect(rel, b.get('engine', 'auto'), b.get('params') or {}, b.get('box'),
                                   replace=b.get('replace', True))
            return self.send({'state': st, 'meta': {k: v for k, v in meta.items() if k != 'sheets'}})
        if path == 'state':
            st = b['state']
            cur = core.load_state(st['rel'])
            if cur.get('version', 0) != st.get('version', 0):
                return self.send({'error': 'changed elsewhere', 'state': cur}, code=409)
            st.pop('names', None)
            return self.send(core.save_state(st))
        if path == 'cutouts':
            # ritagli gia' salvati: girare (senza perdita), testo nei metadati, nel Cestino
            rels, act = b.get('rels') or [], b.get('action')
            for r in rels:
                core.abspath(r)
            if act == 'rotate':
                return self.send({'done': core.rotate_files(rels, int(b.get('deg', 90)))})
            if act == 'ocr':
                return self.send({'done': core.ocr_files(rels)})
            if act == 'merge':
                return self.send({'done': [core.relpath(core.merge_tiff(rels))]})
            if act == 'trash':
                return self.send({'done': core.trash_files(rels)})
            return self.send({'error': 'unknown action'}, code=400)
        if path == 'ocr_sheets':
            return self.send(core.ocr_sheets(rel, b.get('ids') or []))
        if path == 'checked':
            return self.send({'done': core.mark_checked(b.get('rels') or [])})
        if path == 'sam_unload':
            core.sam3_unload(); core.matte_unload()
            return self.send({'ok': True})
        if path == 'wand':
            op = core.wand(rel, float(b['x']), float(b['y']), b.get('tol', 14), b.get('contig', True))
            return self.send(op or {'error': 'nothing selected'}, code=200 if op else 404)
        if path == 'compare':
            return self.send(core.compare(rel, b.get('engines') or core.settings()['compare_engines']))
        if path == 'export':
            return self.send({'written': core.export(rel, replace=b.get('replace'), subfolder=b.get('subfolder'))})
        if path == 'settings':
            return self.send(core.save_settings(b))
        if path == 'jobs':
            kind = b.pop('kind')
            if kind not in ('batch', 'export', 'ocr', 'claude', 'preview', 'scan', 'install'):
                return self.send({'error': 'unknown job kind'}, code=400)
            return self.send(JOBS.public(JOBS.add(kind, **b)))
        if path == 'cancel':
            j = JOBS.jobs.get(b.get('id'))
            if not j:
                return self.send({'error': 'no such job'}, code=404)
            j['status'] = 'cancelled'
            if j.get('proc'):
                j['proc'].terminate()
            return self.send({'ok': True})
        if path == 'open':
            what = b.get('what')
            if what == 'finder':
                subprocess.run(['open', '-R', core.abspath(rel)] if rel else ['open', core.ROOT])
            elif what == 'canon':
                subprocess.run(['open', '-a', 'Canon IJ Scan Utility Lite'])
            elif what == 'imagecapture':
                subprocess.run(['open', '-a', 'Image Capture'])
            elif what == 'eagle':
                subprocess.run(['open', '-a', 'Eagle'])
            elif what == 'hide':
                # "riduci a icona" della cornice Vista: nasconde il Chrome dello studio (il clic nel
                # Dock lo riporta davanti, scan-studio.sh)
                pid = studio_chrome_pid()
                if pid:
                    subprocess.run([os.path.join(os.path.dirname(__file__), 'appctl'), 'hide', str(pid)], timeout=10)
            elif what == 'sam3page':
                subprocess.run(['open', 'https://huggingface.co/facebook/sam3'])
            elif what == 'hfpage' and str(b.get('url', '')).startswith('https://huggingface.co/'):
                subprocess.run(['open', b['url']])
            elif what == 'hftokens':
                subprocess.run(['open', 'https://huggingface.co/settings/tokens'])
            elif what == 'scripts':
                os.makedirs(core.SCRIPTS, exist_ok=True)
                subprocess.run(['open', core.SCRIPTS])
            elif what == 'kick':
                label = core.agent_label()
                if not label:
                    raise ValueError('the inbox agent is not installed (./install.sh --agent)')
                subprocess.run(['launchctl', 'kickstart', f'gui/{os.getuid()}/{label}'])
            return self.send({'ok': True})
        self.send_error(404)


def studio_chrome_pid():
    # il Chrome che mostra lo studio: quello con il profilo studio-data/window
    r = subprocess.run(['pgrep', '-o', '-f', 'user-data-dir=.*studio-data/window'], capture_output=True, text=True)
    return r.stdout.strip().split('\n')[0] if r.stdout.strip() else None


def scanners():
    # per ora: gli scanner che macOS conosce (la guida vera arriva con la tappa 2)
    out = []
    try:
        r = subprocess.run(['lpstat', '-v'], capture_output=True, text=True, timeout=5).stdout
        for line in r.splitlines():
            if 'LiDE' in line or 'scan' in line.lower():
                name = line.split(' for ')[-1].split(':')[0]
                out.append({'name': name.replace('_', ' '), 'uri': line.split(': ', 1)[-1], 'driver': 'eSCL / ImageCaptureCore'})
    except Exception:
        pass
    return out


def idle_exit(after_s=75):
    # modalita' app: chiusa la finestra (niente richieste da un po', nessun lavoro in corso)
    # il processo esce, e il prossimo clic nel Dock riparte pulito
    def watch():
        while True:
            time.sleep(10)
            busy = any(j['status'] in ('running', 'queued') for j in JOBS.jobs.values()) if JOBS else False
            if LAST_SEEN[0] and not busy and time.time() - LAST_SEEN[0] > after_s:
                os._exit(0)
    threading.Thread(target=watch, daemon=True).start()


def _on_term(*_):
    # fermato dall'app del Dock (SIGTERM): prima le scansioni in corso, poi via
    scanner._stop_all()
    os._exit(0)


def serve(root, port=PORT, ready=None):
    import signal
    try:
        signal.signal(signal.SIGTERM, _on_term)
    except ValueError:
        pass                                    # non nel thread principale (modalita' app): ci pensa atexit
    global JOBS, PORT
    PORT = port
    core.set_root(root)
    JOBS = Jobs()
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    httpd.daemon_threads = True
    if ready:
        ready(httpd)
    httpd.serve_forever()
