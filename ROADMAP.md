# Roadmap

Scan Studio is a beta (0.9). Two rules do not change:

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

**On the `library` branch (in progress, tried in "Scan Studio Preview"):** the library catalog
(SQLite: objects, files, parts, nested secondary areas, texts with correction versions, cuts, series,
tags/collections tables, history log, embeddings table, full-text search; checksums, snapshots,
sidecars); live sync with the studio; Library views Objects / Cutouts / Texts with links between
them; cuts carry their texts and IDs in their metadata; the one-source rule (re-cut, rename and
history when a part changes; rotation and text shared both ways; colour stored on the part);
"export" renamed "cut"; batch reading of cutouts; sort and filter by resolution; series as data;
Edit in Affinity / Preview (saves come back as linked versions); self-updating preview app.

## Next (library branch)

1. **Cuts at the centre:** series and objects feature their cuts; the original shown as "source".
2. **Storage switch:** managed library, one readable folder per object (original, kept cuts, edits,
   `item.json`), folder names produced from the data; inbox inside the library; the agent imports
   into it; the old `originals/` / `cut/` tree leaves the app. Files are moved in only after a
   byte-for-byte check — on the preview first, on the real scans folder only at switch-over, confirmed.
3. **Originals policy:** keep by default (they are the evidence and the only way to re-cut); lossless
   JPEG XL to halve their size; offline storage (external drive, library remembers where); an explicit
   "release this original" that keeps cut, geometry and checksum.
4. **Database editor:** browse every table, edit the safe fields (titles, dates, labels, notes, roles,
   tags, links, text) through the one-source path, every edit logged; notes on any row as a shared
   to-do list for changes.
5. **Parts and views:** group objects (a notebook and its pages, front/back/detail views); label and
   order editable from the library; tags and collections in the interface.
6. **Exports as representations:** LaTeX that can make a book (your preamble, mixed languages marked,
   figures from cuts) and the nvim journal (read-only, dated, linked back); searchable PDF (positioned
   text layer); Word; BagIt package.
7. **Archive sync:** one-way to the site (Directus): cuts + transcriptions + provenance, read-only
   there, linked by ID. To decide: a cut as its own record (an artefact others link to) or a file on
   existing records — depends on the site's collections.
8. **Several libraries:** open in separate windows (like Tropy), merge without duplicates.
9. **Models per Mac:** stored once, shared by all libraries; a library that needs a missing model
   asks to download it (like a missing font).
10. **Safety tools in the interface:** fixity check job, snapshots, backup advice (3-2-1).
11. **Merge into master** once the storage switch is done and tried.

## Next (text and cutting)

12. **OCR with layout rectangles:** models that give a box for every text block and picture
    (LightOnOCR-2-1B-bbox, PaddleOCR-VL, dots.mocr, MinerU), so the side-by-side view places each block
    where it is, pictures cut from the real pixels. Tested on real handwritten and typed pages first.
13. **Selectable text on the drawing** (like Live Text), from line or word boxes.
14. **OCR comparison** on real pages (GLM-OCR vs Qwen3-VL on difficult handwriting); Apple Vision's
    language detection can misfire on handwriting.
15. **Background removal benchmark:** BiRefNet lite / full / HR and RMBG-2.0 on scans and photos.
16. **Find + edge:** one model finds the objects, another cuts each edge up close.
17. **Open lid:** sketchbooks scanned with the lid open; flat-lid results stay byte-identical; shown
    before/after first.

## Later

18. **Scanner:** driving a flatbed directly (Canon LiDE 400): frame sets, presets, settings per frame,
    optical-only resolutions, prescan zoom, 16-bit originals.
19. **Colour calibration (IT8.7/2):** ArgyllCMS profile embedded; pixels untouched.
20. **"Fake pixels" copies,** off by default: descreen (moiré), 16-bit curves, BM3D noise reduction.
21. **Wizard and job manager:** a step-by-step batch wizard and a fuller jobs view.
22. **Search by content:** image and text embeddings over everything ("the drawing with the guitar").

## Ideas welcome

Open an issue: https://github.com/aallevi/scancut/issues
