# Scan Studio

A Vista-style window to see, compare and fix the cutouts, plus headless jobs.
Same engine as the agent (`scancut.py`), same rules: originals are never touched,
cutouts are never overwritten, only real pixels.

## Start

```
python3 -I studio.py              # window (root ~/Scans)
python3 -I studio.py serve        # server only, http://127.0.0.1:8765
... studio.py --root <copy>       # work on a scratch copy
```

(`python3` = the project's `.venv/bin/python3` after `./install.sh`, or any Python with
`requirements.txt`.)

From the Dock: `~/Applications/Scan Studio.app`, a native Swift app (`studio/mac/ScanStudio.swift`,
built and ad-hoc signed by `studio/mac/build.sh`, which writes the code folder, the Python and
the scans root into its Info.plist; rebuild after changing the Swift file, the icon or those
paths, pages and Python are read live). One WebKit window with no macOS frame: the Vista
frame's buttons minimise to the Dock, zoom and close for real. It starts `studio.py serve`
as a child (or uses one already running) and stops it on quit, after saving pending edits.
Dock click brings the window back; ⌘Q quits; View > Reload; Web Inspector via right-click.

From a terminal, without the app: the window uses pywebview when installed (`pip install pywebview`: frameless, the
Vista caption buttons work); otherwise Chrome/Edge in app mode, otherwise the browser.

## Headless

```
studio.py engines
studio.py detect originals/sketchbook --engine classic [--export]
studio.py detect "originals/sketchbook/sketchbook 4.png" --engine sam3 --prompt "drawing"
studio.py export "originals/sketchbook/sketchbook 4.png"   # saves the edited state
```

## Engines

- `auto`: exactly what the agent does. `classic`: same without the Vision fallback.
- `vision`: Apple Vision (`vision_mask`).
- `sam3`: Meta SAM 3, `sam3.pt` read straight by Ultralytics (the same way
  DigitalSreeni Image Annotator does it). Found in Settings' `sam3_weights`, else
  `studio-data/models/`, `~`, `~/Downloads` or the Hugging Face cache; Add-ons installs both.
  Runs in its own process (`studio/sam3_worker.py`)
  on the Apple GPU. First run loads ~3.4 GB (~10 s). Text prompt now; the worker also
  takes clicks (+/-) and boxes (`mode: 'prompt'`) for the coming SAM tool.
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

## Export, rotation, history, automatic cutting

- Settings > Export: PNG or JPEG XL lossless (`cjxl -d 0`, alpha kept; each file is decoded
  back and compared pixel by pixel, else PNG is written). A different cutout whose name is
  taken gets " (2)" and the old one stays (or, if chosen, the old one goes to replaced/).
  "To extra/" exports the same cutouts into a subfolder.
- ⟲/⟳ 90°: lossless rotation of the cutout at export (pixels moved, never resampled).
- Detect never throws away sheets made by hand, and keeps the previous sheets in
  "Earlier" (last 15) to restore. Detection runs only when you press Detect.
- "Format from a corner": no detection, an exact A3–A7, Letter or photo rectangle from the
  chosen corner of the scan (default bottom-left). Works in Batch.
- Settings > Scan agent > Cut automatically: off writes `.scancut/autocut-off`; the agent then
  only files new scans into originals/ (never loses one) and does not cut.
- Two-finger scrolling always pans; zoom by pinching or ⌘ + scroll.

## Recutting a cutout

Open a cutout (in `cut/` or a per-batch folder) and cut it again: the new pieces go in
a folder named after it, next to it, and the cutout itself moves in there untouched:
`cut/sketchbook/sketchbook 3 a.png` -> `cut/sketchbook/sketchbook 3 a/sketchbook 3 a.png` + `sketchbook 3 a a.png` ...
Its transparency stays (the new alpha is never more opaque than the old). For the
engines, transparent areas and a 10 mm margin are filled with grey card (light paper)
or white lid (dark paper); those fill pixels are never saved.

## Data (`<root>/.scancut/studio-data/`, not in git)

`state/` edit state per scan (JSON), `cache/` engine masks, `previews/`,
`replaced/`, `models/` (SAM 3 downloaded from Add-ons), `settings.json`, `server.log`.

## Add-ons

`GET addons` lists the optional parts with their state; `jobs {kind: install, what}` installs one:
`helpers` (swiftc), `sane` / `exiftool` / `jxl` (Homebrew), `ultralytics` (pip into the studio's
Python), `sam3` (Hugging Face download; `token` goes to the child's environment, never into job
listings). Only these fixed commands run.

