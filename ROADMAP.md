# Roadmap

Scan Studio is a beta (0.9). The rule that does not change: **only real pixels**. Cutouts change
transparency only; anything that changes pixels makes a separate copy marked "fake pixels".

## Done

- Automatic cutting agent (inbox → originals → cutouts), never loses or overwrites a scan.
- Editor: engines (automatic, classic, Otsu, format from a corner, Apple Vision, SAM 3, Remove
  background, your own scripts), selection tools, Invert, merge, history, lossless rotation, 16-bit.
- Tabs, units on every number, search across scans, text and help, Mac Help menu.
- Text (OCR): Text pane beside the drawing, side-by-side text view, whole-document reading,
  readers Apple Vision, GLM-OCR and Qwen3-VL (handwriting, mixed languages).
- Local assistant (Ollama or any OpenAI-compatible server) and Ask Claude for jobs.
- Jobs: every task listed with real progress; installer with a progress bar.
- Tests (`tests/`, also in CI) and a UI health check (`tools/health.js`).

## Next

1. **OCR with layout rectangles.** Models that return a box for every text block and picture
   (LightOnOCR-2-1B-bbox, PaddleOCR-VL, dots.mocr, MinerU), so the side-by-side view places each
   paragraph, heading, table and picture in its own rectangle where it sits on the page, pictures
   cut from the real pixels. Tested on real handwritten and typed pages before choosing.
2. **Background removal benchmark.** BiRefNet lite / full / HR and RMBG-2.0 on real scans and
   photos, edges compared zoomed in, before any becomes a default.
3. **Find + edge.** One model finds the objects (SAM 3, automatic cut), another cuts each edge up
   close on a crop around it (BiRefNet HR), like box detection.
4. **Open lid.** Cutting sketchbooks scanned with the lid open (the background fades from light to
   dark); byte-identical results on flat-lid scans, shown before/after first.

## Later

5. **Scanner.** Driving a flatbed directly (tested on a Canon LiDE 400): frame sets, presets,
   settings per frame, optical-only resolutions, prescan zoom, 16-bit originals.
6. **Colour calibration (IT8.7/2).** ArgyllCMS profile embedded in the scans; pixels untouched.
7. **"Fake pixels" copies,** off by default and never replacing an original or a cutout:
   descreen (moiré), 16-bit curves, BM3D noise reduction.
8. **Wizard and job manager.** A step-by-step Vista-style wizard for a batch, and a fuller jobs view.
9. **Search by content.** Image and text embeddings over every scan: "the drawing with the
   guitar", or any phrase in the read text, by meaning.

## Ideas welcome

Open an issue: https://github.com/aallevi/scancut/issues
