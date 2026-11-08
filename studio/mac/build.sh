#!/bin/zsh
# costruisce ~/Applications/Scan Studio.app: binario Swift, icona, Info.plist, firma ad hoc.
# Rifarla dopo aver cambiato ScanStudio.swift o l'icona (le pagine e il Python no: li legge vivi).
#   PYTHON=...      il Python con OpenCV (di solito lo sceglie install.sh: .venv del progetto)
#   SCANS_ROOT=...  la cartella delle scansioni (predefinita ~/Scans)
#   APP_NAME=...    altro nome (es. "Scan Studio Preview"), con PORT=... e un suo identificativo: gira accanto all'altra
set -e
HERE=${0:A:h}
REPO=${HERE:h:h}
NAME=${APP_NAME:-Scan Studio}
PORT=${PORT:-8765}
BID=io.github.aallevi.scanstudio; [[ "$NAME" != "Scan Studio" ]] && BID="$BID.${${NAME:l}// /-}"
APP="${APP_DIR:-$HOME/Applications}/$NAME.app"   # APP_DIR: altrove, per le prove
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$REPO/.venv/bin/python3" ]]; then PYTHON="$REPO/.venv/bin/python3"; else PYTHON=$(command -v python3); fi
fi
SCANS_ROOT=${SCANS_ROOT:-$HOME/Scans}
VERSION=$(cat "$REPO/VERSION")
TMP=$(mktemp -d)
mkdir -p "$TMP/$NAME.app/Contents/MacOS" "$TMP/$NAME.app/Contents/Resources"
swiftc -O "$HERE/ScanStudio.swift" -o "$TMP/$NAME.app/Contents/MacOS/ScanStudio" -framework WebKit -framework AppKit

# icona: dall'immagine 1024 px dello studio, tutte le misure
ICON="$REPO/studio/static/icon.png"
SET="$TMP/AppIcon.iconset"; mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$ICON" --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$ICON" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o "$TMP/$NAME.app/Contents/Resources/AppIcon.icns"

cat > "$TMP/$NAME.app/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIdentifier</key><string>$BID</string>
  <key>ScanStudioPort</key><string>$PORT</string>
  <key>ScanStudioDev</key><string>${DEV:-}</string>
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
  <key>UTExportedTypeDeclarations</key><array><dict>
    <key>UTTypeIdentifier</key><string>io.github.aallevi.scanstudio.doculib</string>
    <key>UTTypeDescription</key><string>Scan Studio Library</string>
    <key>UTTypeConformsTo</key><array><string>com.apple.package</string><string>public.composite-content</string></array>
    <key>UTTypeIconFile</key><string>AppIcon</string>
    <key>UTTypeTagSpecification</key><dict><key>public.filename-extension</key><array><string>doculib</string></array></dict>
  </dict></array>
  <key>CFBundleDocumentTypes</key><array><dict>
    <key>CFBundleTypeName</key><string>Scan Studio Library</string>
    <key>CFBundleTypeRole</key><string>Viewer</string>
    <key>LSHandlerRank</key><string>Owner</string>
    <key>LSTypeIsPackage</key><true/>
    <key>CFBundleTypeIconFile</key><string>AppIcon</string>
    <key>LSItemContentTypes</key><array><string>io.github.aallevi.scanstudio.doculib</string></array>
  </dict></array>
</dict></plist>
EOF

codesign --force --sign - "$TMP/$NAME.app"
# la vecchia si toglie solo quando la nuova e' pronta (stesso posto: il Dock la ritrova)
mkdir -p "${APP:h}"
rm -rf "$APP"
mv "$TMP/$NAME.app" "$APP"
rm -rf "$TMP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP"
echo "built $APP ($VERSION, $PYTHON, scans in $SCANS_ROOT)"