## API (127.0.0.1 only; POSTs need header `X-Studio: 1`)

GET  `tree`, `list?dir=`, `info?rel=`, `state?rel=`, `engines`, `settings`, `jobs`,
`job?id=`, `thumb|preview?rel=`, `tile|masktile?rel=&x=&y=&w=&h=&out=`,
`cutout?rel=&id=`, `scanners`
POST `detect {rel, engine, params, box?, replace?}`, `state {state}` (version-checked),
`compare {rel, engines}`, `export {rel}`, `settings {...}`,
`jobs {kind: batch|export|claude, rels, engine, params, export | message, rel}`,
`cancel {id}`, `open {what: finder|canon|imagecapture|eagle|kick|scripts, rel?}`

`rel` is a path inside the root, e.g. `originals/sketchbook/sketchbook 3.png`.

## Tools

Inspection (read-only, from the full-resolution scan): densitometer (RGB, L*a*b*,
distance from the lid colour the cut uses and its tolerance; single pixel, 3x3 or 5x5),
loupe (G; 4/8/16:1, nearest-neighbour, real pixels), histogram (whole scan or the
selected sheet, lid marker, linear/log), info bar (selected sheet mm, px, MB).
Automatic/Classic take "Tolerance ×": 1 is the agent's own choice (identical cutouts).
SAM 3 menu (top bar): prompt and its options, quick prompts, find every object (replace or
add), click and box tools, unload. SAM 3 tool (S): click the object the prompt names, ⌥-click excludes, drag a box to
search inside it, Enter starts a new object. SAM 3's interactive (click/box) mode in
Ultralytics spreads over the whole bed on these scans, so clicks pick among the text
prompt's results instead. Every SAM result gets a second pass on a crop around it and
its final edge from the real pixels (wand against the local background, within 2 mm).

Magic wand: like Photoshop's, on the 3x3-blurred scan, per-channel tolerance (the
automatic cut uses ~13-15), contiguous or not. Stored as seed + tolerance, so export
recomputes it at full resolution. Clicking paper with no sheet there makes a new sheet.
View menu: background (light blue, white, grey, dark, checker). Pane edges drag;
double-click resets.

## Shortcuts (editor)

V select · H pan (or hold Space) · A edit points (double-click edge adds, ⌥-click
removes) · P polygon (Enter closes) · M rectangle · L lasso · W Magic Wand (options in the bar above the scan) · B brush ·
K / E lasso / brush in Cut mode · X swap Add/Cut (⌥ while clicking does the other) ·
R box detect · [ ] brush size · C compare · O cut view · Tab next sheet ·
⇧/⌘-click or drag on empty space selects several sheets · ⌃-click (or ⌥-click, right-click) a sheet: only that one is exported, again: all back on · Text (OCR) on the selected sheets reads their text into an editable box, written into the cutout's description at export · ⌘A all · Delete deletes the selected (⌘Z undoes) · ⌘Z/⇧⌘Z · ⌘S export · ⌘0 fit · ⌘1 actual pixels · ←/→ scans.
Pinch zooms, two-finger scroll pans, a mouse wheel zooms.
Address bar: every folder is clickable, ▸ lists its subfolders; back/forward with the round
buttons, ⌘[ ⌘], ⌥←/→ or the mouse side buttons.

## Scanner

Through SANE (`scanimage`, `studio/scanner.py`): the scanner's real resolutions and modes,
preview of the bed, scan areas (each with its own settings), 48-bit colour, sessions (Space =
next page, or timed). Scans go to the inbox like any other. Tested with a Canon LiDE 400.

## Testing (for Claude)

- Scratch root: `python3 -I studio.py serve --root <copy> --port 8799`, never the live ~/Scans.
- Screenshots: `swiftc -O tools/snap.swift -o tools/snap`, then
  `tools/snap "http://127.0.0.1:8799/#originals%2F<file>" out.png 1400 880 <wait-s> [script.js]`;
  the JS runs after load (studio globals like `S`, `openScan`, `detect` are reachable), page
  errors are printed. Read the PNG to check.
- Made-up drawings for screenshots: `tools/make_demo_scans.py` (in an empty inbox).
- Pipeline changes: run the HEAD copy and the new `scancut.py` on the same inbox in two
  scratch roots and `cmp` every cutout (`tools/make_test_scans.py` makes made-up scans for this).

