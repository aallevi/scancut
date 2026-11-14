# The database: how the library is organised (schema 2)

One SQLite file, `Library.DocuLib/library.sqlite`, holds everything the studio knows. Pixels are files on
disk; the catalog knows each file by its SHA-256. This page is the map: the tables, how they group, and how
they line up with the archive site (Directus, `records`). The design rule is unchanged: **one source for every
characteristic**, every view derived from it.

## The tree

```
Library
├── Files (the real pixels, never changed)
│   ├── asset             one row per file: checksum, size, path, pixels, dpi, bits, ICC, EXIF/XMP
│   └── capture           how a file arrived: scanner (device, dpi, mode, area) or dragged in
│
├── Things (every archived thing is an item, at the same level)
│   ├── item  kind=scan   a source: a scan, with its files (item_asset: view, front, back, detail, edit, cutout)
│   ├── item  kind=part   ONE PART = ONE ITEM: a cut sheet of a scan. parent_id = the scan, region_id = its outline.
│   │                     Carries place, number in the place, category, date, notes, tags, collections, trash.
│   ├── item  kind=piece  a part found on a cut (a cut cut again); parent_id = the scan the cut came from
│   ├── item  kind=cut    a cut file brought from outside, with no source here
│   ├── item  kind=file   any other file opened in the studio
│   └── series            the scanning session (folder) an item belongs to; parts inherit it from their scan
│
├── Geometry (where things are on a file)
│   └── region            kind=sheet: a part's outline, edits (ops), holes, rotation, included-in-cut, label, order, colour
│                         kind=text: a text area inside a sheet (parent_id) or loose on the file
│                         removed_at: taken away in the studio, kept as history (its part item is then in the trash)
│
├── Text (versions, never overwritten)
│   ├── reading           every OCR run: engine, model, exact model digest, languages, confidence, plain text, structured doc, raw
│   ├── correction        hand corrections as numbered versions on top of a reading
│   ├── current_text      (view) the latest correction, else the reading
│   └── text_link         which cut files carry a text (the cut of the part the text belongs to)
│
├── Representations (files made from the source)
│   └── cut               each cut file of a part: format, path, checksum, settings; a re-cut retires the old row/file into history
│
├── Where things are kept (as in the archive)
│   ├── place             chest, drawer, box, folder; nested; numbers unique per place (triggers)
│   └── category          Drawing, Document, Photograph… the archive's categories
│
├── Ordering
│   ├── tag, item_tag     labels
│   └── collection, collection_item   hand lists or saved searches, nested
│
├── Exchange with the archive
│   └── archive_link      what was sent where: entity (item | text | asset | place), uuid, archive url, id there, checksum
│
├── Safety and history
│   ├── event             provenance log (PREMIS): import, fixity, edit, read, correct, cut, recut, move, archive, migrate
│   ├── trash             what is in the Trash, where each file came from, when it empties
│   ├── editstate         the studio session per file: version, engine, parameters, Earlier versions
│   └── meta, setting     schema version, library uuid and name; per-library settings (JSON)
│
└── Search
    ├── search            FTS5 over title, notes, labels and current text, per item
    └── embedding         vectors (image or text) per asset, region or reading, per model
```

## A part is an item

Until schema 1 a part was only a `region` row, and the archival facts of a part (place, number, category) sat
on the region. Since schema 2 **every sheet region has exactly one item** (`item.kind = 'part'`,
`item.region_id` unique, `item.parent_id` = the scan's item). The region keeps the geometry; the item keeps
what the archive cares about. So a part can be placed, numbered, categorised, tagged, collected, trashed and
exported exactly like a scan, a photo or a document: everything archival lives in one table with one set of
rules (the triggers in `places.sql`). The migration creates the part items, moves place, number and category
from the regions onto them, rebuilds `region` without those columns and keeps a snapshot
(`snapshots/*-before-parts-as-items.sqlite`).

What follows from it, automatically (`bridge.parts_follow`): a part removed in the studio puts its item in the
trash; brought back (Undo), it comes back, unless its number in the place was taken meanwhile; a label change
renames the item; a scan moved to the Trash takes its parts along and brings them back together. Library ›
Check reports a part without its item, two items for one part, or an item out of step with its part.

A part without a place or category of its own follows its scan; a piece found on a cut follows the part the
cut came from. Both are read, never copied (`effective_place`).

## Text: part of the scan and a thing of its own

A text belongs to a region (a part, a text area inside it, or a loose area) through `reading.region_id`;
every reading and every correction is kept, the current one is a view. The same text travels in three ways,
all derived from the same rows: embedded in the part's cut file (XMP, IPTC, EXIF), in the transcription
folder for nvim, and to the archive either inside the part's record (`inscriptions`) or as a record of its own
(category `document`, `source_id = text:<region uuid>`, "Part of" the part's record). Correcting the text in
any view changes the rows; the cut, the folder and the archive follow.

## Alignment with the archive (Directus `records`)

| Scan Studio | Archive record | Notes |
|---|---|---|
| item kind=scan | category `scan`, no files | the "Part of" of its parts; originals stay in the library |
| item kind=part | its category (else the scan's, else `drawing`), the cut as `media` | `source = scanstudio`, `source_id = part uuid` (stable across re-cuts; the cut's uuid and sha travel with the file) |
| current text of the part | `inscriptions` of the part, and/or its own `document` record | chosen at export time |
| item.date (EDTF) | `date_start`, `date_end`, `date_text` | `2014-05?` → start 2014-05-01, text "2014-05?" |
| region bbox × asset dpi | `dimensions` "h × w cm" | rotation applied |
| place (archive_id known) + item.place_number | `kept_in`, `number` | only on first send; the archive owns location afterwards |
| provenance | private `notes` | library uuid, region uuid, checksums |
| `archive_link` | – | what was sent, with which id and checksum, so sending again updates instead of duplicating |

Fields the studio owns on later sends: `inscriptions`, `dimensions`, `media`. Everything else (title, dates,
descriptions, place) is the archive's after the first send. Sending needs a token allowed to create records
and files; with a read-only token (the recommended default) use **Package…**: a folder with `records.json`
and the cut files, in the same shape, for the archive's importer.

## Rules the database itself enforces

- Foreign keys on, `STRICT` tables, JSON columns validated.
- A place cannot be inside itself; a place that still keeps things cannot be deleted.
- Two things in the same place never share a number (items and child places count together); a number
  needs a place; unknown categories are refused.
- A part item needs a sheet region and belongs to the region's item (`item_part_i`).
- One item per region (`item_region` unique index).
- Managed files are named by checksum: identical bytes are one file.

## Speed

WAL journal, memory map, `PRAGMA optimize` at open. Indexes on every lookup the views make:
`item_asset(item_id, role, position)`, `region(kind, parent_id, removed_at, asset_id)`,
`item(place_id, place_number)`, `item(region_id)`, `cut(region_id, id)`, `cut(path, id)`. The Objects list
reads its counts and thumbnails in three queries per page instead of six per row. `tools/bench_library.py`
builds 2000 scans with 4000 parts and times the views (all under 50 ms on this Mac).
