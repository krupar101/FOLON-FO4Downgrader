# Native development builds

Build Windows on Windows and Linux on Linux. Python 3.12 is the CI baseline.
Both builds bundle the same FOLON Qt pages and launch the GUI by default; CLI flags
remain available for diagnostics. Artifacts are development previews until the
release gates in `docs/validation.md` pass.

Windows: run `Build.bat`. Distribute the **whole** `dist/FOLON-Downgrader` directory,
not just its `.exe`. The default executable uses a windowed bootloader;
`FOLON-Downgrader-cli.exe` provides optional console diagnostics.

Linux:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
export APPIMAGETOOL=/absolute/path/to/appimagetool-x86_64.AppImage
export APPIMAGETOOL_SHA256=ac7fd56feade6002c2f57db39587113275d351fce911a5fbb29ea84cd0666cab
export APPIMAGE_RUNTIME=/absolute/path/to/runtime-x86_64
export APPIMAGE_RUNTIME_SHA256=617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46
packaging/linux/build-appimage.sh
```

The tool URL/release and digest are recorded in `docs/source-audit.md`. Obtain that
exact official asset; checksum mismatches must stop the build. No automatic
latest-tool execution is allowed. Result: `dist/FOLON-Downgrader-x86_64.AppImage`
and its SHA-256 file. The GUI is the default even when opened from a file manager.

CI runs tests and produces native one-folder builds. The Linux job also produces
an AppImage using the reviewed tool digest. It uploads development artifacts only;
it does not publish GitHub Releases. Dependencies have explicit runtime versions;
full transitive hash locks, action SHA pinning, reproducible build provenance and
Windows signing remain release-hardening work, not completed claims.
