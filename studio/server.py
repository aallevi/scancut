# server locale dello studio: l'interfaccia (static/) e un'API JSON che usano
# anche i lavori senza finestra e Claude. Solo 127.0.0.1.

import os, io, sys, json, time, sqlite3, threading, traceback, subprocess, uuid, queue, urllib.parse, shutil
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import numpy as np, cv2
from PIL import Image

from . import core, scanner, readers, help as helpdocs
from .library import bridge

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
        if kind in self.BESIDE:
            threading.Thread(target=self.run, args=(j,), daemon=True).start()
        else:
            self.q.put(j['id'])
        return j

    # domande, download e testo dei fogli non aspettano in coda dietro un batch (e viceversa)
    BESIDE = ('claude', 'install', 'ocr_sheets', 'read', 'readcuts')

    def track(self, kind, **args):
        # un'operazione fatta subito (Detect, SAM, Export dall'editor...) compare lo stesso fra i lavori
        jobs = self
        class T:
            def __enter__(self):
                self.j = {'id': uuid.uuid4().hex[:8], 'kind': kind, 'args': args, 'status': 'running', 'done': 0, 'total': 1,
                          'log': [], 'created': time.time(), 'started': time.time(), 'result': None,
                          'current': os.path.basename(args.get('rel') or '')}
                jobs.jobs[self.j['id']] = self.j
                return self.j
            def __exit__(self, et, e, tb):
                j = self.j
                j['finished'] = time.time()
                if e is None:
                    j['status'], j['done'] = 'done', j['total']
                    j['log'].append(f'done in {j["finished"] - j["started"]:.1f} s')
                else:
                    j['status'] = 'failed'
                    j['log'].append(f'ERROR {type(e).__name__}: {e}')
                return False
        return T()

    def public(self, j):
        # il token di Hugging Face non esce mai dal server
        return {k: ({a: v for a, v in j['args'].items() if a != 'token'} if k == 'args' else v) for k, v in j.items() if k != 'proc'}

    def loop(self):
        while True:
            self.run(self.jobs[self.q.get()])

    def run(self, j):
        if j['status'] == 'cancelled':
            return
        j['status'] = 'running'; j['started'] = time.time()
        say = lambda m: j['log'].append(m)
        try:
            getattr(self, 'do_' + j['kind'])(j, say)
            if j.get('detached'):
                return                                       # finisce da se' (l'archiviazione delle scansioni, accanto)
            if j['status'] == 'running':
                j['status'] = 'done'
        except scanner.Cancelled:
            j['status'] = 'cancelled'
            say('stopped; the scanner head went back home')
        except Exception as e:
            say(f'ERROR {type(e).__name__}: {e}')
            traceback.print_exc()
            if j['status'] != 'cancelled':
                j['status'] = 'failed'
        j['phase'] = None
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
                    ws = bridge.cut(rel, log=say)
                    for w in ws:
                        say(f'  {w["status"]}: {core.relpath(w["path"])}')
            except Exception as e:
                say(f'{rel}: ERROR {e}')
            j['done'] = start + (2 if a.get('export') else 1)

    def do_preview(self, j, say):
        # anteprima del letto intero, veloce (75 dpi): per scegliere le aree
        # con un'area: la stessa anteprima solo li', a 300 dpi, per piazzare l'area con precisione
        dev, area = j['args']['dev'], j['args'].get('area')
        d = os.path.join(core.DATA, 'scanner'); os.makedirs(d, exist_ok=True)
        tif = os.path.join(d, 'preview.tif')
        prog = scan_progress(j, 0, [1])
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
        def setting(area):
            own = area[4] if area and len(area) > 4 and isinstance(area[4], dict) else {}
            return int(own.get('res') or a['res']), own.get('mode') or a['mode']        # le impostazioni dell'area, se ne ha
        def size(area):
            res, mode = setting(area)
            mm2 = area[2] * area[3] if area else 216 * 297
            return mm2 * res * res * (2 if '48' in mode or '16' in mode else 1) * (1 if 'ray' in mode else 3)
        sizes = [size(x) for x in areas]
        lib = bridge.library(create=True)
        first_new = lib.db.execute('SELECT COALESCE(MAX(id), 0) FROM asset').fetchone()[0]
        mine, outs = [], []
        for k, area in enumerate(areas):
            if j['status'] == 'cancelled':
                break
            out = next_scan_name(batch)
            prog = scan_progress(j, k, sizes)
            res, mode = setting(area)
            say(f'scanning {os.path.basename(out)} at {res} dpi, {mode}' + (f', area {area[2]:.0f} x {area[3]:.0f} mm' if area else ', whole bed'))
            try:
                scanner.scan(a['dev'], out, res, mode, area=tuple(area[:4]) if area else None,
                             progress=prog, cancelled=lambda: j['status'] == 'cancelled')
            except scanner.Cancelled:
                say('stopped; the scanner head went back home')    # le aree gia' fatte si archiviano lo stesso
                break
            say(f'  read: {os.path.basename(out)}')
            outs.append(out)
            # come e' nata questa scansione (scanner, impostazioni, area): nella libreria, legata al file per checksum
            u = bridge._safe(bridge.record_capture, lib, out, 'scanner', series=batch, device=a['dev'],
                         settings={'res': res, 'mode': mode, 'area': [round(v, 1) for v in area[:4]] if area else None,
                                   'frames': a.get('frames') or None})
            if u:
                mine.append(u)
            j['done'] += 1
        if not j['done']:
            return                                           # fermata prima di finire la prima: niente da archiviare
        j['phase'] = 'filing'
        core.save_settings({'scan_device': a['dev'], 'scan_res': int(a['res']), 'scan_mode': a['mode'], 'scan_batch': batch})
        # fra le fonti e nella libreria, subito: ogni scansione e' gia' un oggetto della sua serie. Accanto, non in coda:
        # lo scanner e' gia' libero e la pagina dopo puo' partire mentre queste si archiviano
        def file():
            try:
                with FILING:
                    say('filing the scans… (see the job “File scans”)')
                    self.file_scans(outs + [x for x in core.scans_left() if x not in outs])   # anche quelle rimaste da prima
                    bridge.register_new(lib)
                    rels = bridge.captured(lib, mine, first_new)          # le sue, non quelle di un'altra scansione
                    j['result'] = {'rels': rels, 'scanned': j['done']}
                say(f'{len(rels)} new source(s) in the library' + (f'; {j["done"] - len(rels)} identical to an earlier scan, not kept twice' if len(rels) < j['done'] else ''))
                if j['status'] == 'running':
                    j['status'] = 'done'
            except Exception as e:
                say(f'ERROR {type(e).__name__}: {e}')
                traceback.print_exc()
                j['status'] = 'failed'
            j['phase'] = None
            j['finished'] = time.time()
        j['detached'] = True
        threading.Thread(target=file, daemon=True).start()

    def file_scans(self, paths):
        # archiviare, come lavoro suo (si vede in Lavori): ogni file, dove va, quanto pesa, quanto ci mette
        with self.track('file', rel=os.path.basename(paths[0]) if paths else '') as fj:
            fj['total'] = len(paths)
            def step(k, name):
                fj['done'], fj['current'] = k, name
            res = core.file_scans(paths, say=fj['log'].append, step=step)
            fj['current'], fj['done'] = '', len(paths)
            return res

    def do_install(self, j, say):
        # i componenti aggiuntivi (pagina Add-ons): Homebrew, pip, swiftc, o il modello da Hugging Face.
        # Niente sudo; solo comandi fissi, il nome arriva da una lista chiusa
        what = j['args'].get('what', 'sane')
        repo = core.REPO
        if what.startswith('pull:'):
            # un modello di Ollama: avanzamento vero (byte scaricati)
            def prog(st, pct):
                if pct is not None:
                    j['pct'] = pct
                if not j['log'] or j['log'][-1] != st:
                    say(st)
            readers.pull(what[5:], prog)
            j['done'] = 1
            return
        if what == 'ollama':
            what = 'ollama-brew'
        if what in ('sane', 'exiftool', 'jxl', 'ollama-brew'):
            cmds = [[core.brew() or 'brew', 'install', {'sane': 'sane-backends', 'exiftool': 'exiftool', 'jxl': 'jpeg-xl', 'ollama-brew': 'ollama'}[what]]]
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
        elif what.startswith('mlx:'):
            cmds = readers.mlx_install_cmds(what[4:])
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

    def do_ocr_sheets(self, j, say):
        # il testo dei fogli scelti di una scansione, uno alla volta (avanzamento vero)
        a = j['args']
        st = core.load_state(a['rel'])
        names = {sid: os.path.basename(p) for sid, p in core.out_names(a['rel'], st)}
        j['result'] = {}
        for sid in a['ids']:
            if j['status'] == 'cancelled':
                break
            j['current'] = names.get(sid, sid)
            t = core.ocr_sheets(a['rel'], [sid]).get(sid)
            if t is not None:
                j['result'][sid] = t
            say(f'{names.get(sid, sid)}: ' + (f'{len(t.splitlines())} line(s)' if t else 'no text'))
            j['done'] += 1

    def do_read(self, j, say):
        # documenti interi: il testo di ognuno (anche gli originali, che non si toccano); per i ritagli,
        # con embed, anche nei loro metadati
        a = j['args']
        j['result'] = []
        n = len(a['rels'])
        for i, rel in enumerate(a['rels']):
            if j['status'] == 'cancelled':
                break
            j['current'] = os.path.basename(rel)
            def prog(k, m, i=i):
                j['pct'] = (i + k / m) / n * 100
                j['current'] = f'{os.path.basename(rel)} · part {k} of {m}'
            try:
                t = core.read_doc(rel, prog)
                bridge._safe(bridge.on_read_doc, rel, t)          # nella libreria: testo della parte, o della fonte
                if a.get('embed') and core.is_recut(rel) and t:
                    core.embed_text(core.abspath(rel), t)
                j['result'].append({'rel': rel, 'text': t})
                say(f'{os.path.basename(rel)}: ' + (f'{len(t.splitlines())} line(s)' if t else 'no text'))
            except Exception as e:
                say(f'{rel}: ERROR {e}')
            j['done'] += 1
            j['pct'] = j['done'] / n * 100

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

    def do_readcuts(self, j, say):
        # il testo di molti ritagli, uno alla volta (barra vera)
        lib = bridge.library(create=False)
        def prog(k, n, name):
            j['pct'] = k / n * 100; j['current'] = name
        j['result'] = bridge.read_cutouts(lib, j['args']['uuids'], prog, log=say)
        j['done'] = 1

    def do_libimport(self, j, say):
        # la cartella delle scansioni nella libreria (originali referenziati, fogli, testo)
        lib = bridge.library(create=True)
        def prog(k, n, name):
            j['pct'] = k / n * 100; j['current'] = name
        r = bridge.import_root(lib, prog, log=say)
        with lib.db:
            lib.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('root_imported', ?)", (str(time.time()),))
        j['result'] = r; j['done'] = 1

    def do_switch(self, j, say):
        # i file dentro la libreria, in JPEG XL senza perdita (dopo il piano, confermato)
        lib = bridge.library(create=True)
        def prog(f, name):
            j['pct'] = f * 100; j['current'] = name
        j['result'] = bridge.switch_storage(lib, prog, log=say)
        j['done'] = 1

    def do_pull(self, j, say):
        def prog(st, pct):
            if pct is not None:
                j['pct'] = pct
            if not j['log'] or j['log'][-1] != st:
                say(st)
        readers.pull(j['args']['model'], prog)
        j['done'] = 1
        if what == 'ollama-brew':
            readers.start_ollama()

    def do_export(self, j, say):
        for rel in j['args']['rels']:
            if j['status'] == 'cancelled':
                break
            j['current'] = os.path.basename(rel)
            w = bridge.cut(rel, log=say)
            for x in w:
                say(f'{x["status"]}: {core.relpath(x["path"])}')
            j['done'] += 1

    def do_claude(self, j, say):
        # Claude Code senza finestra, nella cartella del progetto (legge CLAUDE.md e STUDIO.md)
        a = j['args']
        s = core.settings()
        ctx = (f'[Scan Studio] You are inside the user\'s Scan Studio. Scans root: {core.ROOT}. '
               f'Studio API: http://127.0.0.1:{PORT} (see STUDIO.md). '
               + (f'Current scan: {a["rel"]} (its parts, cuts and texts are in the library; read them with GET /api/state?rel=...). ' if a.get('rel') else '')
               + 'Keep answers short; the reply is shown in a small panel.\n\n')
        exe = shutil.which('claude')
        if not exe:
            raise RuntimeError('Claude Code not found: install it (claude.com/claude-code), then reopen the studio')
        try:
            hits = helpdocs.find(a['message'], k=4)
            if hits:
                ctx += ('Relevant parts of the studio help (use these first; read code only if '
                        'they are not enough):\n' + '\n\n'.join(f'## {h["title"]}\n{h["text"]}' for h in hits) + '\n\n')
        except Exception:
            pass
        cmd = [exe, '-p', ctx + a['message'], '--output-format', 'stream-json', '--verbose',
               '--allowedTools', s['claude_tools']]
        if s.get('claude_model'):
            cmd += ['--model', s['claude_model']]
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


