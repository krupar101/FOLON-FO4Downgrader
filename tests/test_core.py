import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from folon_downgrader.deployment import Transaction
from folon_downgrader.engine import Engine, Request
from folon_downgrader.errors import DowngradeError
from folon_downgrader.files import Lock, digest, inside
from folon_downgrader.manifest import Manifest, verify_depots
from folon_downgrader.platforms import discover
from folon_downgrader.steamcmd import SteamCmdProvider, classify, extract, interactive_download


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='folon test ż ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'library/steamapps/common/Fallout 4'
        self.game.mkdir(parents=True)
        (self.game / 'Fallout4.exe').write_bytes(b'old exe')
        (self.game.parent.parent / 'appmanifest_377160.acf').write_text('"AppState" { "appid" "377160" "installdir" "Fallout 4" }')
        self.content = self.root / 'content'
        self.content.mkdir()
        self.manifest_path = self.root / 'release.json'
        self.manifest_data = {'schema': 1, 'steam_app_id': 377160, 'target_exe_version': '1.10.163.0',
                              'inventory_complete': True, 'depots': [], 'remove': []}
        for depot_id, name, data in [(1, 'Fallout4.exe', b'new exe'), (2, 'Data/file.ba2', b'new data')]:
            path = self.content / f'depot_{depot_id}' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.manifest_data['depots'].append({'id': depot_id, 'manifest': str(depot_id * 100),
                'files': [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]})
        self.write_manifest()
        self.request = Request(self.game, self.root / 'stage', self.root / 'backend', self.root / 'state',
                               self.manifest_path, self.content)
        self.events = []
        self.engine = Engine(self.request, self.events.append)
        self.addCleanup(patch.stopall)
        patch('folon_downgrader.engine.data_root', return_value=self.root / 'appdata').start()
        patch('folon_downgrader.engine.check_not_running').start()
        patch('folon_downgrader.engine.steam_processes', return_value=[]).start()
        patch('folon_downgrader.engine.executable_version', return_value='1.10.984.0').start()
        patch('folon_downgrader.manifest.executable_version', return_value='1.10.163.0').start()

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest_data))

    def snapshot(self):
        return {p.relative_to(self.game).as_posix(): p.read_bytes() for p in self.game.rglob('*') if p.is_file()}

    def test_missing_tree_never_mutates_game(self):
        import shutil
        shutil.rmtree(self.content)
        before = self.snapshot()
        result = self.engine.run('deploy', True)
        self.assertEqual(result['error_code'], 'DEPOT_TREE_MISSING')
        self.assertFalse(result['game_modified'])
        self.assertEqual(before, self.snapshot())

    def test_incomplete_and_corrupt_depot_never_mutate_game(self):
        path = self.content / 'depot_2/Data/file.ba2'
        for contents, expected in [(None, 'DEPOT_INCOMPLETE'), (b'corrupt!', 'HASH_MISMATCH')]:
            with self.subTest(expected=expected):
                if contents is None:
                    path.unlink()
                else:
                    path.write_bytes(contents)
                before = self.snapshot()
                result = self.engine.run('deploy', True)
                self.assertEqual(result['error_code'], expected)
                self.assertEqual(before, self.snapshot())

    def test_default_inventory_blocks_deployment(self):
        self.manifest_data['inventory_complete'] = False
        self.write_manifest()
        self.assertEqual(self.engine.run('deploy', True)['error_code'], 'MANIFEST_UNVERIFIED')
        self.assertFalse((self.root / 'state/transaction.json').exists())

    def test_success_report_and_repeat_are_verified(self):
        result = self.engine.run('deploy', True)
        self.assertTrue(result['ok'], result)
        report = json.loads((self.root / 'state/verification.json').read_text())
        self.assertEqual(report['verification_level'], 'sha256_and_pe_version')
        before = self.snapshot()
        result = self.engine.run('resume', True)
        self.assertTrue(result['ok'])
        self.assertEqual(before, self.snapshot())

    def test_target_version_failure_requires_retry(self):
        with patch('folon_downgrader.manifest.executable_version', return_value='1.0.0.0'):
            result = self.engine.run('deploy', True)
        self.assertEqual(result['error_code'], 'TARGET_VERIFY_FAILED')
        self.assertTrue(result['retry_required'])
        self.assertFalse((self.root / 'state/verification.json').exists())
        self.assertTrue(Engine(self.request).run('deploy', True)['ok'])

    def test_mid_deploy_failure_can_retry(self):
        import folon_downgrader.deployment as deployment
        original = deployment.copy_replace
        before = self.snapshot()
        count = 0
        def broken(source, target, spec):
            nonlocal count
            if target.resolve().is_relative_to(self.game.resolve()):
                count += 1
                if count == 2:
                    raise OSError(28, 'disk full')
            return original(source, target, spec)
        with patch.object(deployment, 'copy_replace', side_effect=broken):
            result = self.engine.run('deploy', True)
        self.assertEqual(result['error_code'], 'INSUFFICIENT_SPACE')
        self.assertTrue(result['retry_required'])
        fresh = Engine(self.request)
        self.assertTrue(fresh.run('deploy', True)['ok'])
        self.assertEqual((self.game / 'Fallout4.exe').read_bytes(), b'new exe')

    def test_crash_after_replace_before_journal_update(self):
        from folon_downgrader.deployment import copy_replace
        files = verify_depots(self.content, Manifest(self.manifest_path))
        tx = Transaction(self.game, self.root / 'state')
        before = self.snapshot()
        tx.prepare(files, [], Manifest(self.manifest_path).sha256)
        # Reproduce a process dying after replace, while the durable entry says writing.
        entry = next(e for e in tx.journal['entries'] if e['name'] == 'Fallout4.exe')
        entry['state'] = 'writing'
        tx.save()
        copy_replace(*[files['Fallout4.exe'][0], self.game / 'Fallout4.exe', files['Fallout4.exe'][1]])
        self.assertTrue(Engine(self.request).run('deploy', True)['ok'])
        self.assertEqual((self.game / 'Fallout4.exe').read_bytes(), b'new exe')

    def test_unexpected_worker_exception_stops_transition(self):
        with patch.object(self.engine, 'verified_source', side_effect=RuntimeError('synthetic secret')):
            result = self.engine.run('deploy', True)
        self.assertEqual(result['error_code'], 'INTERNAL_ERROR')
        self.assertNotIn('synthetic secret', json.dumps(self.events))
        self.assertNotIn('deploy', [e['stage'] for e in self.events])

    def test_cancel_before_deploy(self):
        self.engine.cancelled.set()
        result = self.engine.run('deploy', True)
        self.assertEqual(result['error_code'], 'CANCELLED')
        self.assertFalse(result['game_modified'])

    def test_explicit_confirmation_required(self):
        self.assertEqual(self.engine.run('deploy')['error_code'], 'CONFIRMATION_REQUIRED')
        self.assertEqual((self.game / 'Fallout4.exe').read_bytes(), b'old exe')


    def test_allowlisted_cleanup_preserves_unlisted_files(self):
        (self.game / 'cc-official.ba2').write_bytes(b'original')
        (self.game / 'cc-user.ba2').write_bytes(b'user')
        self.manifest_data['remove'] = ['cc-official.ba2']
        self.write_manifest()
        before = self.snapshot()
        self.assertTrue(self.engine.run('deploy', True)['ok'])
        self.assertFalse((self.game / 'cc-official.ba2').exists())
        self.assertEqual((self.game / 'cc-user.ba2').read_bytes(), b'user')


    def test_source_symlink_rejected(self):
        target = self.content / 'depot_1/Fallout4.exe'
        target.unlink()
        try:
            target.symlink_to(self.game / 'Fallout4.exe')
        except OSError:
            self.skipTest('Host does not permit symlink creation')
        self.assertEqual(self.engine.run('deploy', True)['error_code'], 'UNSAFE_PATH')

    def test_destination_symlink_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            (self.game / 'Data').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Host does not permit symlink creation')
        self.assertEqual(self.engine.run('deploy', True)['error_code'], 'UNSAFE_PATH')
        self.assertEqual(list(outside.iterdir()), [])

    def test_two_instances_are_locked(self):
        with Lock(self.engine.lock_path()):
            result = self.engine.run('deploy', True)
        self.assertEqual(result['error_code'], 'ALREADY_RUNNING')

    def test_nondefault_library_discovery(self):
        steam = self.root / 'Steam'
        (steam / 'steamapps').mkdir(parents=True)
        escaped = str(self.root / 'library').replace('\\', '\\\\')
        (steam / 'steamapps/libraryfolders.vdf').write_text(f'"libraryfolders" {{ "1" {{ "path" "{escaped}" }} }}', encoding="utf-8")
        self.assertEqual(discover([steam]), [self.game.resolve()])

    def test_overlapping_depot_files_require_owner(self):
        spec = copy.deepcopy(self.manifest_data['depots'][0]['files'][0])
        spec['sha256'] = '0' * 64
        self.manifest_data['depots'][1]['files'].append(spec)
        self.write_manifest()
        with self.assertRaises(DowngradeError) as caught:
            Manifest(self.manifest_path).require_inventory()
        self.assertEqual(caught.exception.code, 'MANIFEST_CONFLICT')


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='steamcmd ż ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_existing_empty_folder_is_not_installed(self):
        provider = SteamCmdProvider(self.root, 'windows')
        with self.assertRaises(DowngradeError) as caught:
            provider.check()
        self.assertEqual(caught.exception.code, 'STEAMCMD_NOT_FOUND')

    def test_incomplete_bootstrap_repairs_executable(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('steamcmd.exe', b'fake executable')
        archive.seek(0)
        with patch('urllib.request.urlopen', return_value=archive):
            path = SteamCmdProvider(self.root, 'windows').ensure_available()
        self.assertEqual(path.read_bytes(), b'fake executable')

    def test_archive_traversal_rejected_before_extraction(self):
        for name in ('../escape', '/absolute', 'C:/evil', 'folder/../../evil'):
            with self.subTest(name=name):
                archive = self.root / 'bad.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr('safe', b'not extracted')
                    z.writestr(name, b'bad')
                with self.assertRaises(DowngradeError):
                    extract(archive, self.root / 'out', True)
                self.assertFalse((self.root / 'out/safe').exists())

    def test_tar_link_rejected(self):
        archive = self.root / 'bad.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            entry = tarfile.TarInfo('link')
            entry.type = tarfile.SYMTYPE
            entry.linkname = '/tmp'
            tar.addfile(entry)
        with self.assertRaises(DowngradeError):
            extract(archive, self.root / 'out', False)

    def test_backend_classifies_errors_without_echoing_output(self):
        for output, code in [('ERROR! Download failed', 'DEPOT_DOWNLOAD_FAILED'), ('Invalid Password secret', 'AUTH_DENIED'),
                             ('Rate Limit Exceeded', 'RATE_LIMITED'), ('SSL Error secret', 'TLS_VERIFY_FAILED'),
                             ('Steam Guard required', 'AUTH_PENDING')]:
            self.assertEqual(classify(0, output), code)
        self.assertEqual(classify(1, ''), 'DEPOT_DOWNLOAD_FAILED')
        self.assertIsNone(classify(0, 'unexpected text'))  # This does NOT authorize deployment; verifier still gates it.

    @unittest.skipIf(os.name == 'nt', 'POSIX fake executable; Windows exercised by CI mocks')
    def test_real_child_uses_absolute_cwd_and_no_credentials(self):
        fake = self.root / 'fake steamcmd'
        fake.write_text('#!/bin/sh\npwd > observed-cwd\nprintf "%s" "$*" > observed-args\nexit 0\n')
        fake.chmod(0o700)
        provider = SteamCmdProvider(self.root, 'linux')
        provider.check = lambda: fake
        manifest = type('M', (), {'depots': [{'id': 1, 'manifest': '100'}]})()
        with patch('builtins.print'):
            interactive_download(provider, manifest, timeout=5)
        self.assertEqual((self.root / 'observed-cwd').read_text().strip(), str(self.root))
        self.assertEqual((self.root / 'observed-args').read_text(), '')
        self.assertNotIn('login', (self.root / 'folon-depots.txt').read_text())

    @unittest.skipIf(os.name == 'nt', 'POSIX fake executable')
    def test_real_child_nonzero_exit_stops(self):
        fake = self.root / 'fake'
        fake.write_text('#!/bin/sh\nexit 1\n')
        fake.chmod(0o700)
        provider = SteamCmdProvider(self.root, 'linux')
        provider.check = lambda: fake
        manifest = type('M', (), {'depots': []})()
        with patch('builtins.print'), self.assertRaises(DowngradeError) as caught:
            interactive_download(provider, manifest, timeout=5)
        self.assertEqual(caught.exception.code, 'DEPOT_DOWNLOAD_FAILED')

    def test_missing_executable_at_launch_is_typed(self):
        provider = SteamCmdProvider(self.root, 'windows')
        provider.check = lambda: self.root / 'missing.exe'
        with patch('builtins.print'), self.assertRaises(DowngradeError) as caught:
            interactive_download(provider, type('M', (), {'depots': []})())
        self.assertEqual(caught.exception.code, 'STEAMCMD_NOT_FOUND')


if __name__ == '__main__':
    unittest.main()


class GuiBackendTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX executable fixture')
    def test_pipe_auth_download_and_secret_output_is_not_emitted(self):
        from folon_downgrader.steamcmd import gui_download
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'fake'
            script.write_text('#!' + sys.executable + '\n' + '''
import sys
print('ILocalize::AddFile() failed to load optional translation resource.', flush=True)
print('Steam>', flush=True)
assert input() == 'login example_user'
print('password:', flush=True)
secret = input()
print('echo:' + secret, flush=True)
print('Waiting for user info...OK\\nSteam>', flush=True)
assert input() == 'download_depot 377160 1 100'
print('Depot download complete\\nSteam>', flush=True)
assert input() == 'quit'
''')
            script.chmod(0o700)
            provider = SteamCmdProvider(root, 'linux')
            provider.check = lambda: script
            secret = 'test \\" ż synthetic-password'
            events = []
            gui_download(provider, type('M', (), {'depots': [{'id': 1, 'manifest': '100'}]})(),
                         lambda kind: 'example_user' if kind == 'username' else secret,
                         events.append, timeout=5)
            self.assertNotIn(secret, json.dumps(events))
            self.assertEqual(events[-1]['stage'], 'download')
            self.assertEqual(list(root.iterdir()), [script])


class InventoryTests(unittest.TestCase):
    setUp = Fixture.setUp
    write_manifest = Fixture.write_manifest

    def test_candidate_never_self_approves(self):
        from folon_downgrader.inventory import candidate
        with patch('folon_downgrader.inventory.executable_version', return_value='1.10.163.0'):
            result = candidate(Manifest(self.manifest_path), self.content)
        self.assertFalse(result['inventory_complete'])
        self.assertEqual(len(result['depots']), 2)

    def test_truncated_steam_export_rejected(self):
        from folon_downgrader.inventory import steam_text
        path = self.root / 'export.txt'
        path.write_text('Content Manifest for Depot 1\nManifest ID / date : 100 / date\nTotal number of files : 2\nSize Chunks File SHA Flags Name\n1 1 ' + 'a'*40 + ' 0 Fallout4.exe\n')
        with self.assertRaises(DowngradeError):
            steam_text(path, 1, '100')

    def test_steam_export_ids_and_hashes(self):
        from folon_downgrader.inventory import steam_text
        path = self.root / 'export.txt'
        path.write_text('Content Manifest for Depot 1\nManifest ID / date : 100 / date\nTotal number of files : 1\nSize Chunks File SHA Flags Name\n8 1 ' + 'a'*40 + ' 0 Fallout4.exe\n')
        parsed = steam_text(path, 1, '100')
        self.assertEqual(parsed['Fallout4.exe']['size'], 8)
        with self.assertRaises(DowngradeError):
            steam_text(path, 1, '101')


class SteamStartupRegressionTests(unittest.TestCase):
    def test_optional_localization_warning_is_not_download_failure(self):
        warning = 'ILocalize::AddFile() failed to load file "public/steambootstrapper_polish.txt".\nSteam>'
        self.assertIsNone(classify(0, warning))
        self.assertEqual(classify(1, warning), 'DEPOT_DOWNLOAD_FAILED')

    def test_failure_word_in_account_name_is_not_failure(self):
        self.assertIsNone(classify(0, 'Steam>login failed_user\npassword:'))

    def test_guard_chatter_does_not_hide_depot_failure(self):
        self.assertEqual(classify(0, 'Steam Guard approved\nERROR! Download failed'), 'DEPOT_DOWNLOAD_FAILED')

    def test_phase_is_reported_without_raw_backend_output(self):
        from folon_downgrader.steamcmd import session_failure
        code, message = session_failure('DEPOT_DOWNLOAD_FAILED', 'startup')
        self.assertEqual(code, 'STEAMCMD_BOOTSTRAP_FAILED')
        self.assertIn('SteamCMD startup', message)
        code, message = session_failure('DEPOT_DOWNLOAD_FAILED', 'download', 377161)
        self.assertIn('377161', message)


class ExcludedContentTests(unittest.TestCase):
    setUp = Fixture.setUp
    write_manifest = Fixture.write_manifest
    snapshot = Fixture.snapshot

    def add_cc(self):
        name = 'Data/cc-official.ba2'
        source = self.content / 'depot_2' / name
        source.write_bytes(b'official cc')
        self.manifest_data['depots'][1]['files'].append({'path': name, 'size': 11, 'sha256': hashlib.sha256(b'official cc').hexdigest()})
        self.manifest_data['exclude'] = [name]
        self.manifest_data['remove'] = [name]
        target = self.game / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b'original cc')
        self.write_manifest()
        return source, target

    def test_excluded_verified_content_is_removed(self):
        _, target = self.add_cc()
        before = self.snapshot()
        result = self.engine.run('deploy', True)
        self.assertTrue(result['ok'], result)
        self.assertFalse(target.exists())

    def test_excluded_downloads_still_require_integrity(self):
        source, _ = self.add_cc()
        source.write_bytes(b'bad')
        before = self.snapshot()
        self.assertEqual(self.engine.run('deploy', True)['error_code'], 'HASH_MISMATCH')
        self.assertEqual(before, self.snapshot())

    def test_cannot_exclude_executable(self):
        self.manifest_data['exclude'] = ['Fallout4.exe']
        self.write_manifest()
        self.assertEqual(self.engine.run('deploy', True)['error_code'], 'MANIFEST_INVALID')


