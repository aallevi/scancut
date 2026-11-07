# Scan Studio: finestra per vedere e ritoccare i ritagli, e lavori senza finestra.
#
#   python3 -I studio.py                    apre la finestra (radice ~/Scans)
#   python3 -I studio.py serve [--port N]   solo il server (per Claude o un browser)
#   python3 -I studio.py detect <scan>... [--engine auto|classic|vision|sam3|script:x] [--export]
#   python3 -I studio.py export <scan>...   salva i ritagli dello stato ritoccato
#   python3 -I studio.py engines            elenca i motori
#   --root <cartella> per lavorare su una copia (prove)

import os, sys, argparse, threading, subprocess, time, webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from studio import core, server  # noqa: E402


def rels(paths):
    out = []
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p)) if not p.startswith(('originals/', 'cut/', 'failed/', 'inbox/')) \
            else os.path.join(core.ROOT, p)
        if os.path.isdir(p):
            out += [core.relpath(os.path.join(p, f)) for f in sorted(os.listdir(p)) if core.is_image(f)]
        else:
            out.append(core.relpath(p))
    return out


def window(url):
    # una finestra vera se c'e' pywebview, altrimenti Chrome in modalita' app, o il browser
    try:
        import webview

        class Api:   # i pulsanti della cornice Vista disegnata nella pagina
            def min(self): webview.windows[0].minimize()
            def max(self): webview.windows[0].toggle_fullscreen()
            def close(self): webview.windows[0].destroy()

        webview.create_window('Scan Studio', url, width=1400, height=900, min_size=(900, 600),
                              frameless=True, easy_drag=False, js_api=Api(), background_color='#1b2a3a')
        webview.start()
        return True
    except ImportError:
        pass
    for app in ('Google Chrome', 'Microsoft Edge', 'Brave Browser', 'Chromium'):
        if os.path.exists(f'/Applications/{app}.app'):
            subprocess.Popen(['open', '-na', app, '--args', f'--app={url}', '--window-size=1400,900',
                              f'--user-data-dir={os.path.join(core.DATA, "window")}'])
            return False
    webbrowser.open(url)
    return False


def main():
    ap = argparse.ArgumentParser(prog='studio.py')
    ap.add_argument('cmd', nargs='?', default='app', choices=['app', 'serve', 'detect', 'export', 'engines'])
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--root', default='~/Scans')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--dev', action='store_true', help='anteprima: si riavvia da solo quando il codice cambia')
    ap.add_argument('--engine', default='auto')
    ap.add_argument('--prompt', help='SAM 3 text prompt')
    ap.add_argument('--export', action='store_true')
    a = ap.parse_args()
    core.set_root(a.root)

    if a.cmd == 'engines':
        for e in core.engines():
            print(f'{e["id"]:24} {"ok " if e["available"] else "-- "} {e["name"]}  {e["note"]}')
        return
    if a.cmd in ('detect', 'export'):
        params = {'prompt': a.prompt} if a.prompt else {}
        for rel in rels(a.paths):
            if a.cmd == 'detect':
                st, meta = core.detect(rel, a.engine, params)
                print(f'{rel}: {len(st["sheets"])} sheet(s), {a.engine}, {meta.get("seconds")}s')
            if a.cmd == 'export' or a.export:
                for w in core.export(rel):
                    print(f'  {w["status"]}: {w["path"]}')
        return

    url = f'http://127.0.0.1:{a.port}/'
    if a.cmd == 'serve':
        print(f'Scan Studio on {url}  (root {core.ROOT})', flush=True)
        server.serve(a.root, a.port, dev=a.dev)
        return
    # gia' aperto (un'altra finestra, o il server a mano): basta una finestra nuova
    import urllib.request
    try:
        urllib.request.urlopen(url + 'api/settings', timeout=1).read()
        window(url)
        return
    except OSError:
        pass
    ready = threading.Event()
    threading.Thread(target=server.serve, args=(a.root, a.port, lambda h: ready.set()), daemon=True).start()
    ready.wait(10)
    server.idle_exit()
    if not window(url):
        print(f'Scan Studio on {url}  (Ctrl-C to quit)', flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
