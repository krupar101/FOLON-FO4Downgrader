"""Delete only manifest-listed depot files from recognized download roots."""
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


def download_roots(request):
    """Recognized depot locations; no transaction is needed for interrupted downloads."""
    from .steamcmd import SteamCmdProvider

    if request.content:
        return [request.content]
    return [request.staging / 'content', *SteamCmdProvider(request.steamcmd).candidate_roots()]


def cleanup_candidates(request, manifest):
    """Prevalidate all roots and manifest-listed files before reporting or deletion."""
    roots = []
    for root in download_roots(request):
        root = Path(root)
        if not root.is_dir():
            continue
        # Canonicalized roots are supplied by Request; no cleanup may overlap
        # the installed game or any of the application's other state roots.
        base = root.resolve()
        if any(base.is_relative_to(p.resolve()) or p.resolve().is_relative_to(base)
               for p in (request.game, request.state)):
            continue
        if base == request.steamcmd.resolve() or request.steamcmd.resolve().is_relative_to(base):
            continue
        files = []
        for depot in manifest.depots:
            for spec in depot['files']:
                file = inside(root, f"depot_{depot['id']}/{spec['path']}")
                if file.exists():
                    if not file.is_file():
                        fail('UNSAFE_PATH', 'A downloaded file path is not a regular file.')
                    files.append(file)
        if files:
            roots.append((root, files))
    return roots


def removable_downloads(request):
    """Read-only count of known depot files, including unfinished downloads.

    No successful deployment transaction is required. Only expected manifest
    paths count; unknown content isn't claimed as removable.
    """
    from .manifest import Manifest

    try:
        manifest = Manifest(request.manifest)
        manifest.require_inventory()
        roots = cleanup_candidates(request, manifest)
        return {'bytes': sum(p.stat().st_size for _, files in roots for p in files),
                'files': sum(len(files) for _, files in roots)}
    except (OSError, ValueError, TypeError, KeyError, DowngradeError):
        return {'bytes': 0, 'files': 0}
