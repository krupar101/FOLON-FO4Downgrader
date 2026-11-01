"""Exercise bundled imports/Qt startup without a Steam account or game files."""
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
if sys.platform == 'win32':
    cli = [str(root / 'dist/Downgrader-2.0/Downgrader-2.0-cli.exe')]
    gui = [str(root / 'dist/Downgrader-2.0/Downgrader-2.0.exe')]
else:
    cli = gui = [str(root / 'dist/Downgrader-2.0-x86_64.AppImage'), '--appimage-extract-and-run']
subprocess.run([*cli, '--help'], check=True, timeout=60)
result = subprocess.run([*cli, '--check-inventory'], check=True, timeout=60, capture_output=True, text=True)
inventory = json.loads(result.stdout)
assert inventory == {'version': '2.0.0', 'files': 90, 'inventory_complete': True}, inventory
print('Packaged 2.0.0 inventory is complete: 90 selected files.')
with tempfile.TemporaryDirectory() as cwd, tempfile.TemporaryFile() as log:
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    process = subprocess.Popen([*gui, '--gui'], cwd=cwd, env=env, stdout=log, stderr=log)
    try:
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            print('Packaged GUI stayed running for the startup smoke test.')
        else:
            log.seek(0)
            sys.stderr.write(log.read().decode(errors='replace'))
            raise SystemExit(f'GUI exited prematurely: {process.returncode}')
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
