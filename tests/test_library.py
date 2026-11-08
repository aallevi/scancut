# la libreria (catalogo SQLite): import senza doppioni, fissita', zone e testo con le versioni,
# ricerca, sidecar piccoli, copie del catalogo
import os, json, time, unittest
from helpers import scratch_root, remove_root, fake_scan
from studio.library.db import Library


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.dir = scratch_root()
        self.lib = Library(os.path.join(self.dir, 'Test'), create=True)
        self.scan = fake_scan(os.path.join(self.dir, 'inbox', 'notebook 1.png'))

    def tearDown(self):
        remove_root(self.dir)

    def test_import_dedup_and_fixity(self):
        a, new = self.lib.add_asset(self.scan)
        self.assertTrue(new)
        a2, new2 = self.lib.add_asset(self.scan)
        self.assertEqual((a2, new2), (a, False))                 # stessi byte: un file solo
        row = self.lib.db.execute('SELECT * FROM asset WHERE id = ?', (a,)).fetchone()
        self.assertTrue(os.path.exists(self.lib.asset_path(row)))
        self.assertEqual(self.lib.check_fixity(), [])
        with open(self.lib.asset_path(row), 'r+b') as f:         # un bit cambiato su disco
            f.seek(200); b = f.read(1); f.seek(200); f.write(bytes([b[0] ^ 1]))
        self.assertEqual(self.lib.check_fixity(), [row['uuid']])

    def test_regions_readings_corrections_search(self):
        a, _ = self.lib.add_asset(self.scan)
        it = self.lib.new_item('Notebook page', batch='notebook', assets=[a])
        sheet = self.lib.add_region(it, a, 'sheet', {'poly': [[10, 10], [500, 10], [500, 700], [10, 700]]}, color='#3399ff')
        area = self.lib.add_region(it, a, 'text', {'box': [20, 20, 300, 120]}, parent_id=sheet)
        r = self.lib.add_reading(a, 'ollama', 'Il tavolo in cui si formano combinazioni', region_id=area, model='glm-ocr')
        self.assertEqual(self.lib.search('combinazioni')[0]['title'], 'Notebook page')
        v = self.lib.correct(r, 'Il tavolo in cui si formano le combinazioni di oggetti')
        self.assertEqual(v, 1)
        cur = self.lib.db.execute('SELECT plain, corrected_version FROM current_text WHERE reading_id = ?', (r,)).fetchone()
        self.assertEqual((cur['plain'], cur['corrected_version']), ('Il tavolo in cui si formano le combinazioni di oggetti', 1))
        self.assertTrue(self.lib.search('oggetti'))
        # la lettura del motore resta com'era
        self.assertEqual(self.lib.db.execute('SELECT plain FROM reading WHERE id = ?', (r,)).fetchone()[0], 'Il tavolo in cui si formano combinazioni')

    def test_sidecar_is_small_and_complete(self):
        a, _ = self.lib.add_asset(self.scan)
        it = self.lib.new_item('Page', assets=[a])
        self.lib.add_region(it, a, 'sheet', {'box': [0, 0, 100, 100]})
        row = self.lib.db.execute('SELECT * FROM asset WHERE id = ?', (a,)).fetchone()
        side = self.lib.asset_path(row) + '.json'
        data = json.load(open(side))
        self.assertEqual(data['asset']['sha256'], row['sha256'])
        self.assertEqual(len(data['regions']), 1)
        self.assertLess(os.path.getsize(side), os.path.getsize(self.lib.asset_path(row)) / 100)

    def test_reopen_snapshots(self):
        path = self.lib.path
        Library(path)
        snaps = os.listdir(os.path.join(path, 'snapshots'))
        self.assertTrue(any(s.endswith('-open.sqlite') for s in snaps))

    def test_fast_with_many_items(self):
        # 20 000 oggetti con testo: inserimento e ricerca restano veloci
        db = self.lib.db
        t = time.time()
        with db:
            for i in range(20000):
                db.execute("INSERT INTO item (uuid, title, created_at, modified_at) VALUES (?, ?, 'x', 'x')", (f'u{i}', f'page {i}'))
                db.execute('INSERT INTO search (item_uuid, title, notes, labels, text) VALUES (?, ?, "", "", ?)',
                           (f'u{i}', f'page {i}', f'note number {i} about drawings' + (' guitar' if i % 997 == 0 else '')))
        insert = time.time() - t
        t = time.time()
        hits = self.lib.search('guitar')
        q = time.time() - t
        self.assertEqual(len(hits), 21)
        self.assertLess(q, 0.1)
        self.assertLess(insert, 10)


