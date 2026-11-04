# Scan Studio

A Vista-style window to see, compare and fix the cutouts, plus headless jobs.
Same engine as the agent (`scancut.py`), same rules: originals are never touched,
cutouts are never overwritten, only real pixels.

## Start

```
/opt/miniconda3/bin/python3 -I studio.py              # window (root ~/Scans)
/opt/miniconda3/bin/python3 -I studio.py serve        # server only, http://127.0.0.1:8765
... studio.py --root <copy>                           # work on a scratch copy
```

The window uses pywebview when installed (`pip install pywebview`: frameless, the
Vista caption buttons work); otherwise Chrome/Edge in app mode, otherwise the browser.

## Headless

```
studio.py engines
studio.py detect originals/sketchbook --engine classic [--export]
studio.py detect "originals/notes/notes 4.png" --engine sam3 --prompt "drawing"
studio.py export "originals/notes/notes 4.png"          # saves the edited state
```

## Engines

- `auto`: exactly what the agent does. `classic`: same without the Vision fallback.
- `vision`: Apple Vision (`vision_mask`).
- `sam3`: Meta SAM 3 via transformers, in its own process (`studio/sam3_worker.py`),
  on the Apple GPU. Needs the weights converted once into `~/sam3-hf`:
  ```
  curl -L -o /tmp/convert_sam3_to_hf.py https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/sam3/convert_sam3_to_hf.py
  cd ~ && /opt/miniconda3/bin/python3 -I /tmp/convert_sam3_to_hf.py --checkpoint_path ~/sam3.pt --output_path ~/sam3-hf
  ```
  (~3.3 GB; after that `~/sam3.pt` is no longer needed by the studio.)
  "Refine edge with wand" keeps SAM's region but takes the real edge from the
  classic wand within 2 mm.
- `script:<name>`: any `scripts/<name>.py` with `segment(rgb, ppm, params)` returning
  masks. Reloaded on every run.

## How edits work

Each engine result is cached as exact masks (`studio-data/cache`). The editor shows a
simplified outline (`poly0`). Moving points changes only the area between the old and
the new outline; lasso/brush add or cut away; everything else keeps the engine's
pixels (fibres, tears). New sheets can be drawn by polygon, lasso, or a box detected
with any engine. Export runs `scancut.cutout`, so untouched sheets give the same
bytes as the agent.

Export: a changed cutout with the same name is moved to
`studio-data/replaced/<time>/` (never overwritten); identical ones are left; the
scan is added to `done.tsv` as `studio` so the agent doesn't redo it. It takes the
agent's lock. Optional: also import into Eagle (local API, Settings).

## Data (`<root>/.scancut/studio-data/`, not in git)

`state/` edit state per scan (JSON), `cache/` engine masks, `previews/`,
`replaced/`, `settings.json`.

## API (127.0.0.1 only; POSTs need header `X-Studio: 1`)

GET  `tree`, `list?dir=`, `info?rel=`, `state?rel=`, `engines`, `settings`, `jobs`,
`job?id=`, `thumb|preview?rel=`, `tile|masktile?rel=&x=&y=&w=&h=&out=`,
`cutout?rel=&id=`, `scanners`
POST `detect {rel, engine, params, box?, replace?}`, `state {state}` (version-checked),
`compare {rel, engines}`, `export {rel}`, `settings {...}`,
`jobs {kind: batch|export|claude, rels, engine, params, export | message, rel}`,
`cancel {id}`, `open {what: finder|canon|imagecapture|eagle|kick|scripts, rel?}`

`rel` is a path inside the root, e.g. `originals/sketchbook/sketchbook 3.png`.

## Shortcuts (editor)

V select · H pan (or hold Space) · A edit points (double-click edge adds, ⌥-click
removes) · P polygon (Enter closes) · L lasso add · K lasso cut · B brush · E eraser ·
R box detect · [ ] brush size · C compare · X cut view · Tab next sheet ·
Delete hide/remove sheet · ⌘Z/⇧⌘Z · ⌘S export · ⌘0 fit · ⌘1 actual pixels · ←/→ scans.
Pinch zooms, two-finger scroll pans, a mouse wheel zooms.

## Milestone 2 (next)

Drive the scanner directly (ImageCaptureCore helper, like `vision_mask.swift`):
overview scan, scan area, DPI/colour, several scanners, scan into a batch.
The LiDE 400 is registered as `Canon_LiDE_400` (eSCL over USB).
