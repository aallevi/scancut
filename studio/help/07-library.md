# The library

The library holds everything about sources, parts, cuts and texts. Its views are on the left:

- **Sources**: every scan, with its cuts. Sort and filter by resolution.
- **Cuts**: every cut file. Click opens it; ⌘-click in a new tab.
- **Texts**: every text. Click opens its source with the part selected and the Text pane open.
  "Hide no text found" is on by default.
- **Series**: the sources of one series.

The panel on the right shows where a file belongs: its source, its parts, their cuts and texts.

## Files inside the library

At first sources and cuts are folders next to the inbox (`originals/`, `cut/`). **Move files in…** (top of
the library) puts them inside the library itself, `Library.DocuLib` in the scans folder, which the
Finder shows as one file. First it shows what will happen, then it moves them only when you confirm:

- PNG and TIFF become **lossless JPEG XL**: the same pixels in about half the space. Each one is
  checked pixel for pixel before the old file is let go; colour profile, resolution and metadata go
  with it. JPEGs stay as they are.
- Only the **inbox** stays as a folder. New scans go straight into the library, already in JPEG XL.
- Folders come back when you **export** (Outputs › Export cuts: by place, series or flat).
- The files as they were are kept in `.scancut/studio-data/replaced/switch-<date>/` until you remove them.
- Affinity and Preview open `.jxl` directly. Eagle does not, so cuts sent to Eagle go as PNG.

## Trash

**Move to Trash** (on a source, or on a cut) takes it out of every view: a source goes with its cuts; a
cut's part stops being cut until it comes back. **Library › Trash** lists everything there: **Put back**
returns it exactly where it was. The Trash empties by itself after the days set in Settings (every
three months to start); only then is anything deleted for good. **Empty Trash** and **Delete now** do
it at once.

## Check

**Library › Check** verifies that every file is where the library says and unchanged, every cut is
present, linked and carries its part's current text. With ⌥ it also re-cuts every part in memory and
compares pixel by pixel.

## Edit in another app

A file can be opened in Affinity, Preview or another editor from the library; what you save comes
back as a linked version, never over the original.
