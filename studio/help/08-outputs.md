# Outputs

## Transcriptions for nvim

Outputs › **Transcriptions for nvim** writes **one file per cut** (named like the cut, date first: `2026-11-04
vendrdro 4 a`), plus one for a whole page read at once, into a folder you choose. Areas inside a cut, or
made on the cut itself, are headings in its file.

- **Markdown** is shaped like a wiki note: front matter with `title`, `date` and `id` (the part's UUID, which
  never changes), `source` and `part` addresses (no file paths: the library is the only store). Prints with pandoc like any note.
- **LaTeX** is made by **pandoc** from the text as read: headings, lists, tables, emphasis and formulas are kept,
  and the lines of the page stay lines. It is a small plain document per cut with only standard packages: it
  compiles on its own with lualatex or pdflatex, and pandoc reads it into your own templates (EasyPrint).
  `journal.tex` gathers every cut by date (docmute).
- **Pictures**: when the reader marks pictures on the page (LightOnOCR-2, Unlimited-OCR), each one is cut from the
  cut's real pixels, made smaller only if needed for print (at most 2400 px on the long side, about 20 cm at
  300 dpi), saved as PNG with its transparency in `figures/`, and placed where it is in the text (LaTeX and
  Markdown alike). No other pictures and no file paths: just `scanstudio://` addresses.
  The reader sees the cut as it is turned, so a picture's box is in the turned frame: the text view beside
  the scan turns it back before showing the picture where it is on the sheet.
- **Formulas**: readers write them LaTeX-style, `\( x \)` and `\[ x \]`; the files carry them between dollars
  (`$x$`, `$$x$$`), the only form pandoc renders, so a print shows the formula and not `( \frac{d}{dx} )`.
  A formula the reader imagined (a doodle read as maths) is a text correction, made in the studio as any other.

The files are read-only: correct the text in Scan Studio and they are rewritten a few seconds later.
Your own files in the folder are never touched.

In nvim, `nvim/scanstudio.lua` (in the repository) reads both formats: `:Scans` (open a cut's text),
`:ScansGrep` (search), `:ScanTake` (copy the text under the cursor) and `:ScanInsert` (put a cut's text into
the note you are writing, followed by a comment saying where it comes from):

    require('scanstudio').setup({ dir = '~/wiki/scans' })

## A file with several pages

In Library › Sources (or a series), select several sources (⌘-click, ⇧-click, ⌘A) and press
**Multipage file…**: one PDF or one TIFF with one page per source, in the order shown, or one page
per cut. Lossless (Flate, no JPEG), real pixels at 8 bits per channel, each page the size of its
scan; transparent cuts stay transparent. The file goes into a folder you choose and opens in the
Finder when done; an existing file is never overwritten. It is a copy for reading or sending: the
library keeps the sources and cuts. The same selection also offers **Pass whole**, **Detect + cut**,
**Read text** and **Move to Trash**.

## Cuts in folders, and what travels with them

Outputs › **Export cuts in folders** copies the cuts into a folder of your choice, like Eagle's export:
by place (Chest › Box 24 › Folder 5, each file starting with its number there), by series, or all
together; all cuts, those of the place or series shown, or the selected ones.

**For** Eagle, the archive site, or just a folder, you choose **what travels** with each file: the
transcription, title and part label, date, series, where it is kept (private), size, Scan Studio IDs
and the source scan, the scan's own metadata, and a `.json` beside each file (with `source_system:
scanstudio` and `source_id`, so an importer never makes duplicates). Only metadata changes: the pixels
are the cut's, byte for byte. The choice is remembered per destination. The cut in the library keeps
everything; a copy already there and identical is left alone.

## Archive site (Directus)

Outputs › **Archive site** connects your Directus archive with a **read-only** token: Scan Studio
can see what is there (how many records came from Scan Studio, the lists of events and places) and
never writes. The token is kept in the Mac's Keychain, never in a file. If the token could also
write, the dialog says so. To make one: Access Policies › a policy with Read only on the
collections, then a user with that policy and a generated token.

## Eagle

Cuts can also be sent to Eagle when cutting (Settings).
