# Roadmap

Scan Studio is a beta (0.11). Two rules do not change:

- **Only real pixels.** Cutouts change transparency only; anything that changes pixels makes a
  separate copy marked "fake pixels".
- **One source.** Every characteristic of a part (outline, edits, holes, rotation, label, order,
  colour, included in the cut, text and its areas, sizes) exists once; the scan's sheet, its cut file,
  the text views and the library views are representations of it. Change it anywhere, everything follows.

## Roles: what Scan Studio is for

| | Scan Studio | The art archive (site, e.g. Directus) | Asset tools (e.g. Eagle) | Writing (nvim, LaTeX) |
|---|---|---|---|---|
| Job | capture and extraction: paper → verified cuts and transcriptions | meaning and arrangement: works, publications, installations, books, physical folders | browsing, tags, similarity | writing, print |
| Owns | scans, scanning sessions (series), parts and their **cuts**, geometry, **transcriptions** (reading + corrections), provenance | titles, descriptions, credits, groupings, publishing | nothing permanent | your own texts |
| Gets from Scan Studio | — | cuts + transcription + provenance, one way, read-only, same IDs | cut files with IDs and text | transcriptions, read-only, dated, linked |

Scan Studio goes as far as "physically true and verified"; interpretation belongs to the archive.
Transcriptions are corrected here and re-synced; curated or translated texts are the archive's.

## Done

**Cutting and editing:** automatic agent (inbox → originals → cutouts, never loses or overwrites);
engines (automatic, classic, Otsu, corner format, Apple Vision, SAM 3, Remove background with BiRefNet
family models, scripts); selection tools, Invert (⇧⌘I), merge, history, lossless rotation, 16-bit.
**Interface:** IE7-style tabs (one scan per tab; click = this tab, ⌘-click = new tab), units on every
number, search across scans/text/help, Mac Help menu search, live job badge.
**Text (OCR):** Text pane beside the drawing, side-by-side text view (same zoom, text in the part's
colour, Markdown rendered, editable in place), whole-document reading with a reader, the Text tool for a
box, readers Apple Vision / GLM-OCR / Qwen3-VL (handwriting, mixed languages), long pages in strips.
**Assistant:** local Help model (Ollama or any OpenAI-compatible server) with search by meaning;
Ask Claude for jobs, given the right help first.
**Reliability:** tests (`tests/`, in CI), UI health check (`tools/health.js`), every task in Jobs with
real progress, installer with a progress bar.

**Library (0.10):** the catalog (SQLite in `Library.DocuLib`: objects, files, parts, nested
secondary areas, texts with correction versions, cuts, series, places, tags/collections tables,
history log, embeddings table, full-text search; checksums, snapshots, sidecars) is the only store of
the studio; Library views Objects / Cuts / Texts with links between them; cuts carry their texts and
IDs in their metadata; the one-source rule (re-cut, rename and history when a part changes; only the
changed part is re-cut; rotation and text shared both ways); "export" renamed "cut"; refining a cut
on its source ("Edit its part"); a cut's own parts; transcriptions for nvim as read-only Markdown
shaped like wiki notes (or LaTeX), with `nvim/scanstudio.lua` to open, search, take and insert parts;
"what travels" with exported cuts chosen per destination (Eagle, archive, folder), metadata only;
a read-only link to the Directus archive (token in the Keychain); series and places as data; Trash with days to keep;
Edit in Affinity / Preview (saves come back as linked versions). **Files inside:** "Move files in…"
puts originals and cuts in the package as lossless JPEG XL, checked pixel for pixel; the agent and the
scanner file new scans straight in, flushed to disk before the source goes. **Scanner:** phases and
time left, Cancel that parks the head, Space and timed sessions, each page filed at once ("File
scans" job). **First start on an existing folder:** old state migrated, old cuts linked to their parts
by their pixels.

**Schema 2 (0.11):** every part is an item of its own (`item.kind = 'part'`, one per sheet region), at the
same level as scans and documents: place, number, category, tags, collections and Trash live on items only,
with the rules in the database; parts follow their outline (removed → trashed, back → back, label → title).
Records for the archive (`studio/library/records.py`): scan, parts (cut file, text as Inscriptions) and,
when wanted, each text as a record of its own, "Part of" its part; as a package (`records.json` + files) or
sent to Directus by stable ids (`source_id` = part uuid), updating instead of duplicating; `archive_link`
remembers what went where. Server hardened (origin and host checks, no CORS, CSP, size limits, destination
and app checks, AppleScript argument passing), lists in three queries, Check reads cut texts in one exiftool
call. docs/DATABASE.md is the map. Bench: `tools/bench_library.py`.

**Objects, batch, text (0.12, November 2026):** parts that are the same piece of paper (front and back, a
double page, one drawing in two scans) are joined in the library as one **object**, no file made: one tile
among the cuts, a line under each part, one place for all sides. Batch actions are the same everywhere (Batch
menu, gallery, library, cuts): detect, detect and cut, cut marked parts, pass whole, read, join, multipage file,
export, Trash; items being processed show a spinner. **Text is kept whole:** a reading is stored exactly as the
reader wrote it, and the reader's whole output beside it (Apple Vision lines with boxes and confidence,
LightOnOCR / Unlimited-OCR blocks with boxes, GLM-OCR answers per strip); views render what is there (HTML tables
with merged cells, superscript, formulas). A Text dialog reads from anywhere with the reader chosen for that job
(only unread / unread by this reader / again), Text settings hold the default reader and reading at every cut.
Areas read on a cut belong to its part, placed on the scan; every area can be removed. The journal for nvim goes
through pandoc and EasyPrint without losing a character (tables, interrupted tables, wide tables, `^ ~ @`).
**Speed:** the editor shows parts, texts and the side-by-side view before the image; saved thumbnails come back at
once; text written into a cut keeps its previews. Tabs opened from an item go behind, as in a browser. Scan files
are never written to (only cuts carry text).

