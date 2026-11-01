"""Delete only release-listed downloads; leave unrelated content untouched."""
from pathlib import Path

from .errors import fail
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
