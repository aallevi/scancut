# Welcome to Scan Studio

Scan Studio turns scans of paper into **cuts**: one transparent image per sheet, with only the real
pixels of the paper. It also reads the writing on them and keeps everything in a **library**.

## Four things, linked

- **Source**: a scan (or any image) as it came in. Never changed.
- **Part**: a sheet found on a source: its outline, edits, rotation, name, colour, whether it is cut.
- **Cut**: the file made from a part. It carries the part's text and links back to it.
- **Text**: what was read on a part, with your corrections as versions.

## One source

Every characteristic of a part exists once. Rotate a cut, correct its text, rename it or move its
outline: the source's part, the cut file, the Text pane and the library all follow. Cuts are
re-cut by themselves; the previous files are kept in the history.

## Only real pixels

Cutting changes transparency only: no filling, no colour fixing, no invented edges. Anything that
would change pixels (the Fix menu) makes a separate copy marked "fake pixels".

## The usual way through

1. **Add** a source: scan it, or drop it in the inbox.
2. **Find parts**: Detect with an engine.
3. **Refine**: fix outlines with the tools.
4. **Read**: the Text pane.
5. **Cut** (⌘S).
