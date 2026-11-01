# Native Windows/Linux builds. Windows uses standalone one-file EXEs; the
# Linux AppImage pipeline continues to consume a one-folder staging build.
import sys
from PyInstaller.utils.hooks import collect_data_files

is_windows = sys.platform == 'win32'
a = Analysis(
    ['FOLON-Downgrader.py'], pathex=[], binaries=[],
    datas=collect_data_files('certifi') + [('FOLON.css', '.'), ('img/FOLON256.png', 'img'),
           ('img/FOLONBackground.png', 'img'), ('img/check.svg', 'img'),
           ('img/folder.svg', 'img'), ('img/alert.svg', 'img'),
           ('manifests/fo4-1.10.163.0-en.json', 'manifests'), ('LICENSE', '.')],
    hiddenimports=['folon_downgrader.qt'], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)

if is_windows:
    # Including binaries and datas in EXE (and omitting COLLECT) tells
    # PyInstaller to embed everything in the standalone executable.
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
              name='Downgrader-2.0', debug=False, strip=False, upx=False,
              console=False, icon='img/FOLON256.ico')
    # Optional, independently standalone console build for diagnostics/CI.
    cli_exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
                  name='Downgrader-2.0-cli', debug=False, strip=False,
                  upx=False, console=True, icon='img/FOLON256.ico')
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
              name='Downgrader-2.0', debug=False, strip=False, upx=False,
              console=True)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                   name='Downgrader-2.0')
