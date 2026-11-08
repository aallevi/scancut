# Refining parts

Every edit keeps the engine's real edge everywhere else: moving a point changes only the area
between the old and the new outline. Everything can be undone (⌘Z).

## Tools

- **Select (V)**: click a part; ⇧ or ⌘ adds more; drag on empty space selects with a box.
- **Pan (H)**, or hold Space. Two fingers pan; pinch or ⌘-scroll zooms.
- **Edit points (A)**: drag points; double-click an edge adds one, ⌥-click removes.
- **Polygon (P)**: a new part, click by click; Enter closes it.
- **Rectangle (M)**, **Lasso (L)**, **Brush (B)**: add to a part; K, E (or ⌥) cut away. X swaps.
- **Magic Wand (W)**: like Photoshop, per-channel tolerance, contiguous or not. Clicking paper with
  no part there makes a new part.
- **Read text (T)**: drag a box over writing; see Text.
- **Detect in a box (R)**: the chosen engine inside a box.

## Parts

- **Invert** (⇧⌘I): everything except the selected parts; again gives them back.
- **Merge into one**: several parts become one, each keeping its exact edge.
- **Only this one** (⌃-click a part): only that part is cut; again, all are back.
- **Rotate 90°** (⟲ ⟳ in the Sheets list): lossless; its cuts turn with it. A JPEG cut brought in from
  elsewhere becomes a PNG with exactly the same pixels when turned (the JPEG stays in the history).
- Holes punched in the paper become transparent by themselves.
- **Cut view** (O) darkens what will be cut away.

## Refining a cut

A cut is a part of its scan, and the real pixels are in the scan. In a cut, **Edit its part** (or
picking the brush, lasso, rectangle, wand or points) opens the scan framed on that part, alone: the
other parts are hidden and nothing else can change. Edit as usual (fast, ⌘Z works), then **Done: back
to the cut**: only that cut is redone, and you are back on it. Add back what was cut away, or cut more
away; nothing is invented. A cut with parts of its own (a cut of a cut) is refined like a scan.

When only a part's outline or edits change, only its cut is redone; renaming, reordering or
excluding parts redoes all the cuts of the scan, since their names change.
