# Libraries (design, branch `library`)

Scan Studio grows from "folders of scans" into an archive: **libraries** of items (scans, photos,
documents, objects), their selections, the text read from them, and everything exported from them.
Folders stay on disk; they become one way of looking among many. The rule stays: **only real
pixels**, and nothing is ever lost or overwritten.

## The rule: one source

Every characteristic of a part exists once; everything else is a view of it. The scan's sheet in the
studio, its **cut** (the file: pixels, name, embedded text), the Text pane, the side-by-side view and
the library's Objects / Cutouts / Texts all show the same values. Change one anywhere (rotate a cut,
correct its text, move the outline, rename, reorder, exclude) and every view follows: cuts are
re-cut or renamed automatically, text is rewritten into their metadata, and the previous files stay
in the history (`studio-data/replaced/`, `event` table). Scan, cut and text are three things with
links between them: a part points to its texts, a cut points to the texts of its part.

## A library

A library is a package (a folder macOS shows as one file), `Name.scanlib/`:

```
Name.scanlib/
  library.sqlite        the catalog (studio/library/schema.sql)
  store/ab/<sha256>.tif the managed files, named by their checksum (no duplicates, fixity built in)
  store/ab/<sha256>.tif.json   sidecar: what the catalog knows about that file
  snapshots/            copies of the catalog (last 10): at every open and before big changes
  cache/                previews and masks; safe to delete
```

- **Managed or referenced files.** Managed files are hard-linked or copied into `store/` and checked
  byte for byte. Referenced files stay where they are (e.g. `~/Scans/originals`), the catalog keeps
  their path and checksum. A hard link is not a second copy: backups are separate (see below).
- **Several libraries, several windows.** Like Tropy: File › Open Library in New Window. Each
  window runs its own server on its own library. Two libraries can be **merged**: everything has a
  UUID and files are named by checksum, so merging never duplicates or collides.
- **Not only scans.** `item.kind` is open: scan, photo, document, object. An item can have several
  files (front, back, details, pages).

## What the catalog holds

| Table | What |
|---|---|
| asset | each file: checksum, size, where, pixels, dpi, bits, colour profile, technical metadata |
| item | the thing archived: title, date (EDTF, so "2014-05?" works), batch, notes, trash |
| region | selections on a file: sheet, text area, figure, box; nested (sheet › text areas); geometry, engine, edits, rotation, colour, reading order |
| reading | every OCR run, kept: engine, model and its exact version, languages, confidence, plain text, the **structured document** (blocks, lines, words, boxes, styles, figures) and the raw output |
| correction | hand corrections as versions on top of a reading; the engine's reading never changes |
| tag, collection | labels; hand lists and saved searches (smart collections) |
| export | every file that left the library: format, checksum, settings, which readings and corrections it used |
| event | provenance log in the PREMIS spirit: import, fixity check, edit, read, correct, export, merge |
| embedding | vectors for similar images and search by meaning |
| search | full-text index (FTS5) of titles, notes, labels and current text |

## Fast

SQLite in WAL mode (readers never wait for writers), memory-mapped, indexes on every lookup,
full-text search with FTS5. Measured on this Mac: 100 000 items with text inserted in 0.5 s; a word
search in 1–2 ms; counting the library in 2 ms; 22 MB of catalog. Previews are files in `cache/`,
the gallery loads only what is on screen. Vectors: brute force in memory up to a few hundred
thousand (milliseconds), an index (sqlite-vec) beyond.

## Safe: what archivists do

- **SQLite** is a Library of Congress *recommended storage format* for datasets.
- **Fixity** (NDSA Levels of Digital Preservation): every file has a SHA-256 from the moment it
  enters; a fixity check job re-reads them and logs the result.
- **Provenance** (PREMIS): the `event` table records who did what, when, with which engine.
- **Packaging** (BagIt, OCFL): files named by checksum plus a manifest; a library can be exported as a
  BagIt bag for another archive or for a backup drive.
- **3-2-1 backups**: three copies, two kinds of media, one elsewhere. The library is a folder, so
  Time Machine, an external disk and a cloud drive all work; the catalog snapshots protect against
  mistakes between backups.

**Sidecars do not double the archive.** They hold metadata, not pixels: a few KB next to a file of
tens of MB (under 1%). They are written only when something about that file changes, never when
it is only viewed. If the catalog were lost, `store/` alone rebuilds it.

## Models

Models live once per Mac, not per library (`~/Library/Application Support/Scan Studio/models`,
plus Ollama's own). Each reading and selection records the engine and model that made it. A
library opened on a Mac without that model says so, like a missing font in Illustrator, and offers
the download with a progress bar; nothing already read is lost or changed.

## Text out: representations, never copies to edit

The text is stored structured (blocks, languages, styles), so it can be rendered into any format:

- **LaTeX**, book-capable: chapters by collection or date, sections per item, figures from the
  cutouts (`\includegraphics`), mixed languages marked (`\foreignlanguage`, polyglossia or babel),
  compatible with your own preamble; and searchable PDF, Markdown, Word (via pandoc), JSON.
- **nvim journal**: dated, linked, read-only exports. Each entry carries the item's UUID and a
  `scanstudio://item/<uuid>` link back; corrections are made in the app, the journal is
  regenerated. nvim is for taking parts and printing, not editing.
- **Directus**: a sync job pushes items, regions and text to your Directus site through its API.
- **Eagle**: cutouts and their text, as today.

## Phases

1. **Catalog** (this branch now): schema, library package, import with checksums, fixity,
   snapshots, sidecars, full-text search. Tests in `tests/test_library.py`.
2. Import of today's `~/Scans` (originals referenced in place, edit state and text migrated);
   Library view next to the folders; open several libraries.
3. Exports: LaTeX (book), searchable PDF, nvim journal, Word; BagIt.
4. Similar images and search by meaning (image and text embeddings).
5. Connectors: Directus sync, Eagle, merge libraries.

The working app on `master` stays as it is until the library is ready to replace the folders.
