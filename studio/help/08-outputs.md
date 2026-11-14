# Outputs

## Transcriptions for nvim

Outputs › **Transcriptions for nvim** writes **one file per cut** (named like the cut, date first: `2026-11-04
vendrdro 4 a`), plus one for a whole page read at once, into a folder you choose. Areas inside a cut, or
made on the cut itself, are headings in its file.

- **Markdown** is shaped like a wiki note: front matter with `title`, `date` and `id` (the part's UUID, which
  never changes), `source`, `part` and `cut` addresses. Prints with pandoc like any note.
- **LaTeX** is a small plain document per cut with only standard commands (`\section*`, `\subsection*`,
  `itemize`, the cut's picture when it is PNG/JPEG): it compiles on its own with lualatex or pdflatex, and
  pandoc reads it into your own templates (EasyPrint). `journal.tex` gathers every cut by date (docmute).

The files are read-only: correct the text in Scan Studio and they are rewritten a few seconds later.
Your own files in the folder are never touched.

In nvim, `nvim/scanstudio.lua` (in the repository) reads both formats: `:Scans` (open a cut's text),
`:ScansGrep` (search), `:ScanTake` (copy the text under the cursor) and `:ScanInsert` (put a cut's text into
the note you are writing, followed by a comment saying where it comes from):

    require('scanstudio').setup({ dir = '~/wiki/scans' })

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