if __name__ == '__main__':
    unittest.main()


class BridgeTest(unittest.TestCase):
    # la cartella delle scansioni di oggi entra nella libreria; una copia ritoccata torna come versione nuova
    def setUp(self):
        from helpers import run_agent
        from studio import core
        self.root = scratch_root()
        fake_scan(os.path.join(self.root, 'inbox', 'card 1.png'),
                  sheets=[(0.3, 0.5, 80, 200, 0, (250, 250, 248)), (0.73, 0.5, 85, 200, 1, (225, 235, 250))])
        run_agent(self.root)
        core.set_root(self.root)
        self.rel = 'originals/card/card 1.png'
        st, _ = core.detect(self.rel, 'auto')
        st['sheets'][0]['ocr'] = 'hello sketchbook'
        core.save_state(st)

    def tearDown(self):
        from studio.library import bridge
        bridge._lib = None
        remove_root(self.root)

    def test_import_and_edit(self):
        from studio.library import bridge
        from PIL import Image
        lib = bridge.library()
        r = bridge.import_root(lib)
        self.assertEqual(r, {'files': 1, 'new_items': 0})          # gia' entrata quando e' stata rilevata la prima volta
        self.assertEqual(bridge.import_root(lib)['new_items'], 0)          # di nuovo: niente doppioni
        items = bridge.item_list(lib)
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]['regions'], items[0]['texts']), (2, 1))
        self.assertEqual(bridge.item_list(lib, 'sketchbook')[0]['uuid'], items[0]['uuid'])
        # una copia di lavoro "salvata da Affinity": versione nuova, legata all'originale, originale intatto
        d = bridge.item_detail(lib, items[0]['uuid'])
        a = d['assets'][0]
        work = os.path.join(self.root, 'work.png')
        im = Image.open(lib.asset_path(a)).convert('RGB'); im.putpixel((5, 5), (255, 0, 0)); im.save(work)
        before = open(lib.asset_path(a), 'rb').read()
        aid = bridge.take_edit(lib, work, {'asset': a['id'], 'item': d['item']['id'], 'app': 'Affinity', 'sha': a['sha256']})
        row = lib.db.execute('SELECT * FROM asset WHERE id = ?', (aid,)).fetchone()
        self.assertEqual((row['derived_from'], row['made_with'], row['storage']), (a['id'], 'Affinity', 'managed'))
        self.assertEqual(open(lib.asset_path(a), 'rb').read(), before)
        roles = [x['role'] for x in bridge.item_detail(lib, items[0]['uuid'])['assets']]
        self.assertEqual(roles, ['view', 'cutout', 'cutout', 'edit'])         # i ritagli gia' fatti dall'agente entrano anche loro

    def test_live_sync_and_export(self):
        from studio.library import bridge
        from studio import core
        lib = bridge.library()
        bridge.import_root(lib)
        uuid = bridge.item_list(lib)[0]['uuid']
        # un ritocco e un testo corretto nello studio
        st = core.load_state(self.rel)
        st['sheets'][0]['label'] = 'cat'
        st['sheets'][0]['ocr'] = 'hello sketchbook, corrected'
        core.save_state(st)
        bridge.sync_rel(self.rel)
        d = bridge.item_detail(lib, uuid)
        g = d['regions'][0]
        self.assertEqual((g['label'], g['text']['plain'], g['text']['corrected_version']), ('cat', 'hello sketchbook, corrected', 1))
        # export: i ritagli entrano come file dell'oggetto, legati all'originale
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))
        d = bridge.item_detail(lib, uuid)
        cuts = [a for a in d['assets'] if a['role'] == 'cutout']
        self.assertEqual(len(cuts), 2)
        self.assertTrue(all(a['derived_from'] == d['assets'][0]['id'] for a in cuts))
        self.assertEqual(lib.db.execute('SELECT COUNT(*) FROM cut').fetchone()[0], 2)
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))      # di nuovo: niente doppioni
        self.assertEqual(lib.db.execute('SELECT COUNT(*) FROM cut').fetchone()[0], 2)

    def test_cutout_text_follows_library(self):
        import subprocess, shutil, numpy as np
        from PIL import Image
        from studio.library import bridge
        from studio.library.db import sha256
        from studio import core
        if not shutil.which('exiftool'):
            self.skipTest('exiftool not installed')
        lib = bridge.library()
        bridge.import_root(lib)
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))
        st = core.load_state(self.rel)
        st['sheets'][0]['ocr'] = 'POOL LOVER\nsecond line'                # riletto dopo l'export
        core.save_state(st)
        bridge.sync_rel(self.rel)
        e = lib.db.execute('SELECT e.path, e.sha256, r.uuid FROM cut e JOIN region r ON r.id = e.region_id '
                           "WHERE json_extract(r.source, '$.studio_id') = ?", (st['sheets'][0]['id'],)).fetchone()
        out = subprocess.run(['exiftool', '-s3', '-XMP-dc:Description', '-XMP-dc:Identifier', e['path']], capture_output=True, text=True).stdout
        self.assertIn('POOL LOVER', out)
        self.assertIn('second line', out)                               # a capo conservati
        self.assertIn(f'region={e["uuid"]}', out)                       # il file punta alla sua zona
        self.assertEqual(sha256(e['path']), e['sha256'])                # il catalogo sa il checksum nuovo
        cut = core.cut_sheet(self.rel, st['sheets'][0])[0]
        self.assertTrue(np.array_equal(np.asarray(Image.open(e['path'])), cut))   # pixel identici
        ev = lib.db.execute("SELECT detail FROM event WHERE type = 'metadata' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIn('text changed after export', ev[0])

    def test_cutout_name_matching(self):
        # "card 12.png" non e' un ritaglio di "card 1": solo "card 1.png" e "card 1 a.png", "card 1 b.png"
        import re
        stem = 'card 1'
        pat = re.compile(re.escape(stem) + r'( [a-z])?')
        self.assertTrue(pat.fullmatch('card 1') and pat.fullmatch('card 1 b'))
        self.assertFalse(pat.fullmatch('card 12') or pat.fullmatch('card 1 ab') or pat.fullmatch('card 6'))

    def test_correction_from_cutout_goes_everywhere(self):
        from studio.library import bridge
        from studio import core
        lib = bridge.library()
        bridge.import_root(lib)
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))
        cut = [n for sid, n in core.out_names(self.rel) if sid == core.load_state(self.rel)['sheets'][0]['id']][0]
        t = bridge.texts_for_rel(lib, core.relpath(cut))
        self.assertEqual([x['plain'] for x in t], ['hello sketchbook'])      # il ritaglio vede il testo della sua zona
        bridge.correct_text(lib, t[0]['reading'], 'hello, sketchbook!')
        self.assertEqual(bridge.texts_for_rel(lib, core.relpath(cut))[0]['plain'], 'hello, sketchbook!')
        self.assertEqual(core.load_state(self.rel)['sheets'][0]['ocr'], 'hello, sketchbook!')   # anche sulla scansione

    def test_secondary_areas(self):
        # un'area letta dentro un foglio: zona figlia nella libreria, con il suo testo; il ritaglio del foglio punta a entrambi
        from studio.library import bridge
        from studio import core
        lib = bridge.library()
        bridge.import_root(lib)
        st = core.load_state(self.rel)
        st['sheets'][0]['areas'] = [{'id': 'a1', 'box': [40, 60, 200, 120], 'text': 'small note', 'reader': 'GLM-OCR'}]
        core.save_state(st)
        bridge.sync_rel(self.rel)
        rows = lib.db.execute("SELECT r.kind, p.kind AS parent FROM region r JOIN region p ON p.id = r.parent_id").fetchall()
        self.assertEqual([tuple(r) for r in rows], [('text', 'sheet')])
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))
        cut = [n for sid, n in core.out_names(self.rel) if sid == st['sheets'][0]['id']][0]
        texts = sorted(t['plain'] for t in bridge.texts_for_rel(lib, core.relpath(cut)))
        self.assertEqual(texts, ['hello sketchbook', 'small note'])
        st['sheets'][0]['areas'][0]['text'] = 'small note, fixed'          # corretta nello studio
        core.save_state(st)
        bridge.sync_rel(self.rel)
        self.assertIn('small note, fixed', [t['plain'] for t in bridge.texts_for_rel(lib, core.relpath(cut))])

    def test_rotation_is_one_thing(self):
        import numpy as np
        from PIL import Image
        from studio.library import bridge
        from studio.library.db import sha256
        from studio import core
        lib = bridge.library()
        bridge.import_root(lib)
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))
        sid = core.load_state(self.rel)['sheets'][0]['id']
        cut = [n for s, n in core.out_names(self.rel) if s == sid][0]
        w0, h0 = Image.open(cut).size
        # 1) girato il ritaglio: la zona e il foglio dello studio girano con lui
        bridge.on_cutouts_rotated(core.rotate_files([core.relpath(cut)], 90, log=lambda m: None), 90)
        reg = lib.db.execute("SELECT rotation FROM region WHERE json_extract(source, '$.studio_id') = ?", (sid,)).fetchone()
        self.assertEqual(reg['rotation'], 90)
        self.assertEqual(core.load_state(self.rel)['sheets'][0]['rot'], 90)
        a = lib.db.execute('SELECT * FROM asset WHERE path = ?', (cut,)).fetchone()
        self.assertEqual((a['width'], a['height'], a['sha256']), (h0, w0, sha256(cut)))
        self.assertEqual([w['status'] for w in core.export(self.rel, log=lambda m: None) if w['id'] == sid], ['identical'])
        # 2) girato il foglio nello studio: il ritaglio gia' fatto gira con lui
        st = core.load_state(self.rel); st['sheets'][0]['rot'] = 180; core.save_state(st)
        bridge.sync_rel(self.rel)
        self.assertTrue(np.array_equal(np.asarray(Image.open(cut)), core.cut_sheet(self.rel, st['sheets'][0])[0]))
        self.assertEqual(lib.db.execute('SELECT sha256 FROM asset WHERE path = ?', (cut,)).fetchone()[0], sha256(cut))

    def test_cut_follows_its_part(self):
        # cambia la zona gia' tagliata: il taglio si rifa' uguale alla zona; i file di prima restano nella storia
        import numpy as np
        from PIL import Image
        from studio.library import bridge
        from studio import core
        lib = bridge.library()
        bridge.import_root(lib)
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))
        st = core.load_state(self.rel)
        a, b = st['sheets'][0], st['sheets'][1]
        x0, y0 = min(p[0] for p in a['poly']), min(p[1] for p in a['poly'])
        a['ops'].append({'op': 'sub', 'kind': 'poly', 'pts': [[x0 - 5, y0 - 5], [x0 + 60, y0 - 5], [x0 + 60, y0 + 60], [x0 - 5, y0 + 60]]})
        b['on'] = False                                                    # tolta dal taglio
        core.save_state(st)
        bridge.sync_rel(self.rel)
        bridge._recut_timers.pop(self.rel).cancel()                        # nel test: subito, non fra 2.5 s
        bridge.recut(self.rel)
        out = dict(core.out_names(self.rel))
        self.assertTrue(np.array_equal(np.asarray(Image.open(out[a['id']])), core.cut_sheet(self.rel, a)[0]))   # uguale alla zona
        self.assertNotIn(b['id'], out)
        kept = [os.path.join(dp, f) for dp, _, fs in os.walk(os.path.join(core.DATA, 'replaced')) for f in fs]
        self.assertGreaterEqual(len(kept), 2)                              # il vecchio taglio di a e quello di b: nella storia
        self.assertEqual(len([x for x in os.listdir(os.path.dirname(out[a['id']]))]), 1)     # nella cartella: solo il taglio attuale
        self.assertTrue(lib.db.execute("SELECT 1 FROM event WHERE type = 'superseded'").fetchone())

    def test_series_is_data(self):
        # la serie e' una cosa nel catalogo; un file fuori dalle cartelle non ne ha una (niente nomi indovinati)
        import shutil
        from studio.library import bridge
        from studio import core
        fake_scan(os.path.join(core.ROOT, 'originals', 'IMG_1234.png'), seed=7)
        lib = bridge.library()
        bridge.import_root(lib)
        series = {x['name']: x['items'] for x in bridge.series_list(lib)}
        self.assertEqual(series, {'card': 1, None: 1})
        self.assertEqual(lib.db.execute("SELECT COUNT(*) FROM series WHERE name = 'IMG'").fetchone()[0], 0)

    def test_journal_latex(self):
        # le trascrizioni come LaTeX: un file per oggetto, journal.tex, scanstudio.sty; caratteri speciali protetti
        from studio.library import bridge, journal
        from studio import core
        lib = bridge.library()
        bridge.import_root(lib)
        st = core.load_state(self.rel)
        st['sheets'][0]['ocr'] = '# Title\n- one & two\n50% of $5_x'
        core.save_state(st)
        bridge.sync_rel(self.rel)
        d = os.path.join(self.root, 'journal')
        r = journal.write(lib, d)
        self.assertEqual(r['files'], 1)
        tex = open(os.path.join(d, [f for f in os.listdir(d) if f.endswith('.tex') and f != 'journal.tex'][0])).read()
        self.assertIn(r'\paragraph{Title}', tex)
        self.assertIn(r'\item one \& two', tex)
        self.assertIn(r'50\% of \$5\_x', tex)
        self.assertIn('scanstudio://item/', tex)
        self.assertIn(r'\input{', open(os.path.join(d, 'journal.tex')).read())
        self.assertTrue(os.path.exists(os.path.join(d, 'scanstudio.sty')))

    def test_reading_a_cut_is_reading_its_part(self):
        # "leggi il documento intero" su un taglio: e' il testo della sua parte, visibile anche sulla fonte
        from studio.library import bridge
        from studio import core
        lib = bridge.library()
        bridge.import_root(lib)
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))
        sid = core.load_state(self.rel)['sheets'][1]['id']
        cut = core.relpath([n for s, n in core.out_names(self.rel) if s == sid][0])
        bridge.on_read_doc(cut, 'read on the cut')
        self.assertEqual([s.get('ocr') for s in core.load_state(self.rel)['sheets'] if s['id'] == sid], ['read on the cut'])
        self.assertIn('read on the cut', [t['plain'] for t in bridge.texts_for_rel(lib, cut)])
        bridge.on_read_doc(cut, 'read on the cut')                          # di nuovo uguale: nessun doppione
        self.assertEqual(lib.db.execute("SELECT COUNT(*) FROM reading WHERE plain = 'read on the cut'").fetchone()[0], 1)


    def test_scanned_file_is_registered_with_its_settings(self):
        # una scansione: registrata appena fatta (impostazioni, serie), fra le fonti, nella libreria, senza "aggiorna"
        from studio import core
        from studio.library import bridge
        lib = bridge.library()
        out = fake_scan(os.path.join(self.root, 'inbox', 'session 1.tif'), seed=5)
        bridge.record_capture(lib, out, 'scanner', series='session', device='test:lide', settings={'res': 600, 'mode': 'Color', 'area': [0, 0, 210, 297]})
        core.file_inbox()
        new = bridge.register_new(lib)
        self.assertEqual(bridge.new_rels(lib, new), ['originals/session/session 1.tif'])
        a = lib.db.execute("SELECT * FROM asset WHERE path LIKE '%session 1.tif'").fetchone()
        cap = bridge.capture_of(lib, a['id'])
        self.assertEqual((cap['how'], cap['device'], cap['settings']['res']), ('scanner', 'test:lide', 600))
        it = lib.db.execute('SELECT s.name FROM item i JOIN item_asset ia ON ia.item_id = i.id JOIN series s ON s.id = i.series_id WHERE ia.asset_id = ?', (a['id'],)).fetchone()
        self.assertEqual(it[0], 'session')
        self.assertEqual(bridge.register_new(lib), [])                  # di nuovo: niente doppioni

    def test_agent_is_only_this_roots(self):
        # l'agente di un'altra cartella di scansioni non e' il nostro (l'anteprima non deve muovere le vere)
        from studio import core
        label = core.agent_label()
        if label:
            import plistlib, glob
            f = next(x for x in glob.glob(os.path.expanduser('~/Library/LaunchAgents/*scancut*.plist')) if plistlib.load(open(x, 'rb')).get('Label') == label)
            self.assertIn(os.path.realpath(os.path.join(self.root, 'inbox')), [os.path.realpath(w) for w in plistlib.load(open(f, 'rb'))['WatchPaths']])

    def test_places_follow_the_rules(self):
        # posti come nell'archivio: un posto solo per cosa, numeri liberi nel posto, niente giri, eredita dalla fonte
        import sqlite3
        from studio.library import bridge
        lib = bridge.library()
        chest = bridge.save_place(lib, name='Chest', number=1)
        box = bridge.save_place(lib, name='Box 24', parent=chest, number=24)
        folder = bridge.save_place(lib, name='Folder 5', parent=box, number=5)
        it = lib.db.execute('SELECT uuid FROM item').fetchone()[0]
        regs = [r[0] for r in lib.db.execute("SELECT uuid FROM region WHERE kind = 'sheet' AND removed_at IS NULL AND parent_id IS NULL ORDER BY position")]
        bridge.put(lib, items=[it], place=folder, category='drawing')
        rid = lib.db.execute('SELECT id FROM region WHERE uuid = ?', (regs[0],)).fetchone()[0]
        w = bridge.where_kept(lib, rid)
        self.assertEqual((w['place'], w['own_place'], w['category'], w['address']), (folder, False, 'drawing', '1 · 24 · 5 · ?'))
        bridge.put(lib, regions=[regs[0]], place=folder, number=3)
        self.assertEqual(bridge.where_kept(lib, rid)['address'], '1 · 24 · 5 · 3')
        with self.assertRaises(sqlite3.IntegrityError):              # due cose, un numero: no
            bridge.put(lib, regions=[regs[1]], place=folder, number=3)
        with self.assertRaises(sqlite3.IntegrityError):              # un posto dentro se stesso: no
            bridge.save_place(lib, uuid=chest, name='Chest', parent=folder, number=1)
        with self.assertRaises(sqlite3.IntegrityError):              # una scatola nuova con il numero di una cosa: no
            bridge.save_place(lib, name='Folder 3', parent=folder, number=3)
        with self.assertRaises(sqlite3.IntegrityError):              # un posto che tiene cose non si cancella
            bridge.save_place(lib, uuid=folder, delete=True)
        with self.assertRaises(sqlite3.IntegrityError):              # categorie: solo quelle che ci sono
            bridge.put(lib, regions=[regs[0]], category='nonsense')
        self.assertEqual(bridge.resolve_address(lib, '1 · 24 · 5'), folder)
        lib.db.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('places_in', ?)", (json.dumps(chest),)); lib.db.commit()
        self.assertEqual(bridge.resolve_address(lib, '24-05'), folder)   # come le note di Eagle: scatola 24, cartella 5
        self.assertTrue(lib.db.execute("SELECT 1 FROM event WHERE type = 'move'").fetchone())

    def test_cut_of_a_cut_belongs_to_both(self):
        # un taglio ritagliato: i pezzi sono un oggetto loro, figlio dell'oggetto d'origine; posto e categoria
        # vengono dalla parte da cui e' nato il taglio
        from studio import core
        from studio.library import bridge
        lib = bridge.library()
        w = bridge.cut(self.rel, log=lambda m: None)
        cut_rel = core.relpath(next(x['path'] for x in w if x['status'] in ('written', 'identical')))
        src_item = lib.db.execute("SELECT i.id, i.uuid FROM item i JOIN item_asset ia ON ia.item_id = i.id JOIN asset a ON a.id = ia.asset_id WHERE a.path LIKE '%originals/card/card 1.png'").fetchone()
        box = bridge.save_place(lib, name='Box 3', number=3)
        bridge.put(lib, items=[src_item['uuid']], place=box, category='document')
        st, _ = core.detect(cut_rel, 'auto')
        self.assertTrue(st['sheets'])
        piece = lib.db.execute("SELECT * FROM item WHERE kind = 'piece'").fetchone()
        self.assertEqual(piece['parent_id'], src_item['id'])                   # appartiene anche all'oggetto d'origine
        rid = lib.db.execute('SELECT id FROM region WHERE item_id = ? AND removed_at IS NULL', (piece['id'],)).fetchone()[0]
        w2 = bridge.where_kept(lib, rid)
        self.assertEqual((w2['place'], w2['category']), (box, 'document'))
        self.assertIn(src_item['uuid'], [i['uuid'] for i in bridge.item_list(lib, place=box)])

    def test_trash_put_back_and_empty(self):
        # cestino: la fonte e i suoi tagli spariscono dalle viste, tornano esattamente dov'erano; svuotato, via davvero
        from studio import core
        from studio.library import bridge
        lib = bridge.library()
        w = bridge.cut(self.rel, log=lambda m: None)
        cuts = [x['path'] for x in w if x['status'] in ('written', 'identical')]
        src = core.abspath(self.rel)
        it = lib.db.execute("SELECT i.uuid FROM item i JOIN item_asset ia ON ia.item_id = i.id JOIN asset a ON a.id = ia.asset_id WHERE a.path = ?", (os.path.realpath(src),)).fetchone()[0]
        self.assertEqual(bridge.trash(lib, items=[it]), 1)
        self.assertFalse(os.path.exists(src) or any(os.path.exists(c) for c in cuts))
        self.assertNotIn(it, [x['uuid'] for x in bridge.item_list(lib)])
        self.assertEqual(bridge.check(lib, deep=True), [])                       # coerente anche con cose nel cestino
        t = bridge.trash_list(lib)[0]
        self.assertTrue(bridge.restore(lib, t['uuid']))
        self.assertTrue(os.path.exists(src) and all(os.path.exists(c) for c in cuts))
        self.assertIn(it, [x['uuid'] for x in bridge.item_list(lib)])
        self.assertEqual(bridge.check(lib, deep=True), [])
        # un taglio solo: la sua parte esce dal taglio finche' non torna; poi svuotato per sempre
        c = lib.db.execute('SELECT uuid FROM asset WHERE path = ?', (cuts[0],)).fetchone()[0]
        bridge.trash(lib, cuts=[c])
        self.assertFalse(any(s['on'] for s in core.load_state(self.rel)['sheets'] if s['id'] == 's1') and os.path.exists(cuts[0]))
        self.assertEqual(bridge.empty_trash(lib, older_than_days=1), 0)          # non ancora il suo tempo
        self.assertEqual(bridge.empty_trash(lib), 1)
        self.assertFalse(lib.db.execute('SELECT 1 FROM asset WHERE uuid = ?', (c,)).fetchone())
        self.assertFalse(os.listdir(os.path.join(core.DATA, 'trash')) if os.path.isdir(os.path.join(core.DATA, 'trash')) else [])
        self.assertEqual(bridge.check(lib, deep=True), [])

    def test_jpeg_cut_turns_into_same_pixels_png(self):
        # un JPEG portato da fuori: girato, diventa un PNG con gli stessi pixel; il JPEG resta nella storia
        import numpy as np
        from PIL import Image
        from studio import core
        from studio.library import bridge
        lib = bridge.library()
        d = os.path.join(self.root, 'cut', 'added'); os.makedirs(d, exist_ok=True)
        jpg = os.path.join(d, 'ticket.jpg')
        Image.fromarray((np.random.default_rng(2).random((60, 90, 3)) * 255).astype('uint8')).save(jpg, quality=80)
        bridge.add_cut_file(lib, jpg)
        before = np.asarray(Image.open(jpg).convert('RGB'))
        done = core.rotate_files(['cut/added/ticket.jpg'], 90)
        bridge.on_cutouts_rotated(done, 90)
        self.assertEqual(done, ['cut/added/ticket.png'])
        self.assertTrue(np.array_equal(np.rot90(before, k=-1), np.asarray(Image.open(core.abspath(done[0])).convert('RGB'))))
        self.assertFalse(os.path.exists(jpg))
        self.assertTrue(lib.db.execute('SELECT 1 FROM asset WHERE path = ?', (os.path.realpath(core.abspath(done[0])),)).fetchone())
        self.assertEqual(bridge.check(lib), [])

