# lo studio: percorsi solo dentro la radice, stato dei ritocchi, esportazione uguale all'agente,
# server che risponde solo in locale
import os, json, threading, unittest, urllib.request, urllib.error
from helpers import sc, scratch_root, remove_root, fake_scan, run_agent, files
from studio import core, server


def setUpModule():
    global ROOT
    ROOT = scratch_root()
    fake_scan(os.path.join(ROOT, 'inbox', 'card 1.png'),
              sheets=[(0.3, 0.5, 80, 200, 0, (250, 250, 248)), (0.73, 0.5, 85, 200, 1, (225, 235, 250))])
    run_agent(ROOT)                      # l'agente taglia: i suoi ritagli sono il riferimento
    core.set_root(ROOT)


def tearDownModule():
    remove_root(ROOT)


REL = 'originals/card/card 1.png'


class Paths(unittest.TestCase):
    def test_outside_refused(self):
        for bad in ('../x', '/etc/passwd', 'originals/../../x'):
            with self.assertRaises(ValueError, msg=bad):
                core.abspath(bad)

    def test_symlink_outside_refused(self):
        link = os.path.join(ROOT, 'originals', 'card', 'escape.png')
        os.symlink('/etc/hosts', link)
        try:
            with self.assertRaises(ValueError):
                core.abspath('originals/card/escape.png')
        finally:
            os.remove(link)

    def test_homebrew_on_path(self):
        # dal Dock il PATH e' corto: exiftool, cjxl, djxl stanno in Homebrew
        self.assertIn('/opt/homebrew/bin', os.environ['PATH'].split(':'))


class Studio(unittest.TestCase):
    def test_tree_and_listing(self):
        top = {n['name']: n for n in core.tree()}
        self.assertEqual(top['originals']['children'][0]['count'], 1)
        self.assertEqual([x['name'] for x in core.listing('originals/card')], ['card 1.png'])

    def test_untouched_export_same_as_agent(self):
        st, meta = core.detect(REL, 'auto')
        self.assertEqual(len(st['sheets']), 2)
        written = core.export(REL)
        self.assertEqual([w['status'] for w in written], ['identical', 'identical'])
        self.assertEqual(files(ROOT, 'cut'), ['card/card 1 a.png', 'card/card 1 b.png'])

    def test_edit_then_export_new_copy(self):
        st, _ = core.detect(REL, 'auto')
        sh = st['sheets'][0]
        p = sh['poly']
        x0, y0 = min(q[0] for q in p), min(q[1] for q in p)
        # un quadrato tolto dall'angolo: il ritaglio cambia, il vecchio resta, il nuovo prende (2)
        sh['ops'].append({'op': 'sub', 'kind': 'poly', 'pts': [[x0 - 5, y0 - 5], [x0 + 40, y0 - 5], [x0 + 40, y0 + 40], [x0 - 5, y0 + 40]]})
        core.save_state(st)
        written = core.export(REL)
        self.assertEqual(sorted(w['status'] for w in written), ['identical', 'written'])
        self.assertIn('card/card 1 a (2).png', files(ROOT, 'cut'))
        os.remove(os.path.join(ROOT, 'cut', 'card', 'card 1 a (2).png'))

    def full(self, rel, sheet, W, H):
        import numpy as np
        y, x, M, _, _ = core.sheet_mask(rel, sheet)
        F = np.zeros((H, W), bool)
        F[y:y + M.shape[0], x:x + M.shape[1]] = M
        return F

    def test_invert(self):
        import copy, numpy as np
        st, _ = core.detect(REL, 'auto')
        sh = st['sheets'][0]
        info = core.info(REL)
        W, H = info['w'], info['h']
        inv = copy.deepcopy(sh)
        inv['ops'].append({'op': 'inv', 'kind': 'inv', 'pts': [[0, 0], [W, H]]})
        A, I = self.full(REL, sh, W, H), self.full(REL, inv, W, H)
        self.assertFalse((A & I).any())
        self.assertTrue((A | I).all())
        # ritocco dopo l'inversione, poi di nuovo inverti: il ritocco resta, invertito
        cut = {'op': 'sub', 'kind': 'poly', 'pts': [[0, 0], [60, 0], [60, 60], [0, 60]]}
        inv['ops'] += [cut, {'op': 'inv', 'kind': 'inv', 'pts': [[0, 0], [W, H]]}]
        T = self.full(REL, inv, W, H)
        self.assertTrue(T[:60, :60].all())
        self.assertTrue(np.array_equal(T[100:, 100:], A[100:, 100:]))

    def test_rotate_file_turns_sheets(self):
        import shutil, numpy as np
        from PIL import Image
        # un ritaglio aperto nello studio, con le sue sagome, poi girato di 90 gradi
        src = os.path.join(ROOT, 'cut', 'card', 'card 1 a.png')
        dst = os.path.join(ROOT, 'cut', 'card', 'turn 1.png')
        shutil.copy2(src, dst)
        rel = 'cut/card/turn 1.png'
        try:
            st, _ = core.detect(rel, 'auto')
            info = core.info(rel)
            W, H = info['w'], info['h']
            before = [self.full(rel, x, W, H) for x in st['sheets']]
            core.rotate_files([rel], 90, log=lambda m: None)
            st2 = core.load_state(rel)
            info2 = core.info(rel)
            self.assertEqual((info2['w'], info2['h']), (H, W))
            after = [self.full(rel, x, H, W) for x in st2['sheets']]
            for b, a in zip(before, after):
                self.assertTrue(np.array_equal(np.rot90(b, -1), a))
        finally:
            for f in os.listdir(os.path.join(ROOT, 'cut', 'card')):
                if f.startswith('turn 1'):
                    p = os.path.join(ROOT, 'cut', 'card', f)
                    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    def test_template_names(self):
        st = {'rel': REL, 'sheets': [{'id': 's1', 'on': True}, {'id': 's2', 'on': False}, {'id': 's3', 'on': True, 'label': 'cat'}]}
        names = [os.path.relpath(p, core.ROOT) for _, p in core.out_names(REL, st)]
        self.assertEqual(names, ['cut/card/card 1 a.png', 'cut/card/card 1 b.png'])


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        server.JOBS = server.Jobs()
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, path, body=None, headers=None):
        h = {'X-Studio': '1'} if body is not None else {}
        h.update(headers or {})
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}/api/{path}',
                                     json.dumps(body).encode() if body is not None else None, h)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b'null')
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_ping(self):
        code, r = self.call('ping')
        self.assertEqual(code, 200)
        self.assertIn('version', r)

    def test_other_host_refused(self):
        self.assertEqual(self.call('ping', headers={'Host': 'evil.example'})[0], 403)

    def test_post_needs_header(self):
        code, _ = self.call('settings', {}, headers={'X-Studio': '0'})
        self.assertEqual(code, 403)

    def test_outside_path_refused(self):
        code, _ = self.call('info?rel=../../etc/passwd')
        self.assertNotEqual(code, 200)

    def test_unknown_job_is_404(self):
        self.assertEqual(self.call('job?id=nope')[0], 404)
        self.assertEqual(self.call('cancel', {'id': 'nope'})[0], 404)

    def test_state_conflict(self):
        _, st = self.call('state?rel=' + urllib.parse.quote(REL))
        stale = dict(st, version=st['version'] - 1)
        self.assertEqual(self.call('state', {'state': stale})[0], 409)


import urllib.parse  # noqa: E402

if __name__ == '__main__':
    unittest.main()