class FastDeploymentTests(unittest.TestCase):
    setUp = Fixture.setUp
    write_manifest = Fixture.write_manifest
    snapshot = Fixture.snapshot
    def no_backup_engine(self):
        return Engine(self.request)


    def test_no_backup_installs_without_original_or_staging_copy(self):
        engine = self.no_backup_engine()
        self.assertTrue(engine.run('deploy', True)['ok'])
        self.assertFalse((self.root/'state/original').exists())
        self.assertFalse((self.root/'stage').exists())

    def test_failed_no_backup_install_can_retry(self):
        import folon_downgrader.deployment as deployment
        original = deployment.copy_replace
        def broken(source, target, spec):
            if target.name == 'Fallout4.exe':
                raise OSError(28, 'full')
            return original(source, target, spec)
        engine = self.no_backup_engine()
        with patch.object(deployment, 'copy_replace', side_effect=broken):
            result = engine.run('deploy', True)
        self.assertTrue(result['retry_required'])
        self.assertTrue(self.no_backup_engine().run('deploy', True)['ok'])

    def test_download_verification_reuses_only_unchanged_files(self):
        import folon_downgrader.manifest as module
        engine = self.no_backup_engine()
        with patch.object(module, 'verify_file', wraps=module.verify_file) as verify:
            self.assertTrue(engine.run('verify-download')['ok'])
            self.assertEqual(verify.call_count, 2)
            self.assertTrue(engine.run('verify-download')['ok'])
            self.assertEqual(verify.call_count, 2)
            (self.content/'depot_1/Fallout4.exe').write_bytes(b'bad exe')
            self.assertEqual(engine.run('deploy', True)['error_code'], 'HASH_MISMATCH')
        self.assertEqual((self.game/'Fallout4.exe').read_bytes(), b'old exe')

    def test_source_corruption_never_replaces_destination(self):
        from folon_downgrader.deployment import copy_replace
        source = self.content/'depot_1/Fallout4.exe'
        source.write_bytes(b'bad exe')
        with self.assertRaises(DowngradeError):
            copy_replace(source, self.game/'Fallout4.exe', self.manifest_data['depots'][0]['files'][0])
        self.assertEqual((self.game/'Fallout4.exe').read_bytes(), b'old exe')

    def test_steam_blocks_deployment_before_changes(self):
        with patch('folon_downgrader.engine.steam_processes', return_value=[object()]):
            self.assertEqual(self.no_backup_engine().run('deploy', True)['error_code'], 'STEAM_RUNNING')
        self.assertEqual((self.game/'Fallout4.exe').read_bytes(), b'old exe')


