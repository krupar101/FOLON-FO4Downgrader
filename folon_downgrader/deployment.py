"""Verified atomic file replacement with a small retry journal; no game backups."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .errors import fail
from .files import atomic_json, inside, sync_dir


def copy_replace(source, target, spec):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.folon-copy-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
            hasher = hashlib.sha256()
            size = 0
            while chunk := inp.read(1024 * 1024):
                out.write(chunk)
                hasher.update(chunk)
                size += len(chunk)
            if size != spec['size'] or hasher.hexdigest() != spec['sha256']:
                fail('HASH_MISMATCH', 'A source file changed or does not match the trusted inventory.')
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
        sync_dir(target.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Transaction:
    def __init__(self, game, state):
        self.game = Path(game).resolve()
        self.state = Path(state).resolve()
        inside(self.game, '.boundary-check')
        inside(self.state, '.boundary-check')
        if self.game.is_relative_to(self.state) or self.state.is_relative_to(self.game):
            fail('PATH_CONFLICT', 'Transaction storage must be separate from the game directory.')
        self.path = inside(self.state, 'transaction.json')
        self.journal = None

    def save(self):
        atomic_json(self.path, self.journal)

    def load(self):
        try:
            self.journal = json.loads(self.path.read_text(encoding='utf-8'))
            if self.journal['schema'] != 2 or self.journal['game'] != str(self.game):
                raise ValueError()
        except (ValueError, TypeError, KeyError, OSError):
            fail('JOURNAL_INVALID', 'Cannot read a valid transaction record for this game root.')
        return self.journal

    def prepare(self, files, remove, manifest_hash, cancel=lambda: None):
        entries = []
        growth = 0
        largest = 0
        for name in sorted(set(files) | set(remove)):
            cancel()
            target = inside(self.game, name)
            for parent in target.parents:
                if parent == self.game:
                    break
                if parent.exists() and not parent.is_dir():
                    fail('PATH_CONFLICT', 'A destination parent is not a directory.')
            if target.exists() and not target.is_file():
                fail('PATH_CONFLICT', 'A destination is not a regular file.')
            spec = files[name][1] if name in files else None
            if spec:
                growth += max(0, spec['size'] - (target.stat().st_size if target.exists() else 0))
                largest = max(largest, spec['size'])
            entries.append({'name': name, 'action': 'install' if spec else 'remove', 'state': 'planned'})
        if shutil.disk_usage(self.game).free < growth + largest:
            fail('INSUFFICIENT_SPACE', 'Insufficient space for installation growth and a temporary replacement file.')
        self.journal = {'schema': 2, 'game': str(self.game), 'manifest': manifest_hash,
                        'status': 'prepared', 'entries': entries}
        self.save()

    def commit(self, files, cancel=lambda: None):
        if self.journal is None or self.journal['status'] != 'prepared':
            fail('JOURNAL_INVALID', 'Deployment requires a prepared transaction.')
        self.journal['status'] = 'deploying'
        self.save()
        for entry in self.journal['entries']:
            cancel()
            target = inside(self.game, entry['name'])
            entry['state'] = 'writing'
            self.save()
            if entry['action'] == 'install':
                source, spec = files[entry['name']]
                copy_replace(source, target, spec)
            elif target.exists():
                target.unlink()
                sync_dir(target.parent)
            entry['state'] = 'written'
            self.save()
        self.journal['status'] = 'awaiting_verification'
        self.save()

    def complete(self, report):
        atomic_json(inside(self.state, 'verification.json'), report)
        self.journal['status'] = 'complete'
        self.save()
