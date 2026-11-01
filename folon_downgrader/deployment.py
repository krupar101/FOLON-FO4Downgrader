"""Copy, verify, journal, replace. Backups survive success, failure and process death."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .errors import fail
from .files import atomic_json, digest, inside, sync_dir
from .manifest import verify_file


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
    def __init__(self, game, backup):
        self.game = Path(game).resolve()
        self.backup = Path(backup).absolute()
        inside(self.game, '.boundary-check')
        inside(self.backup, '.boundary-check')
        if self.game.is_relative_to(self.backup.resolve()) or self.backup.resolve().is_relative_to(self.game):
            fail('PATH_CONFLICT', 'Rollback storage must be separate from the game directory.')
        self.path = inside(self.backup, 'transaction.json')
        self.journal = None

    def save(self):
        atomic_json(self.path, self.journal)

    def load(self):
        try:
            self.journal = json.loads(self.path.read_text(encoding='utf-8'))
            if self.journal['schema'] != 1 or self.journal['game'] != str(self.game):
                raise ValueError()
            names = set()
            for entry in self.journal['entries']:
                inside(self.game, entry['name'])
                inside(self.backup, 'original/' + entry['name'])
                if entry['name'].casefold() in names or entry['action'] not in ('install', 'remove'):
                    raise ValueError()
                names.add(entry['name'].casefold())
                for spec in (entry['old'], entry['new']):
                    if spec is not None and (type(spec['size']) is not int or spec['size'] < 0 or
                        len(spec['sha256']) != 64 or any(c not in '0123456789abcdef' for c in spec['sha256'])):
                        raise ValueError()
        except (ValueError, TypeError, KeyError, OSError):
            fail('JOURNAL_INVALID', 'Cannot read a valid rollback journal for this game root.')
        return self.journal

    def prepare(self, files, remove, manifest_hash, cancel=lambda: None, backup_enabled=True):
        if self.path.exists():
            old = self.load()
            fail('TRANSACTION_EXISTS', f"Existing transaction is {old['status']}. Retain it for rollback; select a fresh backup directory for a new deployment.")
        # Full preflight before copying even the first backup or touching the game.
        entries = []
        for name in sorted(set(files) | set(remove)):
            target = inside(self.game, name)
            for parent in target.parents:
                if parent == self.game:
                    break
                if parent.exists() and not parent.is_dir():
                    fail('PATH_CONFLICT', 'A destination parent is not a directory.')
            if target.exists() and not target.is_file():
                fail('PATH_CONFLICT', 'A destination is not a regular file.')
            old = {'size': target.stat().st_size, 'sha256': digest(target)} if backup_enabled and target.is_file() else None
            entries.append({'name': name, 'action': 'install' if name in files else 'remove',
                            'old': old, 'new': files[name][1] if name in files else None,
                            'existed': target.exists(), 'state': 'planned'})
        backup_bytes = sum(e['old']['size'] for e in entries if e['old'])
        new_bytes = sum(e['new']['size'] for e in entries if e['new'])
        growth = sum(max(0, files[e['name']][1]['size'] - (inside(self.game, e['name']).stat().st_size if e['existed'] else 0)) for e in entries if e['new'])
        largest = max((e['new']['size'] for e in entries if e['new']), default=0)
        self.backup.mkdir(parents=True, exist_ok=True)
        same_device = self.game.stat().st_dev == self.backup.stat().st_dev
        if shutil.disk_usage(self.backup).free < backup_bytes + (growth + largest if same_device else 0):
            fail('INSUFFICIENT_SPACE', 'Insufficient free space for backups and destination copies.')
        if shutil.disk_usage(self.game).free < growth + largest + (backup_bytes if same_device else 0):
            fail('INSUFFICIENT_SPACE', 'Insufficient free space for deployment and temporary copies.')
        self.journal = {'schema': 1, 'game': str(self.game), 'manifest': manifest_hash,
                        'status': 'preparing', 'backup_enabled': backup_enabled, 'entries': entries}
        self.save()
        for entry in entries:
            cancel()
            if entry['old']:
                source = inside(self.game, entry['name'])
                backup = inside(self.backup, 'original/' + entry['name'])
                if backup.exists():
                    fail('BACKUP_CONFLICT', 'Backup files already exist. Select a fresh backup directory.')
                copy_replace(source, backup, entry['old'])
            entry['state'] = 'backed_up'
            self.save()
        self.journal['status'] = 'prepared'
        self.save()

    def commit(self, files, cancel=lambda: None):
        if self.journal is None or self.journal['status'] != 'prepared':
            fail('JOURNAL_INVALID', 'Deployment requires a prepared transaction.')
        self.journal['status'] = 'deploying'
        self.save()
        for entry in self.journal['entries']:
            cancel()
            target = inside(self.game, entry['name'])
            if entry['old']:
                verify_file(target, entry['old'])
            elif target.exists() and not entry.get('existed', False):
                fail('PATH_CONFLICT', 'A destination changed after preflight.')
            # Persist intent BEFORE replace/unlink, so crash recovery knows this entry may have changed.
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
        atomic_json(inside(self.backup, 'verification.json'), report)
        self.journal['status'] = 'complete'
        self.save()

    def rollback(self):
        journal = self.load()
        if not journal.get('backup_enabled', True):
            fail('BACKUP_DISABLED', 'No rollback backup was requested. Retry the downgrade or restore the game using Steam.')
        if journal['status'] == 'rolled_back':
            return
        # Validate every needed backup and destination before changing any file.
        changed = [e for e in journal['entries'] if e['state'] in ('writing', 'written', 'restoring')]
        for entry in changed:
            if entry['old']:
                verify_file(inside(self.backup, 'original/' + entry['name']), entry['old'])
            target = inside(self.game, entry['name'])
            if target.exists():
                actual = digest(target) if target.is_file() else None
                allowed = [s['sha256'] for s in (entry['old'], entry['new']) if s]
                if actual not in allowed:
                    fail('ROLLBACK_CONFLICT', 'A game file changed since deployment. Preserve it before retrying rollback.')
        journal['status'] = 'rolling_back'
        self.save()
        for entry in reversed(changed):
            target = inside(self.game, entry['name'])
            entry['state'] = 'restoring'
            self.save()
            if entry['old']:
                copy_replace(inside(self.backup, 'original/' + entry['name']), target, entry['old'])
            elif target.exists():
                target.unlink()
                sync_dir(target.parent)
            entry['state'] = 'restored'
            self.save()
        journal['status'] = 'rolled_back'
        self.save()
