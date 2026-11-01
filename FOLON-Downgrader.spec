# Native Windows/Linux builds. Both ship the same GUI and optional CLI.
import sys

a = Analysis(
    ['FOLON-Downgrader.py'], pathex=[], binaries=[],
    datas=[('FOLON.css', '.'), ('img/FOLON256.png', 'img'),
           ('img/FOLONBackground.png', 'img'), ('img/check.svg', 'img'),
           ('img/folder.svg', 'img'), ('img/alert.svg', 'img'), ('manifests/fo4-1.10.163.0-en.json', 'manifests'), ('LICENSE', '.')],
    hiddenimports=['folon_downgrader.qt'], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Downgrader-2.0',
          debug=False, strip=False, upx=False, console=sys.platform != 'win32',
          icon='img/FOLON256.ico' if sys.platform == 'win32' else None)
executables = [exe]
if sys.platform == 'win32':
    executables.append(EXE(pyz, a.scripts, [], exclude_binaries=True,
        name='Downgrader-2.0-cli', debug=False, strip=False, upx=False, console=True,
        icon='img/FOLON256.ico'))
coll = COLLECT(*executables, a.binaries, a.datas, strip=False, upx=False, name='Downgrader-2.0')