FILING = threading.Lock()      # una archiviazione alla volta (l'inbox e la libreria), anche con scansioni una dopo l'altra


def scan_progress(j, k, sizes):
    # avanzamento di una scansione: prima lo scanner si prepara (lampada, calibrazione: niente percentuale),
    # poi legge. Le aree pesano per i pixel che hanno (una piccola e una grande non valgono meta' e meta');
    # il tempo che resta viene dal ritmo misurato di quest'area, esteso alle aree che mancano
    tot = sum(sizes) or 1
    before, mine, after = sum(sizes[:k]), sizes[k], sum(sizes[k + 1:])
    j.update(phase='warming', area=k + 1, areas=len(sizes), pct=before / tot * 100, eta=None, phase_t=time.time())
    def prog(p):
        t = time.time()
        if j['phase'] == 'warming' and p > 0:
            j.update(phase='scanning', phase_t=t, p0=p)
        if j['phase'] == 'scanning' and p - j.get('p0', 0) > 1:
            per = (t - j['phase_t']) / (p - j['p0'])                       # secondi per 1% di quest'area
            j['eta'] = per * (100 - p) + per * 100 * after / (mine or 1)
        j['pct'] = (before + mine * p / 100) / tot * 100
    return prog


def next_scan_name(batch):
    # "<lotto> <numero>.tif", il primo numero libero fra inbox, la cartella dello scanner e originals/<lotto>
    used = [0]
    for d in (os.path.join(core.ROOT, 'inbox'), core.scanning_dir(), core.abspath(os.path.join('originals', batch))):
        if os.path.isdir(d):
            for f in os.listdir(d):
                b, n = core.sc.split_name(core.sc.clean_stem(os.path.splitext(f.replace('.part', ''))[0]))
                if b == batch and n:
                    used.append(n)
    return os.path.join(core.scanning_dir(), f'{batch} {max(used) + 1}.tif')
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
            if u.path == '/api/add_file':
                return self.add_file(urllib.parse.parse_qs(u.query), n)
            body = json.loads(self.rfile.read(n) or b'{}')
            return self.api_post(u.path[5:], body)
        except core.Busy as e:
            self.send({'error': str(e)}, code=409)
        except Exception as e:
            traceback.print_exc()
            self.send({'error': f'{type(e).__name__}: {e}'}, code=500)

    def add_file(self, q, n):
        # un file trascinato nella finestra: i byte arrivano cosi' come sono (niente conversioni), in un .part,
        # poi con un nome libero (mai sopra un altro). Fonti: nell'inbox, l'agente le mette fra le fonti;
        # tagli: in cut/added/, nella libreria come tagli portati da fuori.
        to = (q.get('to') or ['sources'])[0]
        name = os.path.basename((q.get('name') or ['file'])[0]).strip() or 'file'
        if not core.is_image(name) and not name.lower().endswith('.pdf'):
            self.rfile.read(n)
            return self.send({'error': f'{name}: not an image'}, code=400)
        d = core.abspath('inbox' if to == 'sources' else os.path.join('cut', 'added'))
        os.makedirs(d, exist_ok=True)
        part = os.path.join(d, '.' + name + f'.{os.getpid()}-{threading.get_ident()}.part')
        left = n
        with open(part, 'wb') as f:
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                f.write(chunk); left -= len(chunk)
        if left:
            os.remove(part)
            return self.send({'error': 'upload interrupted'}, code=400)
        dst = core.sc.unique(os.path.join(d, name))
        os.link(part, dst); os.remove(part)                  # mai sopra un file che c'e'
        lib = bridge.library(create=True)
        if to == 'sources':
            bridge.record_capture(lib, dst, 'added', name=name)
        else:
            bridge.add_cut_file(lib, dst)
        return self.send({'ok': True, 'rel': core.relpath(dst)})

    # ------------------------------------------------------------ GET
    def api_get(self, path, q):
        rel = q.get('rel')
        if rel:
            core.abspath(rel)          # fuori dalla radice: errore
        if path == 'ping':
            return self.send({'idle': round(time.time() - LAST_SEEN[0], 1) if LAST_SEEN[0] else 9999, 'version': core.VERSION,
                              'build': BUILD[0], 'dev': '--dev' in sys.argv})
        if path == 'addons':
            return self.send(core.addons() + readers.addon_rows())
        if path == 'tree':
            lib = bridge.library(create=False)
            if lib:
                bridge._safe(bridge.register_new, lib, False)      # le fonti arrivate intanto: nella libreria
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
        if path == 'search':
            return self.send(helpdocs.search(q.get('q', '')))
        if path == 'library':
            lib = bridge.library(create=False)
            return self.send(dict(bridge.info(lib), exists=True) if lib else {'exists': False, 'path': bridge.library_path()})
        if path == 'library/trash':
            lib = bridge.library(create=False)
            return self.send(bridge.trash_list(lib) if lib else [])
        if path == 'library/places':
            lib = bridge.library(create=False)
            return self.send({'places': bridge.places(lib), 'categories': bridge.categories(lib)} if lib else {'places': [], 'categories': []})
        if path == 'library/items':
            lib = bridge.library(create=False)
            return self.send(bridge.item_list(lib, q.get('q') or None, series=q.get('series') or None, place=q.get('place') or None) if lib else [])
        if path == 'library/journal':
            lib = bridge.library(create=False)
            return self.send({'dir': bridge.journal_dir(lib) if lib else None})
        if path == 'library/switch':
            return self.send(bridge.switch_plan(bridge.library(create=True)))
        if path == 'library/check':
            lib = bridge.library(create=False)
            return self.send(bridge.check(lib, deep=q.get('deep') == '1') if lib else [])
        if path == 'library/where':
            lib = bridge.library(create=False)
            return self.send(bridge.where(lib, rel) if lib else {'known': False})
        if path == 'library/series':
            lib = bridge.library(create=False)
            return self.send(bridge.series_list(lib) if lib else [])
        if path == 'library/item':
            r = bridge.item_detail(bridge.library(create=False), q['uuid'])
            return self.send(r) if r else self.send({'error': 'no such item'}, code=404)
        if path == 'library/texts':
            lib = bridge.library(create=False)
            return self.send(bridge.text_list(lib, q.get('q') or None) if lib else [])
        if path == 'library/cutouts':
            lib = bridge.library(create=False)
            return self.send(bridge.cutout_list(lib, series=q.get('series') or None, place=q.get('place') or None) if lib else [])
        if path == 'library/texts_for':
            lib = bridge.library(create=False)
            return self.send(bridge.texts_for_rel(lib, rel) if lib else [])
        if path == 'library/editors':
            return self.send(bridge.editors())
        if path == 'read_cached':
            return self.send({'text': core.read_cached(rel)})
        if path == 'help':
            # la finestra Aiuto: tutti i capitoli (indice e testi), o le sezioni che rispondono a una ricerca
            return self.send(helpdocs.find(q['q'], k=20) if q.get('q') else helpdocs.chapters())
        if path == 'bgtol':
            return self.send({'tol': core.bg_tol(rel)})
        if path == 'remembered':
            return self.send(core.remembered(rel))
        if path == 'engines':
            return self.send(core.engines())
        if path == 'state':
            st = core.load_state(rel)
            if st is None:
                raise FileNotFoundError(rel)
            st['names'] = {sid: core.relpath(p) if p.startswith(core.ROOT) else p
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
            e = b.get('engine', 'auto')
            kind = 'sam' if e == 'sam3' and (b.get('params') or {}).get('points') else 'detect'
            with JOBS.track(kind, rel=rel, engine=e, box=b.get('box')) as j:
                st, meta = core.detect(rel, e, b.get('params') or {}, b.get('box'), replace=b.get('replace', True))
                j['log'].append(f'{len(st["sheets"])} sheet(s)')
            return self.send({'state': st, 'meta': {k: v for k, v in meta.items() if k != 'sheets'}})
        if path == 'state':
            st = b['state']
            cur = core.load_state(st['rel'])
            if cur.get('version', 0) != st.get('version', 0):
                return self.send({'error': 'changed elsewhere', 'state': cur}, code=409)
            st.pop('names', None)
            return self.send(core.save_state(st))                  # salvare = scrivere la libreria
        if path == 'recut_part':
            # "Fatto" dopo aver ritoccato una parte venendo dal suo taglio: si rifa' solo quel taglio, subito
            bridge.recut_now(b['rel'], {b['id']})
            lib = bridge.library()
            a = lib.db.execute('SELECT id FROM asset WHERE path = ?', (os.path.realpath(core.abspath(b['rel'])),)).fetchone()
            c = lib.db.execute("SELECT x.path FROM cut x JOIN region r ON r.id = x.region_id WHERE r.asset_id = ? AND json_extract(r.source, '$.studio_id') = ? "
                               "AND r.removed_at IS NULL AND x.path NOT LIKE '%/studio-data/%' ORDER BY x.id DESC LIMIT 1", (a['id'], b['id'])).fetchone() if a else None
            return self.send({'rel': core.relpath(c['path']) if c and os.path.exists(c['path']) else None})
        if path == 'cutouts':
            # ritagli gia' salvati: girare (senza perdita), testo nei metadati, nel Cestino
            rels, act = b.get('rels') or [], b.get('action')
            for r in rels:
                core.abspath(r)
            if act == 'rotate':
                done = core.rotate_files(rels, int(b.get('deg', 90)))
                bridge._safe(bridge.on_cutouts_rotated, done, int(b.get('deg', 90)))     # la rotazione e' della zona
                return self.send({'done': done})
            if act == 'ocr':
                return self.send({'done': core.ocr_files(rels)})
            if act == 'merge':
                return self.send({'done': [core.relpath(core.merge_tiff(rels))]})
            if act == 'trash':
                # nel cestino della libreria (si rimette a posto da li'; si svuota da solo dopo i giorni scelti)
                lib = bridge.library()
                ids = []
                for r in rels:
                    p_ = os.path.realpath(core.abspath(r))
                    a = lib.db.execute('SELECT uuid FROM asset WHERE path = ?', (p_,)).fetchone()
                    ids.append(a[0] if a else lib.db.execute('SELECT uuid FROM asset WHERE id = ?', (bridge.add_cut_file(lib, p_),)).fetchone()[0])
                bridge.trash(lib, [], ids)
                return self.send({'done': rels})
            return self.send({'error': 'unknown action'}, code=400)
        if path == 'ocr_box':
            eng = core.settings().get('ocr_engine') or 'vision'
            with JOBS.track('ocr_box', rel=rel, engine=eng) as j:
                text = core.ocr_box(rel, b['box'])
                j['log'].append(f'{len(text.splitlines())} line(s)' if text else 'no text')
            return self.send({'text': text, 'engine': eng})
        if path == 'library/trash':
            # nel cestino della libreria: fonti intere (con i loro tagli) o tagli (per uuid, o per percorso)
            lib = bridge.library()
            cuts = list(b.get('cuts') or [])
            for r in b.get('rels') or []:
                a = lib.db.execute('SELECT uuid FROM asset WHERE path = ?', (os.path.realpath(core.abspath(r)),)).fetchone()
                if a:
                    cuts.append(a[0])
            return self.send({'trashed': bridge.trash(lib, b.get('items') or [], cuts)})
        if path == 'library/restore':
            return self.send({'ok': bridge.restore(bridge.library(), b['uuid'])})
        if path == 'library/empty':
            return self.send({'gone': bridge.empty_trash(bridge.library(), None, b.get('uuids') or None)})
        if path == 'library/export':
            r = bridge.export_cuts(bridge.library(), b['dir'], b.get('structure') or 'place', b.get('series') or None, b.get('place') or None, b.get('cuts') or None)
            if b.get('reveal'):
                subprocess.run(['open', r['dir']])
            return self.send(r)
        if path == 'choose_folder':
            # la finestra del Mac per scegliere una cartella
            r = subprocess.run(['osascript', '-e', f'POSIX path of (choose folder with prompt "{b.get("prompt") or "Choose a folder"}")'], capture_output=True, text=True)
            return self.send({'dir': r.stdout.strip().rstrip('/') or None})
        if path == 'library/place':
            # un posto nuovo o cambiato (nome, dentro quale, numero) o tolto; le regole le tiene il database
            lib = bridge.library()
            try:
                u = bridge.save_place(lib, b.get('uuid'), b.get('name'), b.get('parent'), b.get('number'), b.get('kind') or 'storage', b.get('notes'), bool(b.get('delete')))
            except sqlite3.IntegrityError as e:
                return self.send({'error': str(e)}, code=409)
            return self.send({'uuid': u, 'places': bridge.places(lib)})
        if path == 'library/put':
            # in un posto (con numero) e/o una categoria: fonti intere o singole parti; un indirizzo "24-05" si risolve
            lib = bridge.library()
            kw = {}
            if 'place' in b:
                kw['place'] = bridge.resolve_address(lib, b['address']) if b.get('address') else b['place']
                if b.get('address') and not kw['place']:
                    return self.send({'error': f'no place at {b["address"]}'}, code=404)
            if 'number' in b:
                kw['number'] = b['number']
            if 'category' in b:
                kw['category'] = b['category']
            try:
                n = bridge.put(lib, b.get('items') or [], b.get('regions') or [], **kw)
            except sqlite3.IntegrityError as e:
                return self.send({'error': str(e)}, code=409)
            return self.send({'changed': n})
        if path == 'add_done':
            # i file trascinati sono tutti arrivati: fra le fonti e nella libreria
            core.file_inbox()
            new = bridge.register_new(bridge.library(create=True))
            return self.send({'rels': bridge.new_rels(bridge.library(), new)})
        if path == 'library/journal':
            lib = bridge.library(create=False)
            if b.get('dir'):
                bridge.set_journal_dir(lib, b['dir'])
            r = bridge.write_journal(lib)
            if r and r['dir'].startswith(core.ROOT):
                r['rel'] = core.relpath(r['dir'])
            if r and b.get('reveal'):
                subprocess.run(['open', r['dir']])
            return self.send(r or {'error': 'no folder chosen'})
        if path == 'library/correct':
            lib = bridge.library(create=False)
            bridge.correct_text(lib, int(b['reading']), str(b['text']))
            return self.send({'ok': True})
        if path == 'library/edit_in':
            lib = bridge.library(create=False)
            with JOBS.track('edit_in', rel=None, engine=None) as j:
                work = bridge.edit_in(lib, b['asset'], b['app'])
                j['current'] = os.path.basename(work)
                j['log'].append(f'opened in {b["app"]}: saving there adds a new version to the library')
            return self.send({'work': work})
        if path == 'save_text':
            # il testo letto in un file Markdown accanto ai ritagli, mai sopra uno che c'e' gia'
            names = core.out_names(rel)
            d = os.path.dirname(names[0][1]) if names else core.abspath(os.path.join('cut', core.batch_of(rel)))
            os.makedirs(d, exist_ok=True)
            out = core.sc.unique(os.path.join(d, core.sc.clean_stem(os.path.splitext(os.path.basename(rel))[0]) + '.md'))
            with open(out + '.part', 'w', encoding='utf-8') as f:
                f.write(str(b.get('text', '')))
            os.replace(out + '.part', out)
            return self.send({'path': core.relpath(out) if out.startswith(core.ROOT) else out})
        if path == 'ocr_sheets':
            return self.send(core.ocr_sheets(rel, b.get('ids') or []))
        if path == 'checked':
            return self.send({'done': core.mark_checked(b.get('rels') or [])})
        if path == 'sam_unload':
            core.sam3_unload(); core.matte_unload(); readers.unload_ocr()
            return self.send({'ok': True})
        if path == 'wand':
            op = core.wand(rel, float(b['x']), float(b['y']), b.get('tol', 14), b.get('contig', True))
            return self.send(op or {'error': 'nothing selected'}, code=200 if op else 404)
        if path == 'compare':
            with JOBS.track('compare', rel=rel):
                r = core.compare(rel, b.get('engines') or core.settings()['compare_engines'])
            return self.send(r)
        if path == 'export':
            with JOBS.track('export', rel=rel) as j:
                # una copia congelata (sottocartella) non e' il taglio della parte: la libreria non la segue
                w = bridge.cut(rel, follow=not b.get('subfolder'), replace=b.get('replace'), subfolder=b.get('subfolder'), log=j['log'].append)
                j['log'] += [f'{x["status"]}: {core.relpath(x["path"])}' for x in w]
            return self.send({'written': w})
        if path == 'settings':
            return self.send(core.save_settings(b))
        if path == 'jobs':
            kind = b.pop('kind')
            if kind not in ('readcuts', 'libimport', 'switch', 'batch', 'export', 'ocr', 'read', 'ocr_sheets', 'claude', 'pull', 'preview', 'scan', 'install'):
                return self.send({'error': 'unknown job kind'}, code=400)
            return self.send(JOBS.public(JOBS.add(kind, **b)))
        if path == 'jobs_clear':
            for k in [k for k, j in JOBS.jobs.items() if j['status'] not in ('running', 'queued')]:
                del JOBS.jobs[k]
            return self.send({'ok': True})
        if path == 'cancel':
            j = JOBS.jobs.get(b.get('id'))
            if not j:
                return self.send({'error': 'no such job'}, code=404)
            j['status'] = 'cancelled'
            if j.get('phase') in ('warming', 'scanning'):
                j['phase'] = 'stopping'                      # la scansione si ferma da se' e riporta la testina a casa
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
            elif what == 'hfpage' and str(b.get('url', '')).startswith(('https://huggingface.co/', 'https://ollama.com/')):
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


BUILD = ['']


def code_stamp():
    # quando e' cambiato per l'ultima volta il codice (Python e pagine)
    base = os.path.dirname(os.path.abspath(__file__))
    files = [os.path.join(d, f) for d, _, fs in os.walk(base) for f in fs if f.endswith(('.py', '.js', '.css', '.html'))]
    return str(max((os.path.getmtime(f) for f in files), default=0))


def dev_reload():
    # anteprima: Python cambiato -> il server si riavvia (aspetta che i lavori finiscano); le pagine
    # si ricaricano da sole (vedono /api/ping cambiare)
    base = os.path.dirname(os.path.abspath(__file__))
    def py_stamp():
        return max(os.path.getmtime(os.path.join(d, f)) for d, _, fs in os.walk(base) for f in fs if f.endswith('.py'))
    start = py_stamp()
    def loop():
        while True:
            time.sleep(1.5)
            BUILD[0] = code_stamp()
            if py_stamp() != start and not any(j['status'] in ('running', 'queued') for j in JOBS.jobs.values()):
                time.sleep(0.5)
                os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=loop, daemon=True).start()


def serve(root, port=PORT, ready=None, dev=False):
    import signal
    try:
        signal.signal(signal.SIGTERM, _on_term)
    except ValueError:
        pass                                    # non nel thread principale (modalita' app): ci pensa atexit
    global JOBS, PORT
    PORT = port
    core.set_root(root)
    JOBS = Jobs()
    BUILD[0] = code_stamp()
    if dev:
        dev_reload()
    lib = bridge.library(create=False)
    if lib:
        bridge.start_watch(lib)
    # la prima volta su una cartella di scansioni che c'era gia': fonti, parti e tagli di prima nella libreria, una volta
    lib0 = bridge.library(create=True)
    if not lib0.meta('root_imported') and os.path.isdir(core.abspath('originals')) and any(
            core.is_image(f) for _, _, fs in os.walk(core.abspath('originals')) for f in fs):
        JOBS.add('libimport')
    if core.scans_left():
        def left():
            with FILING:
                JOBS.file_scans(core.scans_left())
                bridge.register_new(bridge.library(create=True))
        threading.Thread(target=left, daemon=True).start()                 # le copie aperte in Affinity & co. da prima: si guardano ancora
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    httpd.daemon_threads = True
    if ready:
        ready(httpd)
    httpd.serve_forever()