class SteamShutdownTests(unittest.TestCase):
    def test_normal_shutdown_waits_for_exit(self):
        from folon_downgrader.platforms import shutdown_steam
        from unittest.mock import Mock
        process = Mock()
        process.exe.return_value = '/steam/steam'
        with patch('folon_downgrader.platforms.steam_processes', side_effect=[[process], []]), patch('subprocess.Popen') as spawn:
            shutdown_steam()
            self.assertEqual(spawn.call_args.args[0], ['/steam/steam', '-shutdown'])

    def test_slow_shutdown_keeps_waiting_and_can_cancel(self):
        from folon_downgrader.platforms import shutdown_steam
        from unittest.mock import Mock
        process = Mock()
        process.exe.return_value = '/steam/steam'
        cancel = Mock(side_effect=[None, None, DowngradeError('CANCELLED', 'Cancelled')])
        progress = Mock()
        with patch('folon_downgrader.platforms.steam_processes', return_value=[process]), patch('subprocess.Popen'), patch('time.monotonic', side_effect=[0, 120]), patch('time.sleep'):
            with self.assertRaises(DowngradeError) as error:
                shutdown_steam(cancel, progress)
        self.assertEqual(error.exception.code, 'CANCELLED')
        self.assertEqual(progress.call_count, 2)
        process.kill.assert_not_called()

    def test_steam_exits_between_discovery_and_shutdown(self):
        import psutil
        from folon_downgrader.platforms import shutdown_steam
        from unittest.mock import Mock
        process = Mock()
        process.exe.side_effect = psutil.NoSuchProcess(42)
        with patch('folon_downgrader.platforms.steam_processes', side_effect=[[process], []]), patch('subprocess.Popen') as spawn:
            shutdown_steam()
            spawn.assert_not_called()

    def test_zombie_and_dead_steam_are_not_running(self):
        import psutil
        from folon_downgrader.platforms import steam_processes
        from unittest.mock import Mock
        zombie = Mock(info={'name': 'steam', 'status': psutil.STATUS_ZOMBIE})
        dead = Mock(info={'name': 'steam.exe', 'status': psutil.STATUS_DEAD})
        active = Mock(info={'name': 'steam', 'status': psutil.STATUS_SLEEPING})
        active.is_running.return_value = True
        with patch('psutil.process_iter', return_value=[zombie, dead, active]):
            self.assertEqual(steam_processes(), [active])

    def test_slow_shutdown_automatically_continues_on_exit(self):
        from folon_downgrader.platforms import shutdown_steam
        from unittest.mock import Mock
        process = Mock()
        process.exe.return_value = '/steam/steam'
        with patch('folon_downgrader.platforms.steam_processes', side_effect=[[process], [process], [process], []]), patch('subprocess.Popen'), patch('time.monotonic', side_effect=[0, 120]), patch('time.sleep'):
            shutdown_steam()


