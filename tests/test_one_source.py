# prove che la libreria e' l'unico posto dei dati dello studio, e che tutto cio' che ne deriva le corrisponde.
# Ogni prova deve poter fallire: si rompe apposta quello che deve scoprire.
#  1. tutto via tranne la libreria (e i file): in un processo nuovo torna tutto, uguale
#  2. impronta su disco: una sessione intera scrive solo libreria, tagli, cache ricostruibili, storia, impostazioni
#  3. andata e ritorno con modifiche a caso: dopo ogni salvataggio si rilegge esattamente cio' che si e' salvato
#  4. il controllo di coerenza scopre ogni cosa rotta apposta, e non trova niente dopo una sessione pulita
#  5. il codice: nessuna scrittura negli archivi di prima; nel browser solo preferenze dell'interfaccia
import os, re, ast, json, glob, random, shutil, subprocess, sys, unittest
from helpers import REPO, scratch_root, remove_root, fake_scan, run_agent

PY = sys.executable


def norm(st):
    # cio' che conta di uno stato (senza versione, ora di salvataggio, nomi calcolati)
    sh = []
    for s in st.get('sheets') or []:
        x = {k: s.get(k) for k in ('id', 'poly', 'ops', 'label', 'holes', 'color')}
        x['on'] = s.get('on', True) is not False
        x['rot'] = int(s.get('rot') or 0)
        x['label'] = x['label'] or ''
        x['holes'] = x['holes'] or []
        if 'ocr' in s:
            x['ocr'] = s['ocr']
        x['areas'] = [{'id': a['id'], 'box': list(a['box']), 'text': a.get('text') or ''} for a in s.get('areas') or []]
        sh.append(x)
    loose = [{'id': a['id'], 'box': list(a['box']), 'text': a.get('text') or ''} for a in st.get('loose') or []]
    return {'sheets': sh, 'loose': loose, 'engine': st.get('engine')}


class Base(unittest.TestCase):
    def setUp(self):
        from studio import core
        self.root = scratch_root()
        fake_scan(os.path.join(self.root, 'inbox', 'card 1.png'),
                  sheets=[(0.3, 0.5, 80, 200, 0, (250, 250, 248)), (0.73, 0.5, 85, 200, 1, (225, 235, 250))])
        fake_scan(os.path.join(self.root, 'inbox', 'card 2.png'), seed=3,
                  sheets=[(0.5, 0.35, 150, 110, -1, (248, 246, 240)), (0.5, 0.75, 150, 100, 2, (240, 248, 246))])
        run_agent(self.root)
        core.set_root(self.root)
        self.rels = ['originals/card/card 1.png', 'originals/card/card 2.png']

    def tearDown(self):
        from studio.library import bridge
        for t in list(bridge._recut_timers.values()):
            t.cancel()
        bridge._recut_timers.clear()
        if bridge._journal_timer[0]:
            bridge._journal_timer[0].cancel()
        bridge._lib = None
        remove_root(self.root)

    def settle(self):
        # le conseguenze che lo studio fa poco dopo (tagli rifatti): qui subito
        from studio.library import bridge
        for rel, t in list(bridge._recut_timers.items()):
            t.cancel()
            bridge._recut_timers.pop(rel, None)
            bridge.recut(rel)

    def session(self, seed=1, steps=25, cut=True):
        # una sessione di lavoro a caso, come in Scan Studio: rileva, ritocca, ruota, include/esclude,
        # rinomina, testo, aree, aree sciolte, riordina, toglie, disegna; taglia; rilegge e corregge
        from studio import core
        from studio.library import bridge
        rnd = random.Random(seed)
        lib = bridge.library()
        for rel in self.rels:
            core.detect(rel, 'auto')
            if cut:
                bridge.on_export(rel, core.export(rel, log=lambda m: None))
        expect = {}
        for k in range(steps):
            rel = rnd.choice(self.rels)
            st = core.load_state(rel)
            sheets = st['sheets']
            op = rnd.choice(['rot', 'on', 'label', 'text', 'area', 'unarea', 'loose', 'unloose', 'order', 'remove', 'draw', 'edit'])
            if op == 'rot' and sheets:
                s = rnd.choice(sheets); s['rot'] = rnd.choice([0, 90, 180, 270])
            elif op == 'on' and sheets:
                s = rnd.choice(sheets); s['on'] = not s.get('on', True)
            elif op == 'label' and sheets:
                rnd.choice(sheets)['label'] = rnd.choice(['', 'cat', 'note', 'page ' + str(k)])
            elif op == 'text' and sheets:
                rnd.choice(sheets)['ocr'] = rnd.choice(['', 'Ciao', 'line one\nline two', f'text {k} — ünïcode 50% $x_1'])
            elif op == 'area' and sheets:
                s = rnd.choice(sheets); b = [rnd.randint(0, 300), rnd.randint(0, 300)]
                s.setdefault('areas', []).append({'id': f'a{k}', 'box': b + [b[0] + 60, b[1] + 40], 'text': f'area {k}'})
            elif op == 'unarea':
                s = next((x for x in sheets if x.get('areas')), None)
                if s: s['areas'].pop(rnd.randrange(len(s['areas'])))
            elif op == 'loose':
                b = [rnd.randint(0, 400), rnd.randint(0, 400)]
                st.setdefault('loose', []).append({'id': f'l{k}', 'box': b + [b[0] + 50, b[1] + 30], 'text': f'loose {k}'})
            elif op == 'unloose' and st.get('loose'):
                st['loose'].pop(rnd.randrange(len(st['loose'])))
            elif op == 'order' and len(sheets) > 1:
                sheets.reverse()
            elif op == 'remove' and len(sheets) > 1:
                sheets.pop(rnd.randrange(len(sheets)))
            elif op == 'draw':
                x, y = rnd.randint(50, 300), rnd.randint(50, 400)
                sheets.append({'id': f'm{k}', 'src': None, 'engine': 'manual', 'poly0': None, 'poly': [[x, y], [x + 120, y], [x + 120, y + 160], [x, y + 160]],
                               'ops': [], 'on': True, 'label': '', 'holes': [], 'color': '#ff8c1a'})
            elif op == 'edit' and sheets:
                s = rnd.choice(sheets); p = s['poly'][0]
                s['ops'].append({'op': 'sub', 'kind': 'poly', 'pts': [[p[0] - 3, p[1] - 3], [p[0] + 25, p[1] - 3], [p[0] + 25, p[1] + 25], [p[0] - 3, p[1] + 25]]})
            saved = core.save_state(st)
            want = norm(st)
            self.assertEqual(norm(saved), want, f'step {k} ({op}) on {rel}: what comes back differs from what was saved')
            expect[rel] = want
            if rnd.random() < 0.25:
                self.settle()
        self.settle()
        return lib, expect


