"""Persistent GUI preference for the managed SteamCMD / depot download root.

CLI --steamcmd-root always overrides this preference.
"""
import json
from pathlib import Path

from .platforms import data_root


def preference_file():
    return data_root() / 'storage-settings.json'


def load_download_root():
    try:
        saved = json.loads(preference_file().read_text(encoding='utf-8'))
        value = saved.get('steamcmd_root')
        if isinstance(value, str) and value and Path(value).is_absolute():
            return Path(value)
    except (OSError, ValueError, TypeError):
        pass
    return data_root() / 'steamcmd'


def save_download_root(path):
    path = Path(path).expanduser().absolute()
    config = preference_file()
    config.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps({'steamcmd_root': str(path)}, indent=2), encoding='utf-8')
        temporary.replace(config)
    finally:
        temporary.unlink(missing_ok=True)
    return path
