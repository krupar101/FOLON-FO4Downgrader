"""Persistent GUI preference for the managed SteamCMD / depot download root.

CLI --steamcmd-root always overrides this preference.
"""
import json
from pathlib import Path

from .platforms import data_root
from .files import atomic_json


def preference_file():
    return data_root() / 'storage-settings.json'


def load_download_root():
    try:
        saved = json.loads(preference_file().read_text(encoding='utf-8'))
        # Accept existing unversioned preferences when upgrading.
        if not isinstance(saved, dict) or saved.get('schema', 1) != 1:
            return data_root() / 'steamcmd'
        value = saved.get('steamcmd_root')
        if isinstance(value, str) and value and Path(value).is_absolute():
            return Path(value)
    except (OSError, ValueError, TypeError):
        pass
    return data_root() / 'steamcmd'


def save_download_root(path):
    path = Path(path).expanduser().absolute()
    config = preference_file()
    atomic_json(config, {'schema': 1, 'steamcmd_root': str(path)})
    return path
