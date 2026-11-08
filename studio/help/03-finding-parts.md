# Finding parts: Detect

Open a source and choose an engine in the right-hand panel (or the Detect menu), then press
**Detect**. Detect never throws away parts you drew by hand, and keeps earlier results under
**Earlier** so you can go back.

## Engines

- **Automatic (as the agent)**: the scan agent's own cut. Finds the lid colour, removes it from the
  outside in, then the shadow; keeps fibres and tears; uses Apple Vision when the paper is close to
  the lid colour. **Tolerance ×**: 1 is the agent's choice; higher removes more lid and shadow.
- **Classic auto-cut**: the same without the Apple Vision fallback.
- **Otsu threshold**: splits light from dark at the best cut-off. Fast; good when paper and lid
  differ clearly in lightness.
- **Format from a corner**: no detection: an exact A3–A7, Letter or photo rectangle from the corner
  where you placed the sheet. Instant, works in batch.
- **Paper frames**: no detection: fixed frames (A4, two A5, four A6…) or a frame set saved on the
  Scanners page, measured from the corner of the bed. For batches of the same size: scan and cut with
  the same areas. If a scan was made of one area of the bed, the frames follow it.
- **Apple Vision**: foreground objects found by macOS. Smooth edges; for white on white.
- **SAM 3**: finds what you name ("drawing", "photo", "ticket"). Downloaded from Add-ons. Choose it
  as the engine, then Detect › Look for… sets what it searches; the S tool picks objects by clicking.
- **Remove background**: the BiRefNet models (Add-ons), for photos and lifting a subject.
- **Scripts**: your own engines in the scripts folder.

Model engines (SAM 3, Remove background, the text readers) run in their own process, load on first
use and unload by themselves after a few idle minutes. Detect › Free memory unloads them at once.

## Compare

**Compare engines** (C) draws several engines' outlines over the scan, each in its colour.

## Detect in a box

The box tool (R) runs the chosen engine only inside the box you drag: useful for one sheet among
many, or a crowded bed.
