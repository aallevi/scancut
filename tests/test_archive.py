# l'archivio (il sito): ogni parte e' un record suo, con il testo; la fonte e' il record di cui le parti sono
# "Part of"; i testi possono viaggiare dentro la parte o come record loro. Mandare due volte non fa doppioni.
import os, json, unittest
from helpers import scratch_root, remove_root, fake_scan, run_agent


class FakeDirectus:
    # un Directus finto: tiene records, files e item_kinds in memoria, come farebbe il vero
    def __init__(self):
        self.token = 'x'
        self.records, self.files, self.kinds, self.calls = {}, {}, [], []

    def call(self, method, path, body=None, params=None, files=None):
        self.calls.append((method, path))
        if path == '/items/records' and method == 'GET':
            return list(self.records.values())
        if path == '/items/item_kinds' and method == 'GET':
            return self.kinds
        if path == '/items/item_kinds' and method == 'POST':
            k = {'id': len(self.kinds) + 1, **body}; self.kinds.append(k); return k
        if path == '/files' and method == 'POST':
            fid = f'file-{len(self.files) + 1}'; self.files[fid] = files['file'][0]; return {'id': fid}
        if path.startswith('/files/') and method == 'PATCH':
            return {}
        if path == '/items/records' and method == 'POST':
            rid = f'rec-{len(self.records) + 1}'
            self.records[rid] = {'id': rid, **body, 'media': [m['directus_files_id'] for m in body.get('media', [])]}
            return self.records[rid]
        if path.startswith('/items/records/') and method == 'PATCH':
            r = self.records[path.rsplit('/', 1)[1]]
            r.update(body)
            if 'media' in body:
                r['media'] = [m['directus_files_id'] for m in body['media']]
            return r
        raise AssertionError(f'unexpected {method} {path}')

    def all(self, collection, fields, **filters):
        return self.call('GET', f'/items/{collection}')


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        from studio import core
        from studio.library import bridge
        self.root = scratch_root()
        fake_scan(os.path.join(self.root, 'inbox', 'card 1.png'),
                  sheets=[(0.3, 0.5, 80, 200, 0, (250, 250, 248)), (0.73, 0.5, 85, 200, 1, (225, 235, 250))])
        run_agent(self.root)
        core.set_root(self.root)
        self.rel = 'originals/card/card 1.png'
        st, _ = core.detect(self.rel, 'auto')
        st['sheets'][0]['ocr'] = 'hello sketchbook'
        st['sheets'][0]['label'] = 'guitar'
        core.save_state(st)
        self.lib = bridge.library()
        bridge.cut(self.rel, log=lambda m: None)

    def tearDown(self):
        from studio.library import bridge
        bridge._lib = None
        remove_root(self.root)

    def test_every_part_is_an_item(self):
        # ogni foglio ha il suo item (kind part), figlio della fonte; posto e categoria stanno li'
        from studio.library import bridge
        lib = self.lib
        src = lib.db.execute("SELECT * FROM item WHERE kind = 'scan'").fetchone()
        parts = lib.db.execute("SELECT p.*, g.label FROM item p JOIN region g ON g.id = p.region_id WHERE p.kind = 'part' ORDER BY g.position").fetchall()
        self.assertEqual(len(parts), 2)
        self.assertEqual({p['parent_id'] for p in parts}, {src['id']})
        self.assertEqual(parts[0]['title'], 'guitar')                     # il titolo segue l'etichetta
        box = bridge.save_place(lib, name='Box 3', number=3)
        bridge.put(lib, items=[parts[1]['uuid']], place=box, number=7, category='document')   # una parte per il suo uuid, come ogni oggetto
        w = bridge.where_kept(lib, parts[1]['region_id'])
        self.assertEqual((w['place'], w['number'], w['category'], w['own_place']), (box, 7, 'document', True))
        self.assertEqual(w['part'], parts[1]['uuid'])
        self.assertEqual(bridge.places(lib)[0]['things'], 1)
        # la lista degli oggetti non mostra le parti come fonti; il dettaglio della fonte le da' con il loro uuid
        self.assertEqual([i['kind'] for i in bridge.item_list(lib)], ['scan'])
        d = bridge.item_detail(lib, src['uuid'])
        self.assertEqual([g['part']['uuid'] for g in d['regions']], [p['uuid'] for p in parts])
        self.assertEqual(bridge.info(lib)['parts'], 2)
        self.assertEqual([p for p in bridge.check(lib) if 'part' in p['kind'] and 'item' in p['kind']], [])

    def test_part_item_follows_its_part(self):
        # tolta la parte nello studio, il suo item e' nel cestino; tornata, torna; rinominata, il titolo segue
        from studio import core
        from studio.library import bridge
        lib = self.lib
        st = core.load_state(self.rel)
        gone = st['sheets'].pop(1)
        core.save_state(st)
        self.assertEqual(lib.db.execute("SELECT COUNT(*) FROM item WHERE kind = 'part' AND trashed_at IS NULL").fetchone()[0], 1)
        self.assertEqual(lib.db.execute("SELECT COUNT(*) FROM item WHERE kind = 'part'").fetchone()[0], 2)
        st = core.load_state(self.rel)
        st['sheets'].append(gone); st['sheets'][0]['label'] = 'violin'
        core.save_state(st)
        rows = lib.db.execute("SELECT p.title, p.trashed_at FROM item p JOIN region g ON g.id = p.region_id WHERE p.kind = 'part' ORDER BY g.position").fetchall()
        self.assertEqual([(r['title'], r['trashed_at']) for r in rows], [('violin', None), (None, None)])
        self.assertEqual([p for p in bridge.check(lib) if 'part' in p['kind'] and 'item' in p['kind']], [])

    def test_records_parts_texts_and_source(self):
        from studio.library import records as archive, bridge
        lib = self.lib
        recs = archive.build(lib, texts='both')
        kinds = [r['kind'] for r in recs]
        self.assertEqual(kinds, ['source', 'part', 'text', 'part'])         # fonte, parte con testo + il suo record di testo, parte senza testo
        src, p1, t1, p2 = recs
        self.assertEqual((src['category'], src['files'], src['source']), ('scan', [], 'scanstudio'))
        self.assertEqual(p1['within'], [src['source_id']])
        self.assertEqual(p1['inscriptions'], 'hello sketchbook')
        self.assertEqual(p1['title'], 'guitar')
        self.assertEqual(t1['within'], [p1['source_id']])
        self.assertEqual((t1['category'], t1['inscriptions']), ('document', 'hello sketchbook'))
        self.assertEqual(len(p1['files']), 1)
        self.assertTrue(os.path.exists(p1['files'][0]['path']))
        self.assertRegex(p1['dimensions'], r'^\d+\.\d × \d+\.\d cm$')
        self.assertEqual(p1['category'], 'drawing')
        # il testo solo come record: la parte non lo porta
        only = archive.build(lib, texts='records')
        self.assertIsNone(next(r for r in only if r['kind'] == 'part')['inscriptions'])
        # la categoria della fonte vale per le parti senza una loro
        bridge.put(lib, items=[lib.db.execute("SELECT uuid FROM item WHERE kind = 'scan'").fetchone()[0]], category='document')
        self.assertEqual({r['category'] for r in archive.build(lib, texts='inline') if r['kind'] == 'part'}, {'document'})

    def test_package_and_push_without_duplicates(self):
        from studio.library import records as archive
        lib = self.lib
        recs = archive.build(lib, texts='inline')
        out = archive.package(lib, os.path.join(self.root, 'pkg'), recs, log=lambda m: None)
        man = json.load(open(os.path.join(out['dir'], 'records.json')))
        self.assertEqual(man['source'], 'scanstudio')
        self.assertEqual(len(man['records']), 3)
        f = next(r for r in man['records'] if r['kind'] == 'part')['files'][0]
        self.assertTrue(os.path.exists(os.path.join(out['dir'], f['file'])))
        api = FakeDirectus()
        done = archive.push(lib, recs, url='https://archive.test', client=api, log=lambda m: None)
        self.assertEqual((done['created'], done['files']), (3, 2))
        parts = [r for r in api.records.values() if r.get('title') == 'guitar']
        self.assertEqual(parts[0]['status'], 'draft')
        self.assertEqual(parts[0]['within'], [{'wholes_id': next(r['id'] for r in api.records.values() if r['category'] == 'scan')}])
        self.assertEqual(lib.db.execute("SELECT COUNT(*) FROM archive_link WHERE entity = 'item'").fetchone()[0], 3)
        # di nuovo: niente di nuovo, niente file ricaricati
        again = archive.push(lib, archive.build(lib, texts='inline'), url='https://archive.test', client=api, log=lambda m: None)
        self.assertEqual((again['created'], again['updated'], again['same'], again['files']), (0, 0, 3, 0))
        # il testo corretto nello studio: solo quel campo cambia la'
        rid = lib.db.execute("SELECT reading_id FROM current_text WHERE plain = 'hello sketchbook'").fetchone()[0]
        lib.correct(rid, 'hello notebook')
        third = archive.push(lib, archive.build(lib, texts='inline'), url='https://archive.test', client=api, log=lambda m: None)
        self.assertEqual((third['updated'], third['files']), (1, 0))
        self.assertEqual(parts[0]['inscriptions'], 'hello notebook')
        self.assertTrue(lib.db.execute("SELECT 1 FROM event WHERE type = 'archive'").fetchone())


if __name__ == '__main__':
    unittest.main()
