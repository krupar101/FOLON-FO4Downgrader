from dataclasses import dataclass
import hashlib
import json
import shutil
from contextlib import ExitStack
import os
from pathlib import Path
import threading

from .deployment import Transaction, copy_replace
from .errors import DowngradeError, Stage, fail
from .files import Lock, inside, atomic_json
from .manifest import Manifest, executable_version, verify_depots, verify_target, verify_file
from .platforms import check_not_running, data_root, host
from .steamcmd import SteamCmdProvider, interactive_download, gui_download


@dataclass(frozen=True)
class Request:
    game: Path
    staging: Path
    steamcmd: Path
    backup: Path
    manifest: Path
    content: Path | None = None


class Engine:
    def __init__(self, request, emit=lambda event: None, ask=None):
        self.request = request
        self.ask = ask
        self.emit = emit
        self.cancelled = threading.Event()
        self.stage = Stage.PREFLIGHT
        self.game_modified = False

    def check_cancel(self):
        if self.cancelled.is_set():
            fail('CANCELLED', 'Operation cancelled. Staging and backups were retained.')

    def event(self, stage, **fields):
        self.stage = stage
        self.emit({'stage': stage.value, **fields})

    def preflight(self):
        r = self.request
        host()
        game = r.game.resolve()
        if not inside(game, 'Fallout4.exe').is_file():
            fail('GAME_NOT_FOUND', 'Select the Steam Fallout 4 directory containing Fallout4.exe.')
        appmanifest = game.parent.parent / 'appmanifest_377160.acf'
        if game.parent.name != 'common' or not appmanifest.is_file():
            fail('GAME_NOT_FOUND', 'A Steam library appmanifest_377160.acf is required for this target.')
        from .platforms import vdf_pairs
        app = dict(vdf_pairs(appmanifest.read_text(encoding='utf-8', errors='replace')))
        if app.get('appid') != '377160' or app.get('installdir') != game.name:
            fail('GAME_NOT_FOUND', 'The Steam app manifest does not identify this game directory.')
        managed = [game, r.staging.absolute(), r.steamcmd.absolute(), r.backup.absolute()]
        for root in managed:
            inside(root, '.boundary-check')
        for i, a in enumerate(managed):
            for b in managed[i + 1:]:
                if a.resolve().is_relative_to(b.resolve()) or b.resolve().is_relative_to(a.resolve()):
                    fail('PATH_CONFLICT', 'Game, staging, SteamCMD and backup roots must be separate, non-nested directories.')
        if r.content:
            content = r.content.resolve()
            if content.is_relative_to(game) or game.is_relative_to(content):
                fail('PATH_CONFLICT', 'Download content cannot overlap the game directory.')
        manifest = Manifest(r.manifest)
        check_not_running()
        report = {'platform': host(), 'game': str(game), 'staging': str(r.staging.absolute()),
                  'steamcmd': str(r.steamcmd.absolute()), 'backup': str(r.backup.absolute()),
                  'current_build': executable_version(game / 'Fallout4.exe'),
                  'target_build': manifest.data['target_exe_version'],
                  'manifest_sha256': manifest.sha256, 'inventory_complete': manifest.data.get('inventory_complete', False),
                  'writable': os.access(game, os.W_OK), 'game_modified': False}
        self.event(Stage.PREFLIGHT, **report)
        return manifest, report

    def lock_path(self):
        key = hashlib.sha256(os.path.normcase(str(self.request.game.resolve())).encode()).hexdigest()
        return data_root() / 'locks' / (key + '.lock')

    def verified_source(self, manifest):
        r = self.request
        cached = inside(r.staging.absolute(), 'verified/' + manifest.sha256)
        receipt = inside(cached, 'receipt.json')
        if receipt.is_file() and not r.content:
            try:
                data = json.loads(receipt.read_text(encoding='utf-8'))
                if data.get('manifest') == manifest.sha256 and data.get('game') == str(r.game.resolve()):
                    files = {name: (inside(cached, 'files/' + name), spec) for name, (_, spec) in manifest.selected_files().items()}
                    for path, spec in files.values():
                        self.check_cancel()
                        verify_file(path, spec)
                    return files
            except (ValueError, OSError, DowngradeError) as error:
                if isinstance(error, DowngradeError) and error.code == 'CANCELLED':
                    raise
        candidates = [r.content] if r.content else [r.staging / 'content', *SteamCmdProvider(r.steamcmd).candidate_roots()]
        existing = [p for p in candidates if p.is_dir()]
        if not existing:
            fail('DEPOT_TREE_MISSING', 'No downloaded depot tree exists. Game files have not been modified.')
        valid = []
        last = None
        for candidate in existing:
            try:
                files = verify_depots(candidate, manifest, self.check_cancel)
                valid.append(files)
            except DowngradeError as error:
                if error.code == 'CANCELLED':
                    raise
                last = error
        if not valid:
            raise last
        return valid[0]  # Every candidate was checked against the identical trusted hashes.

    def stage_verified(self, files, manifest):
        root = inside(self.request.staging.absolute(), 'verified/' + manifest.sha256)
        root.mkdir(parents=True, exist_ok=True)
        needed = sum(spec['size'] for source, spec in files.values() if not source.is_relative_to(root))
        if shutil.disk_usage(root).free < needed:
            fail('INSUFFICIENT_SPACE', 'Insufficient space for a durable verified staging copy.')
        staged = {}
        for name, (source, spec) in files.items():
            self.check_cancel()
            target = inside(root, 'files/' + name)
            if source != target:
                try:
                    verify_file(target, spec)
                except DowngradeError:
                    copy_replace(source, target, spec)
            staged[name] = (target, spec)
        atomic_json(inside(root, 'receipt.json'), {'manifest': manifest.sha256, 'game': str(self.request.game.resolve())})
        return staged

    def run(self, action, confirmed=False):
        """All frontends use this success/failure boundary; no generic finished callback."""
        tx = None
        try:
            with ExitStack() as locks:
                locks.enter_context(Lock(self.lock_path()))
                # Also serialize shared caches/backup roots across different game selections.
                for root in sorted({str(self.request.steamcmd.resolve()), str(self.request.staging.resolve()), str(self.request.backup.resolve())}):
                    key = hashlib.sha256(os.path.normcase(root).encode()).hexdigest()
                    locks.enter_context(Lock(data_root() / 'locks' / ('resource-' + key + '.lock')))
                if action == 'rollback':
                    if not confirmed:
                        fail('CONFIRMATION_REQUIRED', 'Rollback modifies game files; confirm the selected target first.')
                    check_not_running()
                    tx = Transaction(self.request.game, self.request.backup)
                    self.game_modified = True
                    tx.rollback()
                    result = {'ok': True, 'stage': 'rolled_back', 'game_modified': True}
                    self.emit(result)
                    return result
                manifest, report = self.preflight()
                self.check_cancel()
                if action in ('preflight', 'dry-run'):
                    return {'ok': True, 'stage': 'preflight', **report}
                if action == 'setup-steamcmd':
                    self.event(Stage.BOOTSTRAP)
                    SteamCmdProvider(self.request.steamcmd).ensure_available()
                    return {'ok': True, 'stage': 'bootstrap_steamcmd', 'game_modified': False}
                if action == 'download':
                    self.event(Stage.DOWNLOAD)
                    if self.ask:
                        gui_download(SteamCmdProvider(self.request.steamcmd), manifest, self.ask, self.emit, self.check_cancel)
                    else:
                        interactive_download(SteamCmdProvider(self.request.steamcmd), manifest, self.check_cancel)
                manifest.require_inventory()
                if action == 'verify-only':
                    self.event(Stage.VERIFY_TARGET)
                    verify_target(self.request.game, manifest)
                    return {'ok': True, 'stage': 'verified', 'game_modified': False}
                self.event(Stage.VERIFY_DOWNLOAD)
                files = self.verified_source(manifest)
                files = self.stage_verified(files, manifest)
                if action in ('verify-download', 'download'):
                    return {'ok': True, 'stage': 'verified_download', 'files': len(files), 'game_modified': False}
                if action not in ('deploy', 'resume', 'repair'):
                    fail('INVALID_ACTION', 'Unknown engine operation.')
                if not confirmed:
                    fail('CONFIRMATION_REQUIRED', 'Deployment modifies game files; confirm the selected target first.')
                check_not_running()
                tx = Transaction(self.request.game, self.request.backup)
                if tx.path.exists():
                    state = tx.load()
                    if state['manifest'] != manifest.sha256:
                        fail('RESUME_MISMATCH', 'The existing transaction belongs to another release manifest.')
                    if state['status'] == 'complete':
                        verify_target(self.request.game, manifest)
                        return {'ok': True, 'stage': 'complete', 'game_modified': False, 'already_installed': True}
                    fail('ROLLBACK_REQUIRED', 'An existing transaction requires rollback before a new deployment. Backups were retained.')
                self.event(Stage.PREPARE, files=len(files))
                tx.prepare(files, manifest.data.get('remove', []), manifest.sha256, self.check_cancel)
                self.check_cancel()
                self.event(Stage.DEPLOY, files=len(files))
                self.game_modified = True  # Conservative: mutation may have happened even on a failed write.
                tx.commit(files, self.check_cancel)
                self.event(Stage.VERIFY_TARGET)
                verify_target(self.request.game, manifest)
                result = {'ok': True, 'stage': 'complete', 'manifest_sha256': manifest.sha256,
                          'target_version': manifest.data['target_exe_version'], 'game_modified': True,
                          'verification_level': 'sha256_and_pe_version', 'files': len(files)}
                tx.complete(result)
                self.event(Stage.COMPLETE, **{k: v for k, v in result.items() if k != 'stage'})
                return result
        except (Exception, KeyboardInterrupt) as error:
            if isinstance(error, DowngradeError):
                code, message = error.code, error.message
            elif isinstance(error, (KeyboardInterrupt, InterruptedError)):
                code, message = 'CANCELLED', 'Operation cancelled. Staging and backups were retained.'
            elif isinstance(error, PermissionError):
                code, message = 'PERMISSION_DENIED', 'Access denied. Check selected directory permissions.'
            elif isinstance(error, OSError):
                code = 'INSUFFICIENT_SPACE' if error.errno == 28 else 'FILESYSTEM_ERROR'
                message = 'A filesystem operation failed. Staging and backups were retained.'
            else:
                code, message = 'INTERNAL_ERROR', 'The operation stopped unexpectedly. No subsequent stage was started.'
            result = {'ok': False, 'stage': self.stage.value, 'error_code': code, 'message': message,
                      'game_modified': self.game_modified,
                      'rollback_required': self.game_modified and action != 'rollback'}
            self.emit(result)
            return result
