#!/bin/bash
# Scan Studio / scancut installer for macOS.
#   ./install.sh                 Python environment, helpers, the app in ~/Applications
#   ./install.sh --agent         also the inbox agent (cuts every scan that lands in <root>/inbox)
#   ./install.sh --tools         also the Homebrew tools: SANE scanner driver, ExifTool, JPEG XL
#   ./install.sh --root DIR      scans folder (default ~/Scans)
#   ./install.sh --python PATH   use this Python (with numpy, OpenCV, Pillow, tifffile) instead of .venv
set -e
cd "$(dirname "$0")"
REPO=$(pwd)
ROOT="$HOME/Scans"; AGENT=0; TOOLS=0; PY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) AGENT=1 ;;
    --tools) TOOLS=1 ;;
    --root) ROOT="$2"; shift ;;
    --python) PY="$2"; shift ;;
    -h|--help) sed -n 2,7p "$0"; exit 0 ;;
    *) echo "unknown option $1"; exit 1 ;;
  esac
  shift
done
ROOT=$(cd "$(dirname "$ROOT")" 2>/dev/null && echo "$(pwd)/$(basename "$ROOT")" || echo "$ROOT")
say() { printf '\n\033[1m%s\033[0m\n' "$1"; }

[ "$(uname)" = Darwin ] || { echo "Scan Studio runs on macOS only."; exit 1; }
if ! xcode-select -p >/dev/null 2>&1; then
  echo "The Xcode command-line tools are needed (Swift compiler). Run: xcode-select --install, then this again."
  exit 1
fi

say "Python"
if [ -z "$PY" ]; then
  # the newest Python 3.10+ around (macOS's own python3 is 3.9)
  BASE=""
  for c in python3.13 python3.12 python3.11 python3.10 python3.14 python3; do
    p=$(command -v $c || true)
    if [ -n "$p" ] && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then BASE=$p; break; fi
  done
  [ -n "$BASE" ] || { echo "Python 3.10 or newer is needed: brew install python (or python.org)."; exit 1; }
  [ -x .venv/bin/python3 ] || "$BASE" -m venv .venv
  PY="$REPO/.venv/bin/python3"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r requirements.txt
fi
"$PY" -c 'import numpy, cv2, PIL, tifffile' || { echo "$PY lacks numpy/OpenCV/Pillow/tifffile: pip install -r requirements.txt"; exit 1; }
echo "$PY"

say "Apple Vision helpers"
swiftc -O vision_mask.swift -o vision_mask
swiftc -O studio/ocr.swift -o studio/ocr
echo "vision_mask, studio/ocr"

say "Scans folder"
mkdir -p "$ROOT"/{inbox,originals,cut,failed,.scancut}
echo "$ROOT"

if [ $TOOLS = 1 ]; then
  say "Homebrew tools"
  if command -v brew >/dev/null; then brew install sane-backends exiftool jpeg-xl
  else echo "Homebrew not found (https://brew.sh): skipped. You can add these later from the app, Add-ons."; fi
fi

say "App"
PYTHON="$PY" SCANS_ROOT="$ROOT" zsh studio/mac/build.sh

if [ $AGENT = 1 ]; then
  say "Inbox agent"
  LABEL=io.github.aallevi.scancut
  DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  sed -e "s|@LABEL@|$LABEL|g" -e "s|@PYTHON@|$PY|g" -e "s|@REPO@|$REPO|g" -e "s|@ROOT@|$ROOT|g" agent/scancut.plist.in > "$DEST"
  launchctl unload "$DEST" 2>/dev/null || true
  launchctl load "$DEST"
  echo "$DEST: watches $ROOT/inbox"
fi

say "Done"
echo "Open Scan Studio from ~/Applications (or: open -a 'Scan Studio')."
echo "Optional extras (scanner driver, SAM 3, ...): in the app, Studio > Add-ons."
