"""Block Steam from updating Fallout 4 by locking its app manifest.

Windows: read-only attribute (attrib +R). Linux: immutable flag (chattr +i via
polkit). Every change is verified by re-reading the attribute afterwards, and
status is None ("unknown") whenever it cannot be determined.
"""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

APP_ID = '377160'
MANIFEST_NAME = f'appmanifest_{APP_ID}.acf'


def manifest_path(game):
    """The Steam manifest of the library that holds this installation, or None."""
    try:
        game = Path(game)
        if game.parent.name.lower() != 'common':
            return None
        manifest = game.parent.parent / MANIFEST_NAME
        return manifest if manifest.is_file() else None
    except (OSError, ValueError, TypeError):
        return None


def status(manifest):
    """True: updates disabled. False: enabled. None: unknown."""
    if manifest is None:
        return None
    manifest = Path(manifest)
    try:
        if sys.platform == 'win32':
            return bool(os.stat(manifest).st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
        result = subprocess.run(['lsattr', '-d', str(manifest)], capture_output=True, text=True, timeout=15)
        fields = result.stdout.split()
        if result.returncode != 0 or not fields:
            return None  # e.g. filesystem without attribute support
        return 'i' in fields[0]
    except (OSError, AttributeError, subprocess.SubprocessError):
        return None


def requires_authentication():
    return sys.platform != 'win32'


def set_disabled(manifest, disabled):
    """Apply the change, then verify it. Returns (ok, message)."""
    if manifest is None:
        return False, 'The Fallout 4 Steam manifest (appmanifest_377160.acf) could not be found.'
    manifest = str(manifest)
    if sys.platform == 'win32':
        command = ['attrib', '+R' if disabled else '-R', manifest]
    else:
        pkexec = shutil.which('pkexec')
        if not pkexec:
            flag = '+i' if disabled else '-i'
            return False, (f'pkexec (polkit) was not found. Run this in a terminal instead:\n'
                           f'sudo chattr {flag} "{manifest}"')
        command = [pkexec, 'chattr', '+i' if disabled else '-i', manifest]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as error:
        return False, f'Could not run the command: {error}'
    if result.returncode != 0:
        if sys.platform != 'win32' and result.returncode in (126, 127):
            return False, 'Authentication was cancelled or denied. No changes were made.'
        detail = (result.stderr or result.stdout or '').strip()
        return False, detail or 'The command failed.'
    if status(manifest) is not disabled:
        return False, ('The change was not applied. The filesystem may not support it'
                       if sys.platform != 'win32' else 'The change was not applied.')
    return True, ''
