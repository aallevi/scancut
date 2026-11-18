# Text (OCR)

Reading never changes pixels. Everything is in the **Text pane** beside the drawing
(Text › Show text pane, or T).

## Readers

- **Apple Vision**: built in, instant. Print and neat handwriting; no layout.
- **GLM-OCR** (Add-ons, ~2.7 GB): handwriting and print, keeps headings, lists and tables.
- **Qwen3-VL 8B** (Add-ons, ~6 GB): difficult handwriting.
- **Unlimited-OCR** (Add-ons, ~3.7 GB): printed documents with their layout: a box for every title, text
  block and picture, so the side-by-side view shows pictures from the real pixels where they are. Not
  for handwriting.

Text in several languages is kept as written, never translated.

## Reading

- **Read selected parts / Read every part**: each part read whole. That is the part's own text, its
  **whole part** block (for example "a · whole part"), editable; ↻ reads it again. "Read whole: no text
  found" means the whole part was read and nothing came out.
- **Read an area** (T): drag over any writing. Inside a part (or on a cut, which is its part) it becomes
  a **secondary area** of that part, with its own text and place ("a·1"); outside every part a **loose
  area**.
- **Add to the part's text**: when reading the whole part fails, read areas and add each one to the
  part's own text (a button on every area). The area goes; ⌘Z brings it back.
- **Read the whole page** (on a scan): every word on the page as one text, the text of the whole
  source, not of a part. On a cut the button is **Read the whole cut**: the cut is its part, so that is
  the part's own text.
- In a gallery: select files and use Text › Read the whole document, or read into the cut files.

## Reading many at once

Select sources in a gallery or Library › Sources, or cuts in Library › Cuts or a cuts folder, then
**Read text…** (Batch menu, the pane, or Text › Read text of the selection). The window asks:

- **What**: for sources, their cuts one by one, or the whole scans.
- **Reader**: any installed reader, for this job only. The default stays as it is unless you tick
  **Make this the default reader**. Readers not installed are listed and greyed; Add-ons installs them.
- **Which**: only those not read yet; those not read with this reader; or all again. Earlier readings
  are never lost: they stay under Versions.
- **Free the model's memory when done**, for a long batch with a big model.

Every reading goes to the library: the text of the part, its cut file's description and the
transcriptions, and it follows every correction.

## Text settings

Text › Text settings…: the default reader; **Read each new cut** and the reader for it. Reading after a
cut runs as its own job once the cut is written, so cutting is never slowed down, and only cuts without a
text are read. A fast reader there (Apple Vision) and a careful one for the cuts you choose is a good pair.

## Side by side

A second view the size of the scan, zooming and scrolling with it: each text sits where its part or
box is, in the part's colour, formatted. Click a text to correct it.

## Where it is stored

In the library, as the part's text: every reading is kept, corrections are versions on top. In each
cut file, inside its description. A cut's text is always its part's text.

A text is kept exactly as the reader wrote it, and so is a correction as you typed it: nothing is
converted. With it the library keeps the reader's whole output: the box and confidence of every line
(Apple Vision), every block with its box (LightOnOCR, Unlimited-OCR), the full answer for every strip
(GLM-OCR). Every view shows the text as it is: Markdown, and HTML tables with merged cells, line
breaks in cells, superscript, subscript and underline, in the studio and in the transcriptions (LaTeX
tables through pandoc, pandoc grid tables in Markdown). Scan files are never written to: only cuts
carry their text.

On a cut, the Text pane shows its part's texts (the part, its secondary areas, the loose areas it
carries). A cut is its part: a box read on a cut is a secondary area of that part, placed on the scan
where the cut shows it (through the same straightening and turns), with the same name there and on the
cut. Areas read on a cut before this were moved to their part, with their readings.

Every area can be removed with its ✕, in the Text pane and in the side-by-side view, also from a cut
(it goes from its part, its cut and the transcriptions; the history keeps it). ↻ reads one again on its scan, the same pixels as the cut, and keeps the reading you had;
**Versions** lists every reading and lets you pick one. Both change the text everywhere: the scan,
the cut file, the transcriptions.
