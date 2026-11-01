import importlib.util
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PyQt5'), 'Qt is optional for headless core tests')
class GuiTests(unittest.TestCase):
    def test_original_pages_load_offline_and_failure_does_not_advance(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        self.assertEqual(window.pages.count(), 4)
        self.assertEqual(window.windowTitle(), 'Downgrader 2.0')
        self.assertFalse(hasattr(window, 'rollback'))
        self.assertFalse(hasattr(window, 'backup_option'))
        self.assertEqual(window.PasswordEntry.echoMode(), window.PasswordEntry.Password)
        window.failed({'error_code': 'DEPOT_INCOMPLETE', 'message': 'Missing file', 'rollback_required': False})
        self.assertEqual(window.pages.currentIndex(), 0)
        window.close()

    def test_existing_downloads_are_verified_before_deploy_page(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args(['--content-root', '/existing/depot-tree']))
        window.worker = SimpleNamespace(action='preflight')
        window.succeeded({'inventory_complete': True})
        self.assertEqual(window._next_action, 'verify-download')
        self.assertEqual(window.pages.currentIndex(), 0)
        window.worker.action = 'verify-download'
        window.failed({'error_code': 'DEPOT_INCOMPLETE', 'message': 'Missing file'})
        self.assertEqual(window.pages.currentIndex(), 0)
        window.succeeded({})
        self.assertEqual(window.pages.currentIndex(), 2)
        window.worker = None
        window.close()

    def test_existing_default_downloads_skip_login_until_verification_fails(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        window.worker = SimpleNamespace(action='preflight')
        window.succeeded({'downloads_available': True})
        self.assertEqual(window._next_action, 'verify-download')
        window.worker.action = 'verify-download'
        window.failed({'error_code': 'HASH_MISMATCH', 'message': 'Damaged file'})
        self.assertEqual(window.pages.currentIndex(), 1)
        window.worker = None
        window.close()
