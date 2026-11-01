"""Release contract. Missing trusted metadata is never inferred from downloaded bytes."""
import hashlib
import json
from pathlib import Path
import re
import struct

from .errors import fail
from .files import digest, inside, relative_name


class Manifest:
    def __init__(self, path):
        try:
            raw = Path(path).read_bytes()
            self.data = json.loads(raw)
            self.sha256 = hashlib.sha256(raw).hexdigest()
            d = self.data
            if d['schema'] != 1 or d['steam_app_id'] != 377160:
                raise ValueError()
            if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', d['target_exe_version']):
                raise ValueError()
            if not d['depots'] or len({x['id'] for x in d['depots']}) != len(d['depots']):
                raise ValueError()
            for depot in d['depots']:
                if not re.fullmatch(r'\d+', str(depot['id'])) or not re.fullmatch(r'\d+', str(depot['manifest'])):
                    raise ValueError()
                names = set()
                for f in depot['files']:
                    relative_name(f['path'])
                    if f['path'].casefold() in names:
                        raise ValueError()
                    names.add(f['path'].casefold())
                    if type(f['size']) is not int or f['size'] < 0 or not re.fullmatch('[a-f0-9]{64}', f['sha256']):
                        raise ValueError()
            for name in d.get('remove', []) + d.get('exclude', []):
                relative_name(name)
        except (KeyError, TypeError, ValueError, OSError):
            fail('MANIFEST_INVALID', 'Cannot read a valid release manifest.')

    @property
    def depots(self):
        return self.data['depots']

    def require_inventory(self):
        if self.data.get('inventory_complete') is not True or any(not d['files'] for d in self.depots):
            fail('MANIFEST_UNVERIFIED', 'This release has no complete trusted file inventory. Deployment is disabled.')
        if not any(f['path'] == 'Fallout4.exe' for d in self.depots for f in d['files']):
            fail('MANIFEST_INVALID', 'The target executable must be included in the release inventory.')
        # Conflicting depot files need an explicit owner, never filesystem iteration order.
        owners = self.data.get('overrides', {})
        seen = {}
        for depot in self.depots:
            for f in depot['files']:
                key = f['path'].casefold()
                if key in seen and seen[key][0] != f['path']:
                    fail('MANIFEST_CONFLICT', 'Depot paths differ only by case.')
                if key in seen and seen[key] != (f['path'], f['sha256']):
                    if owners.get(f['path']) not in [d['id'] for d in self.depots if any(x['path'] == f['path'] for x in d['files'])]:
                        fail('MANIFEST_CONFLICT', 'Conflicting depot files need an explicit override.')
                seen[key] = (f['path'], f['sha256'])
        for name, owner in owners.items():
            if not any(d['id'] == owner and any(f['path'] == name for f in d['files']) for d in self.depots):
                fail('MANIFEST_CONFLICT', 'An override does not identify a file in its owning depot.')
        for name in seen:
            parts = name.split('/')
            if any('/'.join(parts[:i]) in seen for i in range(1, len(parts))):
                fail('MANIFEST_CONFLICT', 'A release file is also a parent directory.')
        excluded = self.data.get('exclude', [])
        if 'fallout4.exe' in {name.casefold() for name in excluded}:
            fail('MANIFEST_INVALID', 'The target executable cannot be excluded from deployment.')
        if any(name.casefold() not in seen or seen[name.casefold()][0] != name for name in excluded):
            fail('MANIFEST_INVALID', 'Excluded files must exactly identify verified depot files.')
        installed = {name.casefold() for name in self.selected_files()}
        if any(name.casefold() in installed for name in self.data.get('remove', [])):
            fail('MANIFEST_CONFLICT', 'A release cannot install and remove the same file.')

    def selected_files(self):
        selected = {}
        owners = self.data.get('overrides', {})
        for depot in self.depots:
            for f in depot['files']:
                if f['path'] in self.data.get('exclude', []):
                    continue
                if f['path'] not in owners or owners[f['path']] == depot['id']:
                    selected[f['path']] = (depot['id'], f)
        return selected


def verify_file(path, spec):
    if not path.is_file():
        fail('DEPOT_INCOMPLETE', 'A required file is absent.')
    if path.stat().st_size != spec['size'] or digest(path) != spec['sha256']:
        fail('HASH_MISMATCH', 'A required file does not match the trusted release inventory.')


def verify_depots(root, manifest, cancel=lambda: None, cache=None):
    manifest.require_inventory()
    root = Path(root)
    if not root.is_dir():
        fail('DEPOT_TREE_MISSING', 'SteamCMD did not produce the required content directory. Retry the download.')
    for depot in manifest.depots:
        base = inside(root, f"depot_{depot['id']}")
        for spec in depot['files']:
            cancel()
            path = inside(base, spec['path'])
            stat = path.stat() if path.is_file() else None
            stamp = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) if stat else None
            key = (str(path.absolute()), spec['sha256'])
            if cache is None or stamp is None or cache.get(key) != stamp:
                verify_file(path, spec)
                after = path.stat()
                if stamp != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    fail('SOURCE_CHANGED', 'A downloaded file changed during verification.')
                if cache is not None:
                    cache[key] = stamp
    return {name: (inside(root, f'depot_{depot}/{name}'), spec)
            for name, (depot, spec) in manifest.selected_files().items()}


def executable_version(path):
    """Read PE version resource using pefile on either host OS (never execute the game)."""
    try:
        import pefile
        with pefile.PE(str(path), fast_load=True) as pe:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
            info = pe.VS_FIXEDFILEINFO[0]
            return '.'.join(str(x) for x in (info.FileVersionMS >> 16, info.FileVersionMS & 65535,
                                             info.FileVersionLS >> 16, info.FileVersionLS & 65535))
    except (ImportError, OSError, AttributeError, IndexError, ValueError, struct.error):
        fail('WRONG_GAME_BUILD', 'Cannot read the Fallout4.exe PE version. Install the pinned dependencies and select a valid game.')
    except Exception:
        fail('WRONG_GAME_BUILD', 'Fallout4.exe does not contain a readable PE version resource.')


def verify_target(root, manifest):
    for name, (_, spec) in manifest.selected_files().items():
        verify_file(inside(root, name), spec)
    for name in manifest.data.get('remove', []):
        if inside(root, name).exists():
            fail('TARGET_VERIFY_FAILED', 'An explicitly removed release file is still present.')
    if executable_version(inside(root, 'Fallout4.exe')) != manifest.data['target_exe_version']:
        fail('TARGET_VERIFY_FAILED', 'The installed executable version does not match the selected release.')
