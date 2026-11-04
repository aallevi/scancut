# Scans

Automatic cutting of scanned drawings. Antonio scans with Image Capture into
`~/Scans/inbox`; a LaunchAgent runs `scancut.py`, which moves each scan to
`originals/` and writes one transparent PNG per sheet to `cut/`. Antonio then
imports the cutouts into Eagle and empties the folders by hand.

## Layout

```
~/Scans/
  inbox/                 scans arrive here; the script empties it
  originals/<batch>/     every scan, untouched (renamed only on collision)
  cut/<batch>/           cutouts: <stem>.png, or <stem> a.png, b.png ... per sheet
  failed/                symlinks to originals that need a look
  .scancut/              this repo
    scancut.py           the whole pipeline (comments in Italian)
    vision_mask.swift    Apple Vision helper; build: swiftc -O vision_mask.swift -o vision_mask
    com.antonioallevi.scancut.plist   copy of ~/Library/LaunchAgents/ (the live one)
    studio.py, studio/   Scan Studio: Vista-style window + API + headless jobs (see STUDIO.md)
    scripts/             user engines for the studio: segment(rgb, ppm, params) -> masks
    done.tsv             ledger of cut originals: path inside originals/, size, mtime, result
    log.txt, errors.txt  run log, launchd stderr
```

Batch = file name minus the final number (after a space, `_`, `-`, or glued to
letters; never after a dot, so dates stay whole). Image Capture restarts its
numbering each time it opens, so a taken name gets the next free number.

## Rules that must not break

- **Never lose a scan.** A file leaves the inbox only after it is safely in
  `originals/` (hard link, no overwrite, then unlink). Byte-identical repeats are
  dropped. Non-images, odd names, corrupt files all still land in `originals/`.
- **Never overwrite** an original or a cutout. Identical cutouts are not rewritten.
- One run at a time (`.scancut/lock`). Do not run the script by hand while the
  agent may be running; use `launchctl kickstart` instead.
- **Only real pixels.** Cutouts change transparency only: no filling, no colour
  fixing, no synthetic edges. Antonio was explicit: "no fake pixels", keep it simple.

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

- Discuss options with Antonio before big changes; Antonio chooses. Use they/them
  for Antonio unless told otherwise.
- Code comments in Italian; docs in English. Commit messages so far are Italian.
- Test on **copies** with a scratch root: `python3 -I scancut.py <root>` takes the
  root as its argument. Compare old vs new on real scans and look at zoomed edges.
  Synthetic tests (rotating a scan by hand) mislead: they rotate the lid too.
- Python: `/opt/miniconda3/bin/python3` (OpenCV, NumPy, Pillow).
- Redo a scan: delete its line in `done.tsv` (move old cutouts aside first, or
  identical ones are skipped and changed ones get ` (2)`).
- The agent starts only when the inbox changes (WatchPaths; no timer, no run at
  login) and runs as a background process (efficiency cores, low-priority I/O) to
  keep the Mac cool. Leftover uncut originals wait for the next scan, or a kickstart.
- Reload after editing the plist:
  `launchctl unload ~/Library/LaunchAgents/com.antonioallevi.scancut.plist && launchctl load ...`
  (the script itself is re-read on every run, no reload needed).
- Known limits: overlapping sheets stay one piece; same-colour sheets touching with
  no gap may stay one; white on white relies on Vision (grey card is better);
  coloured paper on the white lid keeps a ~1 px light edge.
- Scan Studio shares the pipeline: `cut_scan` returns each sheet's mask as a 6th
  tuple item `(mask, holes, exact)`; untouched studio exports must stay byte-identical
  to the agent's. Studio data lives in `.scancut/studio-data/` (gitignored).
