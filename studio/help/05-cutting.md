# Cutting

**Cut** (⌘S, or the scissors) writes one file per included part: `name.png`, or `name a.png`,
`name b.png`… when there are several.

- After that, cuts **follow their part**: change the outline, rotation, name, order or inclusion and
  the cut is made again by itself. The previous file goes into the history, never overwritten.
- Identical cuts are never rewritten.
- Format (Settings › Cuts): PNG, or JPEG XL lossless (smaller, same pixels; every file is checked).
- 16-bit scans give 16-bit cuts.
- The part's text goes into the cut file (description in XMP, IPTC and EXIF) with links back to
  the source and the text in the library.

## Cutting a cut again

Open a cut and cut it: the new pieces go into a folder named after it, and the cut itself moves in
there unchanged. Transparency already there stays.

## Freeze a copy

The Cut dialog can also write the cuts as they are now into a subfolder: that copy does not follow
its parts any more.
