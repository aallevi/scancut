# lo scanner, attraverso SANE (scanimage): l'unica via che sul Mac da' i 48 bit del LiDE 400.
# Elenca gli scanner, legge le loro opzioni vere (risoluzioni, modi, letto), fa l'anteprima
# del letto intero e le scansioni delle aree scelte. Una scansione alla volta.
# brew install sane-backends

import os, re, shutil, signal, subprocess, threading, time, atexit

SCANIMAGE = shutil.which('scanimage') or '/opt/homebrew/bin/scanimage'
_busy = threading.RLock()       # rientrante: il nuovo tentativo dopo aver tolto un orfano
_cache = {}
_running = set()              # le scansioni in corso: se lo studio si ferma, si fermano anche loro


def _stop_all(*_):
    # una richiesta sola (la seconda lascerebbe la testina a meta'), poi 20 s per tornare a casa; poi si forza
    for p in list(_running):
        if p.poll() is None:
            p.send_signal(signal.SIGINT)
            try:
                p.wait(20)
            except subprocess.TimeoutExpired:
                p.kill()


atexit.register(_stop_all)


def clear_orphans(dev):
    # una scansione rimasta da sola (lo studio che l'aveva lanciata non c'e' piu': genitore 1)
    # tiene occupato lo scanner: si ferma. Solo scanimage di questo scanner, senza genitore
    r = subprocess.run(['ps', '-axo', 'pid=,ppid=,command='], capture_output=True, text=True)
    n = 0
    for line in r.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[1] == '1' and 'scanimage' in parts[2] and dev in parts[2]:
            pid = int(parts[0])
            try:
                os.kill(pid, signal.SIGINT); n += 1
                for _ in range(200):                     # fino a 20 s per fermarsi e riportare a casa la testina
                    time.sleep(0.1)
                    os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)            # mentre aspetta lo scanner non sente la richiesta gentile
            except OSError:
                pass                                    # gia' finito
    if n:
        time.sleep(2)                                   # lo scanner si libera
    return n


def available():
    return os.path.exists(SCANIMAGE)


def devices(refresh=False):
    # [{id, name}] ; scanimage -L ci mette qualche secondo, si tiene a mente
    if 'devices' in _cache and not refresh:
        return _cache['devices']
    if not available():
        return []
    r = subprocess.run([SCANIMAGE, '-L'], capture_output=True, text=True, timeout=60)
    out = []
    for line in r.stdout.splitlines():
        m = re.match(r"device `(.+?)' is a (.+)", line.strip())
        if m:
            out.append({'id': m.group(1), 'name': re.sub(r'\s+(multi-function peripheral|flatbed scanner)$', '', m.group(2))})
    _cache['devices'] = out
    return out


def options(dev, refresh=False):
    # le opzioni che lo scanner dichiara: niente risoluzioni inventate
    key = 'opt:' + dev
    if key in _cache and not refresh:
        return _cache[key]
    try:
        r = subprocess.run([SCANIMAGE, '-d', dev, '-A'], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return {'error': 'not responding'}             # bloccato: non si tiene a mente, si riprova
    if r.returncode != 0:
        return {'error': (r.stderr.strip().splitlines() or ['not responding'])[-1]}
    txt = r.stdout
    o = {'resolutions': [], 'modes': [], 'width_mm': 216.0, 'height_mm': 297.0}
    m = re.search(r'--resolution\s+(?:auto\|)?([\d|]+)dpi', txt)
    if m:
        o['resolutions'] = [int(v) for v in m.group(1).split('|') if v]
    m = re.search(r'--mode\s+(?:auto\|)?(.+?)\s+\[', txt)
    if m:
        o['modes'] = [v for v in m.group(1).split('|') if v and v != 'auto']
    m = re.search(r'-x\s+(?:auto\|)?0\.\.([\d.]+)mm', txt)
    if m:
        o['width_mm'] = float(m.group(1))
    m = re.search(r'-y\s+(?:auto\|)?0\.\.([\d.]+)mm', txt)
    if m:
        o['height_mm'] = float(m.group(1))
    _cache[key] = o
    return o


class Cancelled(Exception):
    pass


def scan(dev, out, resolution, mode='Color', area=None, progress=None, cancelled=lambda: False, _retry=2):
    # area: (sinistra, alto, larghezza, altezza) in mm; None = il letto intero.
    # Scrive out + '.part' e lo rinomina solo se la scansione e' completa.
    # Fermare: UNA richiesta gentile e poi si aspetta. scanimage alla prima chiede allo scanner di fermarsi e
    # riportare la testina a casa; alla seconda esce subito e la testina resta a meta' (scanner bloccato).
    args = [SCANIMAGE, '-d', dev, '--format=tiff', '--resolution', str(int(resolution)), '--mode', mode, '-p']
    if area:
        l, t, w, h = area
        args += ['-l', f'{l:.2f}', '-t', f'{t:.2f}', '-x', f'{w:.2f}', '-y', f'{h:.2f}']
    tmp = out + '.part'
    with _busy:
        with open(tmp, 'wb') as f:
            p = subprocess.Popen(args, stdout=f, stderr=subprocess.PIPE, text=True, bufsize=1)
            _running.add(p)
            err = []

            def read():
                # l'avanzamento arriva su stderr ("Progress: 12.3%" e un ritorno a capo): letto a parte,
                # cosi' la richiesta di fermarsi si sente anche mentre lo scanner tace (lampada, calibrazione)
                buf = ''
                while True:
                    ch = p.stderr.read(1)
                    if not ch:
                        break
                    if ch in '\r\n':
                        m = re.search(r'Progress:\s*([\d.]+)%', buf)
                        if m and progress:
                            progress(float(m.group(1)))
                        elif buf.strip():
                            err.append(buf.strip())
                        buf = ''
                    else:
                        buf += ch
            rd = threading.Thread(target=read, daemon=True); rd.start()
            stop_at = None
            while p.poll() is None:
                if stop_at is None and cancelled():
                    p.send_signal(signal.SIGINT)                 # una volta sola
                    stop_at = time.time()
                if stop_at and time.time() - stop_at > 120:      # non si e' fermato in due minuti: si forza
                    p.kill()
                time.sleep(0.15)
            rd.join(2)
            _running.discard(p)
        if stop_at or (cancelled() and p.returncode != 0):
            os.remove(tmp)
            raise Cancelled()
        if p.returncode != 0 or os.path.getsize(tmp) == 0:
            os.remove(tmp)
            # scanner occupato da una scansione rimasta orfana, o ancora confuso da una interrotta:
            # si libera, si aspetta che si riprenda, si riprova (al massimo due volte)
            if _retry and not cancelled() and any(k in e for e in err for k in ('open of device', 'device I/O', 'Device busy')):
                clear_orphans(dev)
                time.sleep(5)
                return scan(dev, out, resolution, mode, area, progress, cancelled, _retry=_retry - 1)
            raise RuntimeError('scan failed: ' + ' / '.join(err[-3:]) if err else f'scanimage exit {p.returncode}')
        os.replace(tmp, out)
    return out
