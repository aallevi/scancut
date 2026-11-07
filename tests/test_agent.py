# l'agente (scancut.py): nomi, lotti, e le regole che non si rompono mai
# (nessuna scansione persa, niente sovrascritto, ritagli identici non riscritti)
import os, unittest
from helpers import sc, scratch_root, remove_root, fake_scan, run_agent, files


class Names(unittest.TestCase):
    def test_split_name(self):
        for stem, want in [('sketchbook 3', ('sketchbook', 3)), ('sketchbook_3', ('sketchbook', 3)),
                           ('sketchbook-3', ('sketchbook', 3)), ('sketchbook3', ('sketchbook', 3)),
                           ('sketchbook 3 (2)', ('sketchbook', 3)), ('notebook 1', ('notebook', 1)),
                           ('sketchbook 04.05.14', ('sketchbook 04.05.14', None)),
                           ('12', ('12', None)), ('', ('unsorted', None))]:
            self.assertEqual(sc.split_name(stem), want, stem)

    def test_clean_stem(self):
        self.assertEqual(sc.clean_stem('  a\tb\n  c  '), 'a b c')
        self.assertEqual(sc.clean_stem('..hidden'), 'hidden')
        self.assertEqual(sc.clean_stem('...'), 'scan')

    def test_unique(self):
        r = scratch_root()
        try:
            p = os.path.join(r, 'x.png')
            self.assertEqual(sc.unique(p), p)
            open(p, 'w').close()
            self.assertEqual(sc.unique(p), os.path.join(r, 'x (2).png'))
        finally:
            remove_root(r)


class Agent(unittest.TestCase):
    def setUp(self):
        self.root = scratch_root()
        self.inbox = os.path.join(self.root, 'inbox')

    def tearDown(self):
        remove_root(self.root)

    def test_files_and_cuts(self):
        fake_scan(os.path.join(self.inbox, 'card 1.png'),
                  sheets=[(0.3, 0.5, 80, 200, 0, (250, 250, 248)), (0.73, 0.5, 85, 200, 1, (225, 235, 250))])
        run_agent(self.root)
        self.assertEqual(os.listdir(self.inbox), [])
        self.assertEqual(files(self.root, 'originals'), ['card/card 1.png'])
        self.assertEqual(files(self.root, 'cut'), ['card/card 1 a.png', 'card/card 1 b.png'])
        self.assertIn('card/card 1.png\t', open(sc.DONE).read())

    def test_identical_repeat_dropped(self):
        fake_scan(os.path.join(self.inbox, 'b 1.png'))
        run_agent(self.root)
        fake_scan(os.path.join(self.inbox, 'b 1.png'))            # stessi byte di nuovo
        run_agent(self.root)
        self.assertEqual(os.listdir(self.inbox), [])
        self.assertEqual(files(self.root, 'originals'), ['b/b 1.png'])

    def test_taken_name_gets_next_number(self):
        fake_scan(os.path.join(self.inbox, 'b 1.png'), seed=1)
        run_agent(self.root)
        fake_scan(os.path.join(self.inbox, 'b 1.png'), seed=2)    # Acquisizione Immagine ricomincia da 1
        run_agent(self.root)
        self.assertEqual(files(self.root, 'originals'), ['b/b 1.png', 'b/b 2.png'])

    def test_non_image_kept(self):
        open(os.path.join(self.inbox, 'notes 1.txt'), 'w').write('hello')
        run_agent(self.root)
        self.assertEqual(files(self.root, 'originals'), ['notes/notes 1.txt'])
        self.assertTrue(os.path.islink(os.path.join(self.root, 'failed', 'notes 1.txt')))

    def test_corrupt_image_kept(self):
        open(os.path.join(self.inbox, 'bad 1.png'), 'wb').write(b'\x89PNG not really')
        run_agent(self.root)
        self.assertEqual(files(self.root, 'originals'), ['bad/bad 1.png'])
        self.assertTrue(os.path.islink(os.path.join(self.root, 'failed', 'bad 1.png')))

    def test_autocut_off_only_files(self):
        open(os.path.join(self.root, '.scancut', 'autocut-off'), 'w').close()
        fake_scan(os.path.join(self.inbox, 'b 1.png'))
        run_agent(self.root)
        self.assertEqual(files(self.root, 'originals'), ['b/b 1.png'])
        self.assertEqual(files(self.root, 'cut'), [])

    def redo(self):
        os.remove(sc.DONE)
        run_agent(self.root)

    def test_redo_keeps_identical_cutouts(self):
        fake_scan(os.path.join(self.inbox, 'b 1.png'))
        run_agent(self.root)
        before = files(self.root, 'cut')
        self.redo()
        self.assertEqual(files(self.root, 'cut'), before)

    def test_redo_keeps_identical_cutouts_16bit(self):
        fake_scan(os.path.join(self.inbox, 'deep 1.tif'), bits=16)
        run_agent(self.root)
        before = files(self.root, 'cut')
        self.assertEqual(before, ['deep/deep 1.png'])
        self.redo()
        self.assertEqual(files(self.root, 'cut'), before)

    def test_redo_keeps_identical_cutouts_16bit_gray(self):
        fake_scan(os.path.join(self.inbox, 'grey 1.tif'), bits='gray16')
        run_agent(self.root)
        before = files(self.root, 'cut')
        self.assertEqual(before, ['grey/grey 1.png'])
        self.redo()
        self.assertEqual(files(self.root, 'cut'), before)


if __name__ == '__main__':
    unittest.main()
