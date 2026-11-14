#!/usr/bin/env python3
# quanto ci mettono le viste della libreria con molti oggetti: una libreria finta (N fonti, due parti l'una, un
# taglio e un testo per parte) in una cartella temporanea, poi i tempi di item_list, cutout_list, text_list, places.
#   python3 -I tools/bench_library.py [N]
import os, sys, time, json, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from studio import core                                  # noqa: E402
from studio.library import bridge                        # noqa: E402
from studio.library.db import new_uuid, now              # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
root = tempfile.mkdtemp(prefix='scancut-bench-')
for d in ('inbox', '.scancut', 'originals', 'cut'):
    os.makedirs(os.path.join(root, d))
core.set_root(root)
lib = bridge.library(create=True)
db = lib.db
t0 = time.time()
with db:
    sid = db.execute("INSERT INTO series (uuid, name, created_at) VALUES (?, 'bench', ?)", (new_uuid(), now())).lastrowid
    for i in range(N):
        a = db.execute("INSERT INTO asset (uuid, sha256, size, storage, path, original_name, width, height, dpi, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (new_uuid(), f'{i:064x}', 1000, 'referenced', os.path.join(root, 'originals', 'bench', f'scan {i}.png'), f'scan {i}.png', 2480, 3508, 300, now())).lastrowid
        it = db.execute("INSERT INTO item (uuid, kind, title, date, series_id, created_at, modified_at) VALUES (?,?,?,?,?,?,?)",
                        (new_uuid(), 'scan', f'scan {i}', '2026-01-01', sid, now(), now())).lastrowid
        db.execute("INSERT INTO item_asset (item_id, asset_id, role, position) VALUES (?,?,'view',0)", (it, a))
        for k in range(2):
            g = db.execute("INSERT INTO region (uuid, item_id, asset_id, kind, label, geometry, position, color, created_at, modified_at, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (new_uuid(), it, a, 'sheet', None, json.dumps({'poly': [[0, 0], [1000, 0], [1000, 1400], [0, 1400]]}), k, '#3399ff', now(), now(),
                            json.dumps({'studio_id': f's{k + 1}', 'studio_rel': f'originals/bench/scan {i}.png'}))).lastrowid
            p = lib.ensure_part(g) if hasattr(lib, "ensure_part") else None
            c = db.execute("INSERT INTO asset (uuid, sha256, size, storage, path, original_name, width, height, dpi, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (new_uuid(), f'{i:060x}{k:04x}', 500, 'referenced', os.path.join(root, 'cut', 'bench', f'scan {i} {"ab"[k]}.png'), f'scan {i} {"ab"[k]}.png', 1000, 1400, 300, now())).lastrowid
            db.execute("INSERT INTO item_asset (item_id, asset_id, role, position) VALUES (?,?,'cutout',?)", (it, c, 100 + k))
            db.execute("INSERT INTO cut (uuid, item_id, region_id, format, path, sha256, created_at) VALUES (?,?,?,?,?,?,?)",
                       (new_uuid(), it, g, 'png', os.path.join(root, 'cut', 'bench', f'scan {i} {"ab"[k]}.png'), f'{i:060x}{k:04x}', now()))
            r = db.execute("INSERT INTO reading (uuid, region_id, asset_id, engine, plain, created_at) VALUES (?,?,?,?,?,?)",
                           (new_uuid(), g, a, 'vision', f'text of scan {i} part {k}', now())).lastrowid
            db.execute("INSERT INTO text_link (reading_id, asset_id) VALUES (?,?)", (r, c))
print(f'{N} sources, {2 * N} parts built in {time.time() - t0:.1f} s')
box = bridge.save_place(lib, name='Box', number=1)
bridge.put(lib, items=[db.execute("SELECT uuid FROM item WHERE kind = 'scan' LIMIT 1").fetchone()[0]], place=box)


def bench(name, fn, reps=3):
    best = min(timeit(fn) for _ in range(reps))
    print(f'{name:36} {best * 1000:8.1f} ms')
    return best


def timeit(fn):
    t = time.time(); fn(); return time.time() - t


bench('item_list (500)', lambda: bridge.item_list(lib, limit=500))
bench('item_list (search)', lambda: bridge.item_list(lib, q='scan'))
bench('cutout_list (1000)', lambda: bridge.cutout_list(lib, limit=1000))
bench('text_list (500)', lambda: bridge.text_list(lib, limit=500))
bench('places', lambda: bridge.places(lib))
bench('item_detail', lambda: bridge.item_detail(lib, db.execute("SELECT uuid FROM item WHERE kind = 'scan' LIMIT 1").fetchone()[0]))
bench('series_list', lambda: bridge.series_list(lib))
shutil.rmtree(root, ignore_errors=True)
