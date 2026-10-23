#!/bin/bash
# creer_app_mac.sh — (re)construit « CT-CORA3D.app » à partir de lanceur_mac.applescript et de l'icône.
# Usage : bash creer_app_mac.sh   (depuis n'importe où)
set -e
ICI="$(cd "$(dirname "$0")" && pwd)"
APP="$ICI/../../CT-CORA3D.app"
rm -rf "$APP"
osacompile -o "$APP" "$ICI/lanceur_mac.applescript"
cp "$ICI/../icone/icone.icns" "$APP/Contents/Resources/applet.icns"
rm -f "$APP/Contents/Resources/Assets.car"            # sinon l'icône AppleScript par défaut l'emporte
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleName CT-CORA3D" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string be.ecam.pmd2.ctcora3d" "$APP/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier be.ecam.pmd2.ctcora3d" "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP" 2>/dev/null || true   # signature locale (ad hoc)
touch "$APP"
chmod +x "$ICI/../lancer_mac.sh"
echo "OK : $APP"