class OneSource(Base):

    # 1) tutto via tranne la libreria: in un processo nuovo torna tutto, uguale
    def test_only_the_library_is_needed(self):
        from studio import core
        lib, expect = self.session(seed=11, steps=30)
        data = core.DATA
        for name in os.listdir(data):
            if name != 'replaced':                     # la storia dei tagli resta (e' storia, non stato)
                p = os.path.join(data, name)
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        code = ('import sys, json; sys.path.insert(0, %r)\n'
                'from studio import core\n'
                'core.set_root(%r)\n'
                'print(json.dumps({r: core.load_state(r) for r in %r}))\n') % (REPO, self.root, self.rels)
        out = subprocess.run([PY, '-c', code], capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        back = json.loads(out.stdout.strip().splitlines()[-1])
        for rel in self.rels:
            if rel in expect:
                self.assertEqual(norm(back[rel]), expect[rel], f'{rel} did not come back from the library alone')

    # 2) impronta su disco: solo i posti permessi
    def test_disk_footprint(self):
        from studio import core
        from studio.library import bridge
        def snap():
            out = {}
            for d, _, fs in os.walk(self.root):
                for f in fs:
                    p = os.path.join(d, f)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    out[os.path.relpath(p, self.root)] = (st.st_size, st.st_mtime_ns)
            return out
        before = snap()
        lib, _ = self.session(seed=5, steps=20)
        jd = os.path.join(self.root, 'journal')
        bridge.set_journal_dir(lib, jd); bridge.write_journal(lib)
        after = snap()
        changed = [p for p in after if before.get(p) != after[p]]
        allowed = (r'^Library\.DocuLib/', r'^cut/', r'^journal/', r'^\.scancut/studio-data/(cache|previews|replaced|models)/',
                   r'^\.scancut/studio-data/settings\.json$', r'^\.scancut/(log\.txt|done\.tsv|lock)$')
        bad = [p for p in changed if not any(re.match(a, p) for a in allowed)]
        self.assertEqual(bad, [], 'written outside the library, the cuts, caches, history and settings')
        self.assertTrue(any(p.startswith('Library.DocuLib/') for p in changed))
        self.assertFalse(glob.glob(os.path.join(core.DATA, 'state', '*')) or glob.glob(os.path.join(core.DATA, 'text', '*')))

    # 3) andata e ritorno con molte sessioni a caso (il confronto e' dentro session(), a ogni passo)
    def test_random_sessions_round_trip(self):
        for seed in range(1, 6):
            from studio.library import bridge
            self.session(seed=seed * 7, steps=30, cut=(seed % 2 == 0))
            self.assertEqual(bridge.check(bridge.library()), [], f'seed {seed}: not consistent after the session')


    def test_edit_during_a_recut_survives(self):
        # un taglio rifatto in corso non deve riscrivere lo stato letto all'inizio sopra un ritocco fatto intanto
        import threading, time
        from studio import core
        from studio.library import bridge
        rel = self.rels[0]
        core.detect(rel, 'auto')
        bridge.cut(rel, log=lambda m: None)
        st = core.load_state(rel)
        st['sheets'][0]['label'] = 'prima'
        core.save_state(st)
        bridge._recut_timers.pop(rel).cancel()
        slow, inside = core.cut_sheet, threading.Event()
        def cut_sheet(*a, **k):
            inside.set(); time.sleep(0.6)
            return slow(*a, **k)
        core.cut_sheet = cut_sheet
        try:
            t = threading.Thread(target=bridge.recut, args=(rel,))
            t.start()
            self.assertTrue(inside.wait(10))
            st = core.load_state(rel)
            st['sheets'][0]['label'] = 'durante'          # il ritocco mentre il taglio gira
            core.save_state(st)
            t.join(30)
        finally:
            core.cut_sheet = slow
        self.assertEqual(core.load_state(rel)['sheets'][0]['label'], 'durante')
        self.settle()
        self.assertEqual(bridge.check(bridge.library(), deep=True), [])

class TheCheckCanFail(Base):
    # 4) il controllo di coerenza: niente dopo una sessione pulita, e scopre ogni cosa rotta apposta

    def cut_path(self, lib):
        r = lib.db.execute("SELECT c.path FROM cut c JOIN region r ON r.id = c.region_id WHERE r.removed_at IS NULL AND r.export_on = 1 "
                           "AND c.path NOT LIKE '%/replaced/%' ORDER BY c.id DESC LIMIT 1").fetchone()
        return r['path']

    def kinds(self, lib, deep=False):
        from studio.library import bridge
        return {p['kind'] for p in bridge.check(lib, deep=deep)}

    def test_clean_session_is_clean_deep(self):
        lib, _ = self.session(seed=3, steps=15)
        from studio.library import bridge
        st = __import__('studio.core', fromlist=['core']).load_state(self.rels[0])
        st['sheets'][0]['ocr'] = 'a text for the cut'
        __import__('studio.core', fromlist=['core']).save_state(st)
        self.assertEqual(bridge.check(lib, deep=True), [])

    def test_catches_changed_pixels(self):
        import numpy as np
        from PIL import Image
        lib, _ = self.session(seed=4, steps=6)
        p = self.cut_path(lib)
        im = np.asarray(Image.open(p)).copy(); im[5, 5, :3] = (im[5, 5, :3].astype(int) + 40) % 256
        info = Image.open(p).info
        Image.fromarray(im).save(p, dpi=info.get('dpi'))
        self.assertIn('file changed outside the library', self.kinds(lib))

    def test_catches_wrong_embedded_text(self):
        if not shutil.which('exiftool'):
            self.skipTest('exiftool not installed')
        from studio import core
        lib, _ = self.session(seed=4, steps=6)
        st = core.load_state(self.rels[0]); st['sheets'][0]['on'] = True; st['sheets'][0]['ocr'] = 'right text'; core.save_state(st)
        self.settle()
        from studio.library import bridge
        cut = lib.db.execute("SELECT c.path FROM cut c JOIN region r ON r.id = c.region_id WHERE json_extract(r.source, '$.studio_id') = ? "
                             "AND r.asset_id = (SELECT id FROM asset WHERE path = ?) ORDER BY c.id DESC LIMIT 1",
                             (st['sheets'][0]['id'], os.path.realpath(core.abspath(self.rels[0])))).fetchone()
        if not cut or not os.path.exists(cut['path']):
            bridge.on_export(self.rels[0], core.export(self.rels[0], log=lambda m: None)); self.settle()
            cut = lib.db.execute("SELECT c.path FROM cut c JOIN region r ON r.id = c.region_id WHERE json_extract(r.source, '$.studio_id') = ? "
                                 "ORDER BY c.id DESC LIMIT 1", (st['sheets'][0]['id'],)).fetchone()
        self.assertEqual(bridge.check(lib), [])
        subprocess.run(['exiftool', '-q', '-overwrite_original', '-XMP-dc:Description=wrong text', cut['path']], check=True)
        kinds = self.kinds(lib)
        self.assertTrue({'cut text differs from its part', 'file changed outside the library'} & kinds, kinds)

    def test_catches_missing_cut(self):
        lib, _ = self.session(seed=4, steps=6)
        os.remove(self.cut_path(lib))
        self.assertTrue({'cut missing', 'missing file'} & self.kinds(lib))

    def test_catches_data_outside_the_library(self):
        from studio import core
        lib, _ = self.session(seed=4, steps=4, cut=False)
        os.makedirs(os.path.join(core.DATA, 'state'), exist_ok=True)
        json.dump({'rel': self.rels[0], 'sheets': []}, open(os.path.join(core.DATA, 'state', 'x.json'), 'w'))
        self.assertIn('data outside the library', self.kinds(lib))

    def test_catches_pixels_that_no_longer_match_the_part(self):
        # il taglio e' intatto per il catalogo (stesso checksum registrato), ma non e' piu' il taglio della sua parte
        from studio import core
        from studio.library import bridge
        from studio.library.db import sha256
        lib, _ = self.session(seed=4, steps=0)
        st = core.load_state(self.rels[0])
        st['sheets'][0]['on'] = True
        p0 = st['sheets'][0]['poly'][0]
        st['sheets'][0]['ops'].append({'op': 'sub', 'kind': 'poly', 'pts': [[p0[0] - 3, p0[1] - 3], [p0[0] + 40, p0[1] - 3], [p0[0] + 40, p0[1] + 40], [p0[0] - 3, p0[1] + 40]]})
        for t in list(bridge._recut_timers.values()):
            t.cancel()
        bridge._recut_timers.clear()
        bridge.schedule_recut = lambda rel, delay=0, only=None: None            # il ritaglio NON si rifa': simula un taglio rimasto indietro
        try:
            core.save_state(st)
        finally:
            import importlib
            importlib.reload(bridge)
        self.assertIn('cut older than its part', self.kinds(bridge.library(), deep=True))


class CodeAudit(unittest.TestCase):
    # 5) nel codice: nessuna scrittura negli archivi di prima; nel browser solo preferenze dell'interfaccia

    def test_no_writes_to_retired_stores(self):
        bad = []
        for f in glob.glob(os.path.join(REPO, 'studio', '**', '*.py'), recursive=True):
            src = open(f, encoding='utf-8').read()
            for m in re.finditer(r"os\.path\.join\(\s*(core\.)?DATA\s*,\s*'(state|text)'", src):
                line = src.count('\n', 0, m.start()) + 1
                # permesso solo in store.migrate_legacy (che li porta dentro e li mette da parte) e nel controllo
                where = os.path.relpath(f, REPO)
                ctx = src[max(0, m.start() - 4000):m.start()]
                fn = re.findall(r'\ndef (\w+)', ctx)
                # permesso: portarli dentro una volta (migrate_legacy, import_read_cache) e il controllo che non ci siano piu'
                if not (where.endswith('library/store.py') and fn and fn[-1] == 'migrate_legacy') and \
                        not (where.endswith('library/bridge.py') and fn and fn[-1] in ('check', 'import_read_cache')):
                    bad.append(f'{where}:{line} ({fn[-1] if fn else "?"})')
        self.assertEqual(bad, [], 'code that touches the retired JSON state or text cache')
        for f in glob.glob(os.path.join(REPO, 'studio', '**', '*.py'), recursive=True):
            tree = ast.parse(open(f, encoding='utf-8').read())
            names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            self.assertNotIn('state_path', names, f'{f}: the old JSON state path is back')

    def test_browser_storage_holds_only_preferences(self):
        js = open(os.path.join(REPO, 'studio', 'static', 'app.js'), encoding='utf-8').read()
        keys = set(re.findall(r"\bstore\('([\w.-]+)'", js))
        # le sole preferenze dell'interfaccia (larghezze, sfondo, lente, pannelli, schede aperte, ordine e filtri)
        prefs = {'navw', 'sidew', 'bg', 'loupe', 'loupez', 'densshut', 'densr', 'tabs', 'textpane', 'shut', 'exportdir', 'navhide', 'sidehide', 'textview',
                 'libmode', 'libsort', 'libdpi', 'libhideempty', 'jobsseen'}
        self.assertTrue(keys <= prefs, f'browser storage used for something that is not a preference: {sorted(keys - prefs)}')
        self.assertNotIn('boxTexts', js, 'text kept only in the window is back')
        self.assertNotIn('localStorage.setItem(', js.replace("localStorage.setItem('studio.' + k, v)", ''), 'direct browser storage outside store()')


if __name__ == '__main__':
    unittest.main()
