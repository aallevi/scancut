# The library

The library holds everything about sources, parts, cuts and texts. Its views are on the left:

- **Sources**: every scan, with its cuts. Sort and filter by resolution.
- **Cuts**: every cut file. Click opens it; ⌘-click in a new tab.
- **Texts**: every text. Click opens its source with the part selected and the Text pane open.
  "Hide no text found" is on by default.
- **Series** (and **Places**): one series or place, like a folder. The Sources | Cuts | Texts switch in the
  bar changes what it shows of that series (its texts too); the title says both. Sources, Cuts and Texts on the left show
  the whole library again, as does the × on the yellow chip.

The panel on the right shows where a file belongs: its source, its parts, their cuts and texts.

## Many cuts at once

Select cuts in Library › Cuts (⌘-click, ⇧-click, ⌘A). The Batch menu and the pane offer: Read text…, turn
left or right (losslessly, with their parts), Join as one object…, a multipage file of just these cuts,
Export these cuts…, Show their sources, Move to Trash.

## Objects: parts that are the same piece of paper

Front and back of a sheet, the two pages of a double page, a drawing scanned in two goes: different parts,
on the same scan or on different ones, that are one thing. Join them as an **object**: the library keeps
the link, nothing is copied or merged, each part keeps its own cut and text. From then on every view shows
them together: one tile in Cuts (the sides in order, a ⧉ badge), a line under each part in the source's
pane and in the editor's sheet list, with the other sides a click away. The object has a name and one
place; a side without a place of its own takes the object's.

- **Join**: select two or more cuts in Library › Cuts, or two or more sources (their parts are listed),
  or two or more sheets in the editor, then **Join as one object…**. Give each a side (front, back,
  left, right, or your own word) and a name.
- **Separate**: from the object's pane (a side, or all). An object left with one part dissolves; the parts
  stay exactly as they were.
- Library › Check reports an object with fewer than two parts.

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

## Import folders

File › Import folders… chooses folders the studio watches while it is open, like Eagle's Auto-Import:
a camera card, Downloads, another program's export folder. A new image there, once it stops changing,
comes into the library as a scan: copied and checked, then filed with the same rules as the inbox (never
overwritten; lossless JPEG XL when the files are inside the library), in Jobs. **Move in** takes it out
of the folder once it is safe; **Copy in** leaves it there and never takes it twice. An image already in
the library, byte for byte, under any name, is recognised and not added again. The scans folder's own
inbox is always watched, also with the studio closed; scans made from the studio go straight in.

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
