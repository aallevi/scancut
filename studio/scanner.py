# lo scanner, attraverso SANE (scanimage): l'unica via che sul Mac da' i 48 bit del LiDE 400.
# Elenca gli scanner, legge le loro opzioni vere (risoluzioni, modi, letto), fa l'anteprima
# del letto intero e le scansioni delle aree scelte. Una scansione alla volta.
# brew install sane-backends

import os, re, shutil, subprocess, threading, time

SCANIMAGE = shutil.which('scanimage') or '/opt/homebrew/bin/scanimage'
_busy = threading.Lock()
_cache = {}


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
    r = subprocess.run([SCANIMAGE, '-d', dev, '-A'], capture_output=True, text=True, timeout=60)
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


def scan(dev, out, resolution, mode='Color', area=None, progress=None, cancelled=lambda: False):
    # area: (sinistra, alto, larghezza, altezza) in mm; None = il letto intero.
    # Scrive out + '.part' e lo rinomina solo se la scansione e' completa.
    args = [SCANIMAGE, '-d', dev, '--format=tiff', '--resolution', str(int(resolution)), '--mode', mode, '-p']
    if area:
        l, t, w, h = area
        args += ['-l', f'{l:.2f}', '-t', f'{t:.2f}', '-x', f'{w:.2f}', '-y', f'{h:.2f}']
    tmp = out + '.part'
    with _busy:
        with open(tmp, 'wb') as f:
            p = subprocess.Popen(args, stdout=f, stderr=subprocess.PIPE, text=True, bufsize=1)
            err = []
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
                if cancelled():
                    p.terminate()
            p.wait()
        if p.returncode != 0 or os.path.getsize(tmp) == 0:
            os.remove(tmp)
            raise RuntimeError('scan failed: ' + ' / '.join(err[-3:]) if err else f'scanimage exit {p.returncode}')
        os.replace(tmp, out)
    return out