class OneSourceTest(unittest.TestCase):
    # la libreria e' l'unico posto: niente file di stato, niente cache; tutto cio' che deriva le corrisponde
    def setUp(self):
        from helpers import run_agent
        from studio import core
        self.root = scratch_root()
        fake_scan(os.path.join(self.root, 'inbox', 'card 1.png'),
                  sheets=[(0.3, 0.5, 80, 200, 0, (250, 250, 248)), (0.73, 0.5, 85, 200, 1, (225, 235, 250))])
        run_agent(self.root)
        core.set_root(self.root)
        self.rel = 'originals/card/card 1.png'

    def tearDown(self):
        from studio.library import bridge
        for t in list(bridge._recut_timers.values()):
            t.cancel()
        bridge._recut_timers.clear()
        bridge._lib = None
        remove_root(self.root)

    def test_no_state_outside_the_library(self):
        from studio import core
        st, _ = core.detect(self.rel, 'auto')
        st['sheets'][0]['ocr'] = 'hello'
        st['loose'] = [{'id': 'l1', 'box': [5, 5, 60, 40], 'text': 'margin note'}]
        core.save_state(st)
        self.assertFalse(os.path.exists(os.path.join(core.DATA, 'state')) and os.listdir(os.path.join(core.DATA, 'state')))
        back = core.load_state(self.rel)
        self.assertEqual(back['sheets'][0]['ocr'], 'hello')
        self.assertEqual([(a['id'], a['text']) for a in back['loose']], [('l1', 'margin note')])
        st = core.load_state(self.rel); st['loose'] = []; core.save_state(st)            # tolta: non si vede, resta nella storia
        self.assertEqual(core.load_state(self.rel)['loose'], [])

    def test_legacy_files_move_in_once(self):
        import json, hashlib
        from studio import core
        from studio.library import bridge
        # uno stato scritto come file dalla versione di prima, e una lettura in cache
        sd = os.path.join(core.DATA, 'state'); os.makedirs(sd, exist_ok=True)
        poly = [[100, 100], [400, 100], [400, 600], [100, 600]]
        json.dump({'rel': self.rel, 'engine': 'manual', 'version': 3, 'sheets': [{'id': 's1', 'src': None, 'poly0': None, 'poly': poly,
                   'ops': [], 'on': True, 'label': 'old', 'ocr': 'from the old file'}]},
                  open(os.path.join(sd, hashlib.sha1(self.rel.encode()).hexdigest()[:20] + '.json'), 'w'))
        bridge._lib = None
        lib = bridge.library()
        from studio.library import store
        store.migrate_legacy(lib)
        st = core.load_state(self.rel)
        self.assertEqual([(s['label'], s['ocr']) for s in st['sheets']], [('old', 'from the old file')])
        self.assertFalse(os.path.isdir(sd))                                               # tenuta da parte
        self.assertTrue([d for d in os.listdir(core.DATA) if d.startswith('state.migrated-')])

    def test_everything_consistent_after_a_session(self):
        from studio import core
        from studio.library import bridge
        lib = bridge.library()
        st, _ = core.detect(self.rel, 'auto')
        bridge.on_export(self.rel, core.export(self.rel, log=lambda m: None))
        st = core.load_state(self.rel)
        st['sheets'][0]['ocr'] = 'first'
        st['sheets'][1]['rot'] = 90
        core.save_state(st)                                     # testo + rotazione: il taglio gira, i metadati cambiano
        t = bridge.texts_for_rel(lib, core.relpath(dict(core.out_names(self.rel))[st['sheets'][0]['id']]))
        bridge.correct_text(lib, t[0]['reading'], 'first, corrected')
        st = core.load_state(self.rel)
        x0, y0 = min(p[0] for p in st['sheets'][0]['poly']), min(p[1] for p in st['sheets'][0]['poly'])
        st['sheets'][0]['ops'].append({'op': 'sub', 'kind': 'poly', 'pts': [[x0 - 5, y0 - 5], [x0 + 50, y0 - 5], [x0 + 50, y0 + 50], [x0 - 5, y0 + 50]]})
        core.save_state(st)                                     # contorno cambiato: il taglio si rifa'
        bridge._recut_timers.pop(self.rel).cancel()
        bridge.recut(self.rel)
        self.assertEqual(bridge.check(lib, deep=True), [])
