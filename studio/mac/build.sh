#!/bin/zsh
# costruisce ~/Applications/Scan Studio.app: binario Swift, icona, Info.plist, firma ad hoc.
# Rifarla dopo aver cambiato ScanStudio.swift o l'icona (le pagine e il Python no: li legge vivi).
#   PYTHON=...      il Python con OpenCV (di solito lo sceglie install.sh: .venv del progetto)
#   SCANS_ROOT=...  la cartella delle scansioni (predefinita ~/Scans)
set -e
HERE=${0:A:h}
REPO=${HERE:h:h}
APP="${APP_DIR:-$HOME/Applications}/Scan Studio.app"   # APP_DIR: altrove, per le prove
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$REPO/.venv/bin/python3" ]]; then PYTHON="$REPO/.venv/bin/python3"; else PYTHON=$(command -v python3); fi
fi
SCANS_ROOT=${SCANS_ROOT:-$HOME/Scans}
VERSION=$(cat "$REPO/VERSION")
TMP=$(mktemp -d)
mkdir -p "$TMP/Scan Studio.app/Contents/MacOS" "$TMP/Scan Studio.app/Contents/Resources"
swiftc -O "$HERE/ScanStudio.swift" -o "$TMP/Scan Studio.app/Contents/MacOS/ScanStudio" -framework WebKit -framework AppKit

# icona: dall'immagine 1024 px dello studio, tutte le misure
ICON="$REPO/studio/static/icon.png"
SET="$TMP/AppIcon.iconset"; mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$ICON" --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$ICON" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o "$TMP/Scan Studio.app/Contents/Resources/AppIcon.icns"

cat > "$TMP/Scan Studio.app/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Scan Studio</string>
  <key>CFBundleDisplayName</key><string>Scan Studio</string>
  <key>CFBundleIdentifier</key><string>io.github.aallevi.scanstudio</string>
  <key>CFBundleExecutable</key><string>ScanStudio</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION%%-*}</string>
  <key>ScanStudioVersion</key><string>$VERSION</string>
  <key>ScanStudioRepo</key><string>$REPO</string>
  <key>ScanStudioPython</key><string>$PYTHON</string>
  <key>ScanStudioRoot</key><string>$SCANS_ROOT</string>
  <key>CFBundleVersion</key><string>$(date +%Y%m%d%H%M)</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.graphics-design</string>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
EOF

codesign --force --sign - "$TMP/Scan Studio.app"
# la vecchia si toglie solo quando la nuova e' pronta (stesso posto: il Dock la ritrova)
rm -rf "$APP"
mv "$TMP/Scan Studio.app" "$APP"
rm -rf "$TMP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP"
echo "built $APP ($VERSION, $PYTHON, scans in $SCANS_ROOT)"