class RootAliasTests(unittest.TestCase):
    setUp = Fixture.setUp
    write_manifest = Fixture.write_manifest
    snapshot = Fixture.snapshot
    def test_selected_roots_through_directory_alias_work(self):
        alias = self.root / 'home-alias'
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest('Host does not permit symlink creation')
        request = Request(alias / self.game.relative_to(self.root), alias/'stage',
                          alias/'backend', alias/'state', self.manifest_path,
                          alias/'content')
        self.assertEqual(request.game, self.game.resolve())
        self.assertEqual(request.content, self.content.resolve())
        self.assertTrue(Engine(request).run('deploy', True)['ok'])

    def test_alias_cannot_hide_overlapping_managed_roots(self):
        alias = self.root/'game-alias'
        try:
            alias.symlink_to(self.game, target_is_directory=True)
        except OSError:
            self.skipTest('Host does not permit symlink creation')
        request = Request(self.game, alias/'stage', self.root/'backend',
                          self.root/'state', self.manifest_path, self.content)
        self.assertEqual(Engine(request).run('deploy', True)['error_code'], 'PATH_CONFLICT')


class BundledInventoryTests(unittest.TestCase):
    def test_bundled_inventory_enables_complete_reviewed_release(self):
        from folon_downgrader.cli import manifest_path, parser
        from folon_downgrader import __version__
        manifest = Manifest(manifest_path())
        manifest.require_inventory()
        self.assertEqual(__version__, '2.0.0')
        self.assertEqual(len(manifest.depots), 14)
        self.assertEqual(sum(len(d['files']) for d in manifest.depots), 117)
        self.assertEqual(len(manifest.selected_files()), 90)
        self.assertEqual(manifest.data['overrides']['Data/Fallout4 - Meshes.ba2'], 377163)
        self.assertEqual(len(manifest.data['remove']), 51)
        flags = parser()._option_string_actions
        self.assertNotIn('--backup', flags)
        self.assertNotIn('--rollback', flags)