## Next (library)

1. **Library autonomy:** the library package holds everything that belongs to it: files (originals and cuts as
   lossless JPEG XL), the inbox, its settings (journal folder, readers chosen, travel fields, places), caches it can
   rebuild. It works without the scans folder around it, opens on another Mac as it is, and the agent and the
   scanner file straight into it. `studio-data/` keeps only what belongs to this Mac (window, models).
2. **Folder removal:** `originals/`, `cut/` and `failed/` stop being the structure; they become views of the
   library (by series, by place, by date, "to check"). The sidebar's folder tree gives way to series and places.
   Removing a folder (a batch) from the app moves its sources and cuts to the library Trash, with the same
   rules as any other Trash (days to keep, put back). Readable folders come back only as an export.
3. **Cuts at the centre:** series and objects feature their cuts; the original shown as "source".
4. **Originals policy:** keep by default (they are the evidence and the only way to re-cut); offline
   storage (external drive, library remembers where); an explicit "release this original" that keeps
   cut, geometry and checksum.
5. **Database editor:** browse every table, edit the safe fields (titles, dates, labels, notes, roles,
   tags, links, text) through the one-source path, every edit logged; notes on any row as a shared
   to-do list for changes.
6. **Parts, objects and views:** objects in the search box and in the archive export; group objects (a
   notebook and its pages); label and order editable from the library; tags and collections in the interface.
7. **Exports as representations:** LaTeX that can make a book (your preamble, mixed languages marked,
   figures from cuts); searchable PDF (positioned text layer); Word; BagIt package.
8. **Archive link:** Scan Studio prepares material for the archive (Directus) as an export package
   its importer already reads, upserted by stable IDs (`source` / `source_id`), each field owned by one
   side. Done: the read-only link and the export with a `.json` per cut. Next: the archive's importer
   reads those folders; show in the library which cuts the archive already has.
9. **Several libraries:** open in separate windows (like Tropy), merge without duplicates.
10. **Models per Mac:** stored once, shared by all libraries; a library that needs a missing model
    asks to download it (like a missing font).
11. **Safety tools in the interface:** fixity check job, snapshots, backup advice (3-2-1).

## Next (text and cutting)

12. **Automatic reader choice:** a quick Apple Vision pass decides per page (sure, plain lines: printed; uneven
    or unsure: handwriting → GLM-OCR; grids, columns, pictures: layout → LightOnOCR), with a default per series
    remembered from your choices; the reason shown, always overridable.
13. **Layout rectangles in the side-by-side view:** the readers' block boxes are now kept with every reading;
    next, each block placed where it is on the page, pictures cut from the real pixels.
14. **Selectable text on the drawing** (like Live Text), from the line and word boxes already kept.
15. **Old cut texts into the library:** texts read at cut time before the library existed live only in the
    cut files' descriptions; brought in as readings of their parts (the files stay as they are).
16. **OCR comparison** on real pages (GLM-OCR, Qwen3-VL, LightOnOCR, Unlimited-OCR on difficult handwriting);
    Apple Vision's language detection can misfire on handwriting.
17. **Background removal benchmark:** BiRefNet lite / full / HR and RMBG-2.0 on scans and photos.
18. **Find + edge:** one model finds the objects, another cuts each edge up close.
19. **Open lid:** sketchbooks scanned with the lid open; flat-lid results stay byte-identical; shown
    before/after first.

## Later

20. **Scanner:** done through SANE (areas and frame sets, settings per area, optical resolutions only,
    area preview, 48-bit); left: named presets of settings, and a check against ImageCaptureCore.
21. **Colour calibration (IT8.7/2):** ArgyllCMS profile embedded; pixels untouched.
22. **"Fake pixels" copies,** off by default: descreen (moiré), 16-bit curves, BM3D noise reduction.
23. **Wizard and job manager:** a step-by-step batch wizard and a fuller jobs view.
24. **Search by content:** image and text embeddings over everything ("the drawing with the guitar").

## Ideas welcome

Open an issue: https://github.com/aallevi/scancut/issues
