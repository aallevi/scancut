# prove di sicurezza: mai perdere una scansione, mai due oggetti per un file, lo scanner fermato bene.
# Uno scanimage finto (uno script) al posto di quello vero: niente scanner, niente rete.
import os, sys, stat, shutil, threading, time, unittest
import numpy as np, cv2
from PIL import Image
from helpers import scratch_root, remove_root, fake_scan, run_agent, sc

FAKE_SCANIMAGE = r'''#!/usr/bin/env python3
# scanimage finto: scrive un TIFF a pezzi, l'avanzamento su stderr come quello vero. Alla prima SIGINT si ferma
# "riportando a casa la testina" (finisce bene, segna PARKED); alla seconda esce subito (segna ABORTED)
import os, sys, time, signal
log = os.environ['FAKE_LOG']
hits = []
def on(sig, frm):
    hits.append(sig)
    open(log, 'a').write('SIGNAL\n')
    if len(hits) > 1:
        open(log, 'a').write('ABORTED\n'); os._exit(3)
signal.signal(signal.SIGINT, on); signal.signal(signal.SIGTERM, on)
for i in range(1, 101):
    if hits:
        time.sleep(0.3); open(log, 'a').write('PARKED\n'); sys.exit(0)
    sys.stdout.buffer.write(b'x' * 1000); sys.stdout.flush()
    sys.stderr.write(f'Progress: {i}.0%\r'); sys.stderr.flush()
    time.sleep(float(os.environ.get('FAKE_STEP', '0.02')))
'''


class ScannerStopTest(unittest.TestCase):
    def setUp(self):
        self.d = scratch_root()
        self.bin = os.path.join(self.d, 'scanimage')
        open(self.bin, 'w').write(FAKE_SCANIMAGE.replace('/usr/bin/env python3', sys.executable))
        os.chmod(self.bin, os.stat(self.bin).st_mode | stat.S_IEXEC)
        self.log = os.path.join(self.d, 'log')
        os.environ['FAKE_LOG'] = self.log
        from studio import scanner
        self.scanner, self.old = scanner, scanner.SCANIMAGE
        scanner.SCANIMAGE = self.bin

    def tearDown(self):
        self.scanner.SCANIMAGE = self.old
        os.environ.pop('FAKE_STEP', None)
        remove_root(self.d)

    def test_progress_and_complete_file(self):
        seen = []
        out = os.path.join(self.d, 'a.tif')
        self.scanner.scan('fake', out, 300, progress=seen.append)
        self.assertEqual(os.path.getsize(out), 100 * 1000)
        self.assertFalse(os.path.exists(out + '.part'))
        self.assertEqual(seen[-1], 100.0)
        self.assertEqual(seen, sorted(seen))

    def test_cancel_asks_once_and_waits_for_the_head(self):
        # la seconda richiesta lasciava la testina a meta': ora una sola, e si aspetta che lo scanner finisca
        os.environ['FAKE_STEP'] = '0.05'
        seen, out = [], os.path.join(self.d, 'b.tif')
        stop = lambda: bool(seen) and seen[-1] >= 20
        with self.assertRaises(self.scanner.Cancelled):
            self.scanner.scan('fake', out, 300, progress=seen.append, cancelled=stop)
        log = open(self.log).read().split()
        self.assertEqual(log, ['SIGNAL', 'PARKED'])
        self.assertFalse(os.path.exists(out) or os.path.exists(out + '.part'))

    def test_cancel_before_anything_arrives(self):
        out = os.path.join(self.d, 'c.tif')
        with self.assertRaises(self.scanner.Cancelled):
            self.scanner.scan('fake', out, 300, cancelled=lambda: True)
        # fermato prima ancora di partire (niente da riportare a casa) o fermato una volta sola: mai due
        self.assertNotIn('ABORTED', open(self.log).read() if os.path.exists(self.log) else '')
        self.assertFalse(os.path.exists(out + '.part'))


