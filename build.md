# Native development builds

Build Windows on Windows and Linux on Linux. Python 3.12 is the CI baseline.
Both builds bundle the same FOLON Qt pages and launch the GUI by default; CLI flags
remain available for diagnostics. Artifacts are development previews until the
platform checks below pass.

Windows: run `Build.bat` from the extracted source directory. The script deletes
old `dist` and `build` directories before rebuilding, then checks the resulting
EXEs and runs a startup smoke test. **Do not launch an old executable copied
elsewhere:** use the newly generated `dist/Downgrader-2.0.exe`. The standalone, windowed GUI executable is
`dist/Downgrader-2.0.exe`: **distribute that single file**. No `_internal`
folder, Python installation, or additional shipped files are needed. For
console diagnostics, `dist/Downgrader-2.0-cli.exe` is also independently
standalone; it is optional and does not need to accompany the GUI executable.
PyInstaller's one-file bootloader temporarily extracts bundled files into a
system temporary directory at runtime; it does not require files beside the EXE.
The user still needs Windows, and the downgrader's normal Steam/game prerequisites.

Linux:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
export APPIMAGETOOL=/absolute/path/to/appimagetool-x86_64.AppImage
export APPIMAGETOOL_SHA256=ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0
export APPIMAGE_RUNTIME=/absolute/path/to/runtime-x86_64
export APPIMAGE_RUNTIME_SHA256=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d
packaging/linux/build-appimage.sh
```

The tool URL/release and digest are recorded in `docs/source-audit.md`. Obtain that
exact official asset; checksum mismatches must stop the build. No automatic
latest-tool execution is allowed. Result: `dist/Downgrader-2.0-x86_64.AppImage`
and its SHA-256 file. The GUI is the default even when opened from a file manager.

CI runs tests and produces standalone Windows executables and a Linux staging folder. The Linux job also produces
an AppImage using the reviewed tool digest. It uploads development artifacts only;
it does not publish GitHub Releases. Dependencies have explicit runtime versions;
full transitive hash locks, reproducible build provenance and
Windows signing remain release-hardening work, not completed claims.

## Testing status

Synthetic tests cover verification, deployment interruptions, selective cleanup,
SteamCMD prompts, and GUI navigation. CI runs them on Windows and Linux and checks
packaged startup. These checks do not establish that the downgraded game launches.

Linux testing recorded authenticated downloads of all 14 depots and a disposable
installation with 90 installed files verified by SHA-256 and executable version
1.10.163.0. The current engine keeps a retry journal and does not create backups
or offer rollback. Earlier rollback experiments describe a superseded implementation.

Before release, exercise real Steam Guard flows, interrupted downloads/deployment,
and game launch on Windows, Linux/Proton and Steam Deck (internal and microSD
storage). Review Windows junction handling and SteamCMD-owned logs/session files.
