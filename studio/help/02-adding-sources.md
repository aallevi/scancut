# Adding sources

## Scanning

**Scanners** (left, under Studio) drives a flatbed directly: preview the bed, draw scan areas (each
with its own resolution and mode), save groups of areas as frame sets ("two A5 side by side"),
and scan page after page. Each scan is filed among the sources at once (a second or so, shown in
Jobs as **File scans**); in a library with its files inside, it arrives already in lossless JPEG XL.

A **session** is the name in **Series**: every scan is named "<series> <number>" and numbered on.
Page after page:

- **Space bar scans the next page**: press Space (anywhere on the page, except while typing).
- **Timed**: set the seconds, **Start timed**. The page on the bed is scanned at once; when the
  scanner has read it, the countdown gives you time to swap the page (three beeps at the end), then
  the next scan. Space skips the wait; Stop, Esc or Cancel end it.

While a page is filed, the next one can already be scanned. The status line shows
each step: the scanner getting ready (lamp and calibration, about 10 s on the LiDE 400), the
percentage and the time left, then filing. **Cancel** asks the scanner once to stop: it brings its
head back home and is ready again (asking twice would leave the head halfway). Areas already scanned
are kept. A scan identical byte for byte to an earlier one is not kept twice, and the line says so.

Every scan becomes a source of its series in the library at once, and keeps how it was made: the
scanner, resolution, mode and area (shown with the source in the library). There is nothing to update
by hand.

Image Capture works too: scan into the inbox folder.

## Dragging files in

Drag files from the Finder onto the window:

- anywhere (or onto **Sources**): they become sources, like a scan, filed into their series;
- onto **Cuts** (the Cuts view, the cut folder or Cuts in the sidebar): they are added as cuts made
  elsewhere.

The files are copied byte for byte, never over another file.

## The inbox

Anything put in the scans folder's **inbox** is filed by the scan agent: moved into the sources
(never lost, never overwritten; identical repeats are dropped) and grouped into a **series** by
its name ("sketchbook 4.png" belongs to "sketchbook"). Photos, AirDrop, downloads: any image works.

## Series

A series is a scanning session or a group of files with the same name. Each series remembers
the engine and settings of its last cut and offers them again for the next scan.