class PackedFilingTest(unittest.TestCase):
    # una radice con la libreria a pacchetto (originali dentro, in JPEG XL)
    def setUp(self):
        if not sc.jxl_tools():
            self.skipTest('cjxl/djxl missing')
        self.root = scratch_root()
        os.makedirs(os.path.join(self.root, 'Library.DocuLib', 'originals'))
        open(os.path.join(self.root, '.scancut', 'autocut-off'), 'w').close()
        sc.set_root(self.root)
        self.od = os.path.join(sc.ORIG, 'serie')

    def tearDown(self):
        remove_root(self.root)

    def inbox(self, name):
        return os.path.join(self.root, 'inbox', name)

    def test_48bit_scan_becomes_same_pixels_jxl_and_inbox_empties(self):
        p = fake_scan(self.inbox('serie 1.tif'), bits=16)
        px = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        run_agent(self.root)
        self.assertEqual(os.listdir(self.od), ['serie 1.jxl'])
        self.assertTrue(np.array_equal(sc.pixels(os.path.join(self.od, 'serie 1.jxl')), px))
        self.assertEqual(os.listdir(os.path.join(self.root, 'inbox')), [])

    def test_multipage_tiff_is_kept_as_it_came(self):
        # due pagine: OpenCV ne leggerebbe una; il controllo dei pixel passerebbe e la seconda andrebbe persa
        p = self.inbox('serie 2.tif')
        a = Image.new('RGB', (60, 40), (200, 10, 10)); b = Image.new('RGB', (60, 40), (10, 200, 10))
        a.save(p, save_all=True, append_images=[b])
        data = open(p, 'rb').read()
        run_agent(self.root)
        self.assertEqual(os.listdir(self.od), ['serie 2.tif'])
        self.assertEqual(open(os.path.join(self.od, 'serie 2.tif'), 'rb').read(), data)

    def test_cmyk_tiff_is_kept_as_it_came(self):
        p = self.inbox('serie 3.tif')
        Image.new('CMYK', (50, 30), (10, 20, 30, 40)).save(p)
        data = open(p, 'rb').read()
        run_agent(self.root)
        self.assertEqual(open(os.path.join(self.od, 'serie 3.tif'), 'rb').read(), data)

    def test_failed_conversion_still_files_the_scan(self):
        p = fake_scan(self.inbox('serie 4.png'))
        data = open(p, 'rb').read()
        old = sc.pack
        sc.pack = lambda path, out=None: None              # cjxl rotto, disco pieno...
        try:
            run_agent(self.root)
        finally:
            sc.pack = old
        self.assertEqual(open(os.path.join(self.od, 'serie 4.png'), 'rb').read(), data)
        self.assertEqual(os.listdir(os.path.join(self.root, 'inbox')), [])

    def test_repeat_of_a_converted_scan_is_recognised(self):
        p = fake_scan(self.inbox('serie 5.tif'), bits=16)
        twin = os.path.join(self.root, 'copy.tif'); shutil.copy2(p, twin)
        run_agent(self.root)
        shutil.move(twin, self.inbox('serie 9.tif'))
        run_agent(self.root)
        self.assertEqual(os.listdir(self.od), ['serie 5.jxl'])

    def test_no_hidden_leftovers(self):
        fake_scan(self.inbox('serie 6.tif'), bits=16)
        run_agent(self.root)
        self.assertEqual([f for f in os.listdir(self.od) if f.startswith('.')], [])


class RegisterOnceTest(unittest.TestCase):
    def setUp(self):
        self.root = scratch_root()
        from studio import core
        from studio.library import bridge
        self.core, self.bridge = core, bridge
        core.set_root(self.root)

    def tearDown(self):
        remove_root(self.root)

    def test_two_threads_register_a_new_scan_once(self):
        # l'archiviazione dello scanner e un trascinamento registrano insieme: un oggetto solo
        d = os.path.join(self.root, 'originals', 'serie'); os.makedirs(d)
        for i in range(4):
            fake_scan(os.path.join(d, f'serie {i + 1}.png'), seed=i + 1)
        lib = self.bridge.library()
        go = threading.Barrier(4)
        def reg():
            go.wait(); self.bridge.register_new(lib)
        ts = [threading.Thread(target=reg) for _ in range(4)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(lib.db.execute("SELECT COUNT(*) FROM item WHERE kind = 'scan'").fetchone()[0], 4)
        self.assertEqual(lib.db.execute('SELECT COUNT(*) FROM asset').fetchone()[0], 4)

    def test_studio_scans_left_behind_are_found(self):
        p = os.path.join(self.core.scanning_dir(), 'serie 1.tif')
        fake_scan(p)
        open(p + '.part', 'w').close()                       # una a meta': non si tocca
        self.assertEqual(self.core.scans_left(), [p])


if __name__ == '__main__':
    unittest.main()
