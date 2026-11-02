"""Regressions for remaining findings from the revised upstream audit."""
import io
import json
from pathlib import Path
import tempfile
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from folon_downgrader.errors import DowngradeError
from folon_downgrader.steamcmd import SteamCmdProvider
import test_core


class RecoveryTests(unittest.TestCase):
    setUp = test_core.Fixture.setUp
    write_manifest = test_core.Fixture.write_manifest

    def test_disk_full_after_mutation_reports_steam_recovery(self):
        with patch('folon_downgrader.deployment.copy_replace', side_effect=OSError(28, 'full')):
            result = self.engine.run('deploy', True)
        self.assertFalse(result['ok'])
        self.assertTrue(result['game_modified'])
        self.assertIn('Verify integrity', result['message'])
        self.assertIn('third-party mods', result['message'])

    def test_cancel_after_first_replacement_reports_incomplete(self):
        from folon_downgrader.deployment import copy_replace
        calls = []
        def cancel_after_copy(*args):
            copy_replace(*args)
            calls.append(args)
            self.engine.cancelled.set()
        with patch('folon_downgrader.deployment.copy_replace', side_effect=cancel_after_copy):
            result = self.engine.run('deploy', True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['error_code'], 'CANCELLED')
        self.assertTrue(result['game_modified'])
        self.assertIn('incomplete', result['message'])
        self.assertFalse((self.request.state / 'verification.json').exists())


class SettingsTests(unittest.TestCase):
    def test_invalid_shapes_and_schema_fall_back_but_old_preferences_load(self):
        from folon_downgrader.storage_settings import load_download_root
        with tempfile.TemporaryDirectory() as tmp, patch('folon_downgrader.storage_settings.data_root', return_value=Path(tmp)):
            config = Path(tmp) / 'storage-settings.json'
            for invalid in ([], None, 3, {'schema': 2, 'steamcmd_root': tmp}):
                config.write_text(json.dumps(invalid))
                self.assertEqual(load_download_root(), Path(tmp) / 'steamcmd')
            config.write_text(json.dumps({'steamcmd_root': tmp}))
            self.assertEqual(load_download_root(), Path(tmp))

    def test_failed_save_preserves_settings_and_unrelated_temp_file(self):
        from folon_downgrader.storage_settings import save_download_root, load_download_root
        with tempfile.TemporaryDirectory() as tmp, patch('folon_downgrader.storage_settings.data_root', return_value=Path(tmp)):
            save_download_root(tmp)
            unrelated = Path(tmp) / 'storage-settings.tmp'
            unrelated.write_text('user data')
            with patch('folon_downgrader.files.os.replace', side_effect=OSError('failure')):
                with self.assertRaises(OSError):
                    save_download_root(Path(tmp) / 'new')
            self.assertEqual(load_download_root(), Path(tmp))
            self.assertEqual(unrelated.read_text(), 'user data')
            self.assertFalse(list(Path(tmp).glob('.folon-*')))

    def test_legacy_writability_probe_preserves_named_user_file(self):
        from Utility import IsWritable
        with tempfile.TemporaryDirectory() as tmp:
            user_file = Path(tmp) / 'FOLON-Downgrader-TestFile'
            user_file.write_bytes(b'keep')
            self.assertTrue(IsWritable(tmp))
            self.assertEqual(user_file.read_bytes(), b'keep')
            self.assertEqual(list(Path(tmp).iterdir()), [user_file])


class BootstrapTests(unittest.TestCase):
    def test_tar_traversal_rejected_before_writing_safe_member(self):
        from folon_downgrader.steamcmd import extract
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'bad.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                for name in ('safe.txt', '../escape.txt'):
                    member = tarfile.TarInfo(name)
                    member.size = 1
                    tar.addfile(member, io.BytesIO(b'x'))
            with self.assertRaises(DowngradeError):
                extract(archive, Path(tmp) / 'out', False)
            self.assertFalse((Path(tmp) / 'out/safe.txt').exists())
            self.assertFalse((Path(tmp) / 'escape.txt').exists())

    def test_interrupted_setup_with_existing_launcher_must_be_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'steamcmd.exe').write_bytes(b'incomplete launcher')
            (root / '.bootstrap-incomplete.json').write_text('{"schema": 1}')
            provider = SteamCmdProvider(root, 'windows')
            with self.assertRaises(DowngradeError):
                provider.check()
            with patch('urllib.request.urlopen', return_value=self.archive()):
                provider.ensure_available()
            self.assertFalse((root / '.bootstrap-incomplete.json').exists())
            self.assertEqual(provider.check().read_bytes(), b'launcher')

    def archive(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('steamcmd.exe', b'launcher')
            archive.writestr('support.dll', b'support')
        stream.seek(0)
        return stream

    def test_cancellation_during_bootstrap_never_publishes_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'backend'
            calls = 0
            def cancel():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise DowngradeError('CANCELLED', 'Cancelled')
            with patch('urllib.request.urlopen', return_value=self.archive()):
                with self.assertRaises(DowngradeError) as caught:
                    SteamCmdProvider(root, 'windows').ensure_available(cancel)
            self.assertEqual(caught.exception.code, 'CANCELLED')
            self.assertFalse((root / 'steamcmd.exe').exists())
            self.assertFalse(list(Path(tmp).glob('.bootstrap-*')))

    def test_promotion_failure_does_not_mark_setup_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'backend'
            with patch('urllib.request.urlopen', return_value=self.archive()), \
                    patch('folon_downgrader.steamcmd.shutil.copy2', side_effect=OSError('full')):
                with self.assertRaises(OSError):
                    SteamCmdProvider(root, 'windows').ensure_available()
            self.assertFalse((root / 'steamcmd.exe').exists())
            self.assertFalse(list(root.glob('.bootstrap-copy-*')))
            with patch('urllib.request.urlopen', return_value=self.archive()):
                SteamCmdProvider(root, 'windows').ensure_available()
            self.assertEqual((root / 'steamcmd.exe').read_bytes(), b'launcher')
            self.assertEqual((root / 'support.dll').read_bytes(), b'support')

    def test_download_space_checks_selected_volume_and_credits_partial_files(self):
        from folon_downgrader.manifest import Manifest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / 'manifest.json'
            manifest_path.write_text(json.dumps({'schema': 1, 'steam_app_id': 377160,
                'target_exe_version': '1.10.163.0', 'inventory_complete': True,
                'depots': [{'id': 1, 'manifest': '100', 'files': [
                    {'path': 'Fallout4.exe', 'size': 100, 'sha256': '0' * 64}]}]}))
            provider = SteamCmdProvider(root, 'windows')
            partial = provider.candidate_roots()[0] / 'depot_1/Fallout4.exe'
            partial.parent.mkdir(parents=True)
            partial.write_bytes(b'x' * 40)
            needed = 60 + 100 + 64 * 1024 * 1024
            with patch('folon_downgrader.steamcmd.shutil.disk_usage', return_value=SimpleNamespace(free=needed-1)) as usage:
                with self.assertRaises(DowngradeError) as caught:
                    provider.check_download_space(Manifest(manifest_path))
                self.assertEqual(caught.exception.code, 'INSUFFICIENT_SPACE')
                usage.assert_called_once_with(provider.candidate_roots()[0])
            with patch('folon_downgrader.steamcmd.shutil.disk_usage', return_value=SimpleNamespace(free=needed)):
                provider.check_download_space(Manifest(manifest_path))
