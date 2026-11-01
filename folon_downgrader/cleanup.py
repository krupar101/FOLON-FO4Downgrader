"""Delete only release-listed downloads; leave unrelated content untouched."""
from pathlib import Path

from .errors import DowngradeError, fail
from .files import inside


def remove_downloads(root, manifest, protected, cancel=lambda: None):
    root = Path(root)
    inside(root, '.boundary-check')
    for path in protected:
        path = Path(path).resolve()
        if root.resolve().is_relative_to(path) or path.is_relative_to(root.resolve()):
            fail('PATH_CONFLICT', 'Download cleanup cannot overlap installation or transaction files.')
    # Validate the entire deletion list before removing anything. Never rmtree a
    # user-selected directory or follow links within a depot.
    files = []
    directories = set()
    for depot in manifest.depots:
        for spec in depot['files']:
            path = inside(root, f"depot_{depot['id']}/{spec['path']}")
            if path.exists():
                if not path.is_file():
                    fail('UNSAFE_PATH', 'A downloaded file path is no longer a regular file.')
                files.append(path)
            parent = path.parent
            while parent != root:
                directories.add(parent)
                parent = parent.parent
    removed = 0
    size = 0
    for path in files:
        cancel()
        # Repeat link/boundary checks immediately before unlinking.
        path = inside(root, path.relative_to(root).as_posix())
        if path.exists():
            size += path.stat().st_size
            path.unlink()
            removed += 1
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()  # Only empty directories; unknown files are retained.
        except OSError:
            pass
    return {'files_removed': removed, 'bytes_removed': size}


def removable_downloads(request):
    """Read-only estimate for the exact files the verified cleanup action may remove.

    Never count arbitrary files in the SteamCMD directory or the installed game.
    A matching completed transaction is required, just as for actual cleanup.
    """
    import json
    from .manifest import Manifest
    from .steamcmd import SteamCmdProvider

    try:
        manifest = Manifest(request.manifest)
        manifest.require_inventory()
        state = json.loads(inside(request.state, 'transaction.json').read_text(encoding='utf-8'))
        if (state.get('schema') != 2 or state.get('game') != str(request.game)
                or state.get('status') != 'complete' or state.get('manifest') != manifest.sha256):
            return {'bytes': 0, 'files': 0}
        root = Path(state.get('download_root', ''))
        allowed = ([request.content] if request.content else
                   [request.staging / 'content', *SteamCmdProvider(request.steamcmd).candidate_roots()])
        if root not in allowed or not root.is_dir():
            return {'bytes': 0, 'files': 0}
        # Do not turn the home-screen status check into an unsafe traversal.
        if root.resolve().is_relative_to(request.game) or request.game.is_relative_to(root.resolve()):
            return {'bytes': 0, 'files': 0}
        total = count = 0
        for depot in manifest.depots:
            for spec in depot['files']:
                file = inside(root, f"depot_{depot['id']}/{spec['path']}")
                if file.is_file():
                    total += file.stat().st_size
                    count += 1
        return {'bytes': total, 'files': count}
    except (OSError, ValueError, TypeError, KeyError, DowngradeError):
        return {'bytes': 0, 'files': 0}
