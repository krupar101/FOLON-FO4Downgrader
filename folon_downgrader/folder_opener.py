"""Open a directory with the host desktop, including from a frozen AppImage.

Linux desktop launchers must not inherit PyInstaller/AppImage library and Qt
plugin overrides; doing so can make the host file manager fail to start.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys


_RUNTIME_OVERRIDES = (
    'LD_LIBRARY_PATH', 'LD_PRELOAD', 'QT_PLUGIN_PATH',
    'QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_QPA_FONTDIR',
    'PYTHONHOME', 'PYTHONPATH', 'GIO_EXTRA_MODULES', 'GI_TYPELIB_PATH',
)


def desktop_environment(environ=None):
    env = dict(os.environ if environ is None else environ)
    for key in _RUNTIME_OVERRIDES:
        original = env.pop(key + '_ORIG', None)
        env.pop(key, None)
        if original is not None:
            env[key] = original
    # AppImage often prepends a temporary mounted tree to XDG_DATA_DIRS.
    # The host desktop should use its own installed desktop entries instead.
    if env.get('APPIMAGE') or env.get('APPDIR'):
        env['XDG_DATA_DIRS'] = '/usr/local/share:/usr/share'
    return env


def open_linux_folder(path, *, launch=subprocess.Popen, which=shutil.which):
    """Start the system folder opener; return whether a launcher was started."""
    folder = Path(path)
    if not folder.is_dir():
        return False
    env = desktop_environment()
    for command in ('xdg-open', 'gio'):
        executable = which(command)
        if executable is None:
            continue
        argv = [executable, str(folder)] if command == 'xdg-open' else [executable, 'open', str(folder)]
        try:
            launch(argv, env=env, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   start_new_session=True)
            return True
        except OSError:
            continue
    return False
