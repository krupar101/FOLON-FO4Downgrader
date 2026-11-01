import os
from pathlib import Path
import platform
import re
import sys

from .errors import fail


def host():
    if sys.platform not in ('win32', 'linux') or platform.machine().lower() not in ('amd64', 'x86_64'):
        fail('UNSUPPORTED_PLATFORM', 'Supported hosts are Windows x64 and Linux x86-64.')
    return 'windows' if sys.platform == 'win32' else 'linux'


def data_root():
    if host() == 'windows':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'FOLON-Downgrader'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'folon-downgrader'


def steam_roots():
    roots = []
    if host() == 'windows':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
                roots.append(Path(winreg.QueryValueEx(key, 'SteamPath')[0]))
        except OSError:
            pass
        for name in ('ProgramFiles(x86)', 'ProgramFiles'):
            if name in os.environ:
                roots.append(Path(os.environ[name]) / 'Steam')
    else:
        roots += [Path.home() / p for p in ('.steam/steam', '.local/share/Steam',
                  '.var/app/com.valvesoftware.Steam/.local/share/Steam')]
    return list(dict.fromkeys(p.resolve() for p in roots if p.is_dir()))


def vdf_pairs(text):
    # Steam's quoted scalar strings, including escaped backslashes/quotes.
    token = r'"((?:\\.|[^"\\])*)"'
    def unescape(s):
        return re.sub(r'\\([\\"])', r'\1', s)
    return [(unescape(a), unescape(b)) for a, b in re.findall(token + r'\s*' + token, text)]


def discover(roots=None):
    libraries = list(steam_roots() if roots is None else roots)
    for root in list(libraries):
        file = root / 'steamapps/libraryfolders.vdf'
        if file.is_file():
            for key, value in vdf_pairs(file.read_text(encoding='utf-8', errors='replace')):
                if key == 'path' or (key.isdigit() and (value.startswith('/') or ':\\' in value)):
                    libraries.append(Path(value))
    found = []
    for library in libraries:
        app = library / 'steamapps/appmanifest_377160.acf'
        if not app.is_file():
            continue
        pairs = dict(vdf_pairs(app.read_text(encoding='utf-8', errors='replace')))
        install = pairs.get('installdir', '')
        if pairs.get('appid') != '377160' or not install or '/' in install or '\\' in install or install in ('.', '..'):
            continue
        game = (library / 'steamapps/common' / install).resolve()
        if (game / 'Fallout4.exe').is_file():
            found.append(game)
    return list(dict.fromkeys(found))


def check_not_running():
    try:
        import psutil
    except ImportError:
        fail('DEPENDENCY_MISSING', 'Install the pinned dependencies to check running game processes.')
    for process in psutil.process_iter(['name']):
        try:
            name = (process.info['name'] or '').lower()
            if name in ('fallout4.exe', 'fallout4launcher.exe', 'f4se_loader.exe'):
                fail('GAME_RUNNING', 'Close Fallout 4, its launcher and F4SE before deployment.')
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def steam_processes():
    import psutil
    return [p for p in psutil.process_iter(['name'])
            if (p.info['name'] or '').lower() in ('steam', 'steam.exe')]


def shutdown_steam(cancel=lambda: None):
    """Request Steam's normal shutdown, never force-kill it."""
    import subprocess
    import time
    import psutil
    processes = steam_processes()
    if not processes:
        return
    try:
        executable = processes[0].exe()
        subprocess.Popen([executable, '-shutdown'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 30
        while steam_processes():
            cancel()
            if time.monotonic() >= deadline:
                fail('STEAM_RUNNING', 'Steam did not exit. Close Steam and retry the downgrade.')
            time.sleep(0.2)
    except (OSError, psutil.Error):
        fail('STEAM_RUNNING', 'Could not request Steam shutdown. Close Steam and retry the downgrade.')
