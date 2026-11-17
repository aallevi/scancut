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

- **Read selected / Read all**: each part's text in its own block, editable; ↻ reads one again.
- **Read a box** (T): drag over any writing. Inside a part it becomes a **secondary area** of that part
  (text with its own place); outside every part a **loose area**.
- **Add to the part's text**: when reading the whole part fails, read boxes and add each one to the
  part's own text (a button on every area). The area goes; ⌘Z brings it back.
- **Read whole scan**: every word on the page, in a reader.
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

Every text is kept as Markdown: headings, lists, emphasis, tables. Some readers write tables in HTML
(LightOnOCR); they become Markdown tables when the text is stored, and so does HTML you type or paste.
The reader's own output stays with the reading. The scan files themselves are never written to: only
cuts carry their text.

On a cut, the Text pane shows its part's texts (the part, its secondary areas, the loose areas it
carries). ↻ reads one again on its scan, the same pixels as the cut, and keeps the reading you had;
**Versions** lists every reading and lets you pick one. Both change the text everywhere: the scan,
the cut file, the transcriptions.
