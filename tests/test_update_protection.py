import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from folon_downgrader import update_protection as up


class UpdateProtectionTests(unittest.TestCase):
    def test_manifest_comes_from_the_games_own_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            steamapps = Path(tmp) / 'Lib/steamapps'
            game = steamapps / 'common/Fallout 4'
            game.mkdir(parents=True)
            self.assertIsNone(up.manifest_path(game))  # manifest missing
            (steamapps / up.MANIFEST_NAME).write_text('x')
            self.assertEqual(up.manifest_path(game), steamapps / up.MANIFEST_NAME)
            self.assertIsNone(up.manifest_path(Path(tmp) / 'elsewhere'))

    def test_status_unknown_without_manifest(self):
        self.assertIsNone(up.status(None))

    def test_windows_status_and_verified_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / up.MANIFEST_NAME
            manifest.write_text('x')
            with patch.object(up.sys, 'platform', 'win32'), \
                    patch.object(up.os, 'stat', create=True) as stat_call:
                stat_call.return_value = SimpleNamespace(st_file_attributes=1)
                self.assertTrue(up.status(manifest))
                stat_call.return_value = SimpleNamespace(st_file_attributes=0)
                self.assertFalse(up.status(manifest))
                # Command "succeeds" but the attribute is unchanged: must not report success.
                with patch.object(up.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')):
                    ok, message = up.set_disabled(manifest, True)
                self.assertFalse(ok)
                self.assertTrue(message)

    def test_linux_status_parses_lsattr_and_handles_unsupported(self):
        with patch.object(up.sys, 'platform', 'linux'):
            with patch.object(up.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout='----i---------e------- /x\n', stderr='')):
                self.assertTrue(up.status('/x'))
            with patch.object(up.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout='--------------e------- /x\n', stderr='')):
                self.assertFalse(up.status('/x'))
            with patch.object(up.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=1, stdout='', stderr='Operation not supported')):
                self.assertIsNone(up.status('/x'))

    def test_linux_denied_authentication_reports_failure(self):
        with patch.object(up.sys, 'platform', 'linux'), \
                patch.object(up.shutil, 'which', return_value='/usr/bin/pkexec'), \
                patch.object(up.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=126, stdout='', stderr='')):
            ok, message = up.set_disabled('/x', True)
        self.assertFalse(ok)
        self.assertIn('Authentication', message)

    def test_missing_manifest_cannot_be_changed(self):
        self.assertFalse(up.set_disabled(None, True)[0])
