#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
: "${APPIMAGETOOL:?Set APPIMAGETOOL to a locally verified appimagetool executable}"
: "${APPIMAGETOOL_SHA256:?Set the pinned SHA256 of that executable}"
printf '%s  %s\n' "$APPIMAGETOOL_SHA256" "$APPIMAGETOOL" | sha256sum --check --status
: "${APPIMAGE_RUNTIME:?Set APPIMAGE_RUNTIME to the reviewed type2 runtime}"
: "${APPIMAGE_RUNTIME_SHA256:?Set its pinned SHA256}"
printf '%s  %s\n' "$APPIMAGE_RUNTIME_SHA256" "$APPIMAGE_RUNTIME" | sha256sum --check --status
python -m PyInstaller --clean -y FOLON-Downgrader.spec
appdir="$(mktemp -d "$PWD/build/FOLON.AppDir.XXXXXX")"
chmod 755 "$appdir"
mkdir -p "$appdir/usr"
cp -a dist/Downgrader-2.0/. "$appdir/usr/"
cp packaging/linux/folon-downgrader.desktop "$appdir/"
cp img/FOLON256.png "$appdir/folon-downgrader.png"
cat > "$appdir/AppRun" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
appdir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$appdir/usr/Downgrader-2.0" "$@"
RUN
chmod +x "$appdir/AppRun"
outputdir="$(mktemp -d "$PWD/dist/.appimage-build.XXXXXX")"
trap 'rm -rf -- "$outputdir"' EXIT
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run --runtime-file "$APPIMAGE_RUNTIME" "$appdir" "$outputdir/Downgrader-2.0-x86_64.AppImage"
mv -f -- "$outputdir/Downgrader-2.0-x86_64.AppImage" dist/Downgrader-2.0-x86_64.AppImage
sha256sum dist/Downgrader-2.0-x86_64.AppImage > dist/Downgrader-2.0-x86_64.AppImage.sha256
