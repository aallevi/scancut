# scancut · Scan Studio

Automatic cutting of scanned drawings. Scans land in `<root>/inbox` (default `~/Scans`);
a LaunchAgent runs `scancut.py`, which moves each scan to `originals/` and writes one
transparent PNG per sheet to `cut/`. Scan Studio (`studio.py`, `studio/`) is the window
to check and fix the cuts, drive the scanner and run headless jobs (see STUDIO.md).

## Layout

```
<root>/                  default ~/Scans; the code can live anywhere
  inbox/                 scans arrive here; the agent empties it
  originals/<batch>/     every scan, untouched (renamed only on collision)
  cut/<batch>/           cutouts: <stem>.png, or <stem> a.png, b.png ... per sheet
  failed/                symlinks to originals that need a look ("To check")
  .scancut/              run data: done.tsv, log.txt, errors.txt, lock, studio-data/
<repo>/
  scancut.py             the whole pipeline (comments in Italian)
  vision_mask.swift      Apple Vision helper; build: swiftc -O vision_mask.swift -o vision_mask
  studio.py, studio/     Scan Studio: window + API + headless jobs
  studio/mac/            native app (build.sh writes repo, Python and root into Info.plist)
  scripts/               user engines for the studio: segment(rgb, ppm, params) -> masks
  agent/scancut.plist.in LaunchAgent template, filled in by install.sh --agent
  install.sh, requirements.txt, VERSION
```

`done.tsv` is the ledger of cut originals: path inside originals/, size, mtime, result.

Batch = file name minus the final number (after a space, `_`, `-`, or glued to
letters; never after a dot, so dates stay whole). Image Capture restarts its
numbering each time it opens, so a taken name gets the next free number.

## Rules that must not break

- **Never lose a scan.** A file leaves the inbox only after it is safely in
  `originals/` (hard link, no overwrite, then unlink). Byte-identical repeats are
  dropped. Non-images, odd names, corrupt files all still land in `originals/`.
- **Never overwrite** an original or a cutout. Identical cutouts are not rewritten.
- One run at a time (`<root>/.scancut/lock`). Do not run the script by hand while the
  agent may be running; use `launchctl kickstart` instead.
- **One source for every characteristic (library).** Each characteristic of a part (outline, edits,
  holes, rotation, label, order, colour, included in the cut, text and secondary areas) is stored once;
  the studio sheet, the cut file (pixels, name, metadata), the text pane, the side-by-side view and the
  library views are representations of it. A change made in any of them changes the source and all
  the others follow (re-cut, rename, metadata), with the previous files kept as history. No exceptions:
  a new characteristic or view is wired to the source before it is shown. Files of parts are "cuts".
- **Only real pixels.** Cutouts change transparency only: no filling, no colour
  fixing, no synthetic edges. Tools that change pixels make separate copies, marked
  as "fake pixels".

## Pipeline (per scan)

1. Background = mode of low-chroma border pixels (white lid, or grey card behind
   white paper); weighted Lab distance (tint x2).
2. Paper mask, components; touching sheets split along straight lines (±8°) with a
   gap, a colour jump, or a narrow neck.
3. Edge = contiguous magic wand from outside on a 3x3-blurred copy (tolerance ≈
   Photoshop 13-15), then shadow pass (darker than background, same tint, last
   1.5 mm, reached from outside), then largest component. Fibres and tears stay.
   Paper close to the lid colour: wand tolerance halfway between lid and paper; for
   grey/ivory paper (lid tint, darker) the shadow pass removes only what is lighter
   than the paper, darker than it, or within 3 px of the shadow line.
4. Punch holes transparent (fitted ellipses). Deskew via minAreaRect: up to 10°,
   up to 45° if clearly rectangular.
5. Paper close to background colour: Apple Vision too (512x512 internal mask,
   smooth edges); the better-scoring result wins.

## Working on it

- Discuss big pipeline changes before making them.
- Code comments in Italian; docs in English; commit messages in Italian.
- Run `python3 -m unittest discover -s tests` before committing (also in CI).
- Test on **copies** with a scratch root: `python3 -I scancut.py <root>` takes the
  root as its argument. Compare old vs new on real scans and look at zoomed edges.
  Synthetic tests (rotating a scan by hand) mislead: they rotate the lid too.
  `tools/make_test_scans.py` and `tools/make_demo_scans.py` make made-up scans.
- Python: the repo's `.venv` (install.sh) or any Python with requirements.txt.
  OpenCV stays on 4.x: 5.x rounds the deskew differently.
- Redo a scan: delete its line in `done.tsv` (move old cutouts aside first, or
  identical ones are skipped and changed ones get ` (2)`).
- The agent starts only when the inbox changes (WatchPaths; no timer, no run at
  login) and runs as a background process (efficiency cores, low-priority I/O).
  Leftover uncut originals wait for the next scan, or a kickstart.
  `<root>/.scancut/autocut-off` makes it only file scans, without cutting.
- Reload after editing the LaunchAgent:
  `launchctl unload ~/Library/LaunchAgents/<label>.plist && launchctl load ...`
  (the script itself is re-read on every run, no reload needed).
- Known limits: overlapping sheets stay one piece; same-colour sheets touching with
  no gap may stay one; white on white relies on Vision (grey card is better);
  coloured paper on the white lid keeps a ~1 px light edge.
- Scan Studio shares the pipeline: `cut_scan` returns each sheet's mask as a 6th
  tuple item `(mask, holes, exact)`; untouched studio exports must stay byte-identical
  to the agent's. On the `library` branch every part, cut and text lives only in the library
  (`<root>/Library.DocuLib`, code in `studio/library/`): `core.load_state`/`save_state` read and
  write its rows. Never add another store; `studio-data/` holds only caches and settings. Library › Check
  (and the end of tools/health.js) must report nothing. After "Move files in…" (`bridge.switch_storage`)
  originals/, cut/, failed/ live inside the package as lossless JPEG XL (`sc.pack`: checked pixel for pixel);
  `sc.PACKED` says so, `core.abspath`/`core.relpath` map the same relative names there. Temporary files
  are hidden (dot names) so nothing registers them.
