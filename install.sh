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

[ "$(uname)" = Darwin ] || { echo "Scan Studio runs on macOS only."; exit 1; }
if ! xcode-select -p >/dev/null 2>&1; then
  echo "The Xcode command-line tools are needed (Swift compiler). Run: xcode-select --install, then this again."
  exit 1
fi

# ---- barra di avanzamento: un passo per cosa installata; i dettagli in install.log
LOG="$REPO/install.log"; : > "$LOG"
PKGS=$(grep -v '^ *#' requirements.txt | sed 's/#.*//' | awk 'NF {print $1}')
STEPS=5                                                      # controllo Python, helper x2, cartella, app
[ -z "$PY" ] && STEPS=$(( STEPS + 2 + $(echo "$PKGS" | wc -l) ))   # venv, pip, un pacchetto per riga
[ $TOOLS = 1 ] && STEPS=$(( STEPS + 3 ))
[ $AGENT = 1 ] && STEPS=$(( STEPS + 1 ))
STEP=0; W=32
bar() {   # $1 messaggio, $2 secondi passati (facoltativo)
  local pct=$(( STEP * 100 / STEPS )) n=$(( STEP * W / STEPS )) b="" i
  for ((i = 0; i < W; i++)); do [ $i -lt $n ] && b="${b}█" || b="${b}░"; done
  local line="$1${2:+  ($2 s)}" cols=$(tput cols 2>/dev/null || echo 80)
  [ ${#line} -gt $(( cols - W - 10 )) ] && line="${line:0:$(( cols - W - 11 ))}…"
  printf '\r\033[K  %s %3d%%  %s' "$b" "$pct" "$line"
}
step() {  # step "messaggio" comando...: gira in sottofondo, la barra resta viva
  local msg=$1; shift
  echo "== $msg: $*" >> "$LOG"
  "$@" >> "$LOG" 2>&1 & local pid=$! t0=$SECONDS
  while kill -0 $pid 2>/dev/null; do bar "$msg" $(( SECONDS - t0 )); sleep 0.25; done
  if ! wait $pid; then
    printf '\n\n  Failed: %s. Last lines of %s:\n\n' "$msg" "$LOG"; tail -15 "$LOG" | sed 's/^/    /'; exit 1
  fi
  STEP=$(( STEP + 1 )); bar "$msg"
}
echo; echo "  Installing Scan Studio"; echo

if [ -z "$PY" ]; then
  # the newest Python 3.10+ around (macOS's own python3 is 3.9)
  BASE=""
  for c in python3.13 python3.12 python3.11 python3.10 python3.14 python3; do
    p=$(command -v $c || true)
    if [ -n "$p" ] && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then BASE=$p; break; fi
  done
  [ -n "$BASE" ] || { echo "Python 3.10 or newer is needed: brew install python (or python.org)."; exit 1; }
  PY="$REPO/.venv/bin/python3"
  if [ -x "$PY" ]; then STEP=$(( STEP + 1 )); else step "Python environment (.venv)" "$BASE" -m venv .venv; fi
  step "pip" "$PY" -m pip install --quiet --upgrade pip
  for pk in $PKGS; do step "$(echo "$pk" | sed 's/[<>=].*//')" "$PY" -m pip install --quiet "$pk"; done
fi
step "Checking Python" "$PY" -c 'import numpy, cv2, PIL, tifffile'

step "Apple Vision helper" swiftc -O vision_mask.swift -o vision_mask
step "Text (OCR) helper" swiftc -O studio/ocr.swift -o studio/ocr
step "Scans folder" mkdir -p "$ROOT"/inbox "$ROOT"/originals "$ROOT"/cut "$ROOT"/failed "$ROOT"/.scancut

if [ $TOOLS = 1 ]; then
  if command -v brew >/dev/null; then
    for t in sane-backends exiftool jpeg-xl; do step "Homebrew: $t" brew install $t; done
  else STEP=$(( STEP + 3 )); echo "  (Homebrew not found: scanner driver, ExifTool, JPEG XL skipped; add them later in Add-ons)" >> "$LOG"; fi
fi

step "The app" env PYTHON="$PY" SCANS_ROOT="$ROOT" zsh studio/mac/build.sh

if [ $AGENT = 1 ]; then
  LABEL=io.github.aallevi.scancut
  DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
  agent() {
    mkdir -p "$HOME/Library/LaunchAgents"
    sed -e "s|@LABEL@|$LABEL|g" -e "s|@PYTHON@|$PY|g" -e "s|@REPO@|$REPO|g" -e "s|@ROOT@|$ROOT|g" agent/scancut.plist.in > "$DEST"
    launchctl unload "$DEST" 2>/dev/null || true
    launchctl load "$DEST"
  }
  step "Inbox agent" agent
fi

STEP=$STEPS; bar "Done"; echo; echo
echo "  Scans folder: $ROOT"
echo "  Open Scan Studio from ~/Applications (or: open -a 'Scan Studio')."
echo "  Optional extras (scanner driver, SAM 3, local assistant, handwriting OCR): in the app, Studio › Add-ons."
echo "  Details: $LOG"
