"""Reject accidentally publishing old PyInstaller one-folder build artifacts."""
from pathlib import Path
import sys

if sys.platform != 'win32':
    raise SystemExit('Windows build verification must run on Windows.')

root = Path(__file__).resolve().parent.parent
folder = root / 'dist'
expected = [folder / 'Downgrader-2.0.exe', folder / 'Downgrader-2.0-cli.exe']
for executable in expected:
    if not executable.is_file() or executable.stat().st_size == 0:
        raise SystemExit(f'ERROR: Missing or empty one-file EXE: {executable}')

unexpected = [item.name for item in folder.iterdir() if item.is_dir()]
if unexpected:
    raise SystemExit(f'ERROR: dist contains folders (possible one-folder build): {unexpected}')

print('Verified: two EXE files and no external dependency folders in dist.')
