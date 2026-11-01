"""Conservative filesystem primitives shared by verification and deployment."""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import tempfile

from .errors import fail


def relative_name(name):
    if not isinstance(name, str) or not name or '\\' in name:
        fail('UNSAFE_PATH', 'Manifest paths must be nonempty relative POSIX paths.')
    parts = name.split('/')
    if any(p in ('', '.', '..') or any(ord(c) < 32 or c in ':*?<>|\"' for c in p) or p.endswith((' ', '.')) for p in parts):
        fail('UNSAFE_PATH', 'Invalid path component.')
    if PureWindowsPath(name).is_absolute() or any(re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?', p) for p in parts):
        fail('UNSAFE_PATH', 'Absolute and reserved paths are not permitted.')
    return parts


def is_link(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def inside(root, name):
    root = Path(root)
    parts = relative_name(name)
    # The user-selected root may be reached through a Wine drive mapping,
    # mount point, or directory alias. Resolve it as the trust boundary;
    # inspecting its ancestors would reject Wine Z: even for safe files.
    resolved_root = root.resolve()
    current = root
    for component in parts:
        current /= component
        if is_link(current):
            fail('UNSAFE_PATH', 'A file path contains a symlink or junction.')
    if not current.resolve().is_relative_to(resolved_root):
        fail('UNSAFE_PATH', 'A file escapes its managed directory.')
    return current


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.folon-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def sync_dir(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class Lock:
    """OS-held lock: process death releases it; the lock file is never unlinked."""
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if is_link(self.path):
            fail('UNSAFE_PATH', 'Lock file is a link.')
        self.stream = self.path.open('a+b')
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                if self.path.stat().st_size == 0:
                    self.stream.write(b'0')
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            fail('ALREADY_RUNNING', 'Another operation holds this installation lock.')
        return self

    def __exit__(self, *args):
        self.stream.close()
