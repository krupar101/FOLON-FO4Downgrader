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
        self.assertFalse(hasattr(window, 'SteamGuardCheck'))
        from PyQt5.QtWidgets import QLabel
        self.assertTrue(any('Steam Guard:' in label.text() for label in window.tab2.findChildren(QLabel)))
        window.failed({'error_code': 'DEPOT_INCOMPLETE', 'message': 'Missing file', 'rollback_required': False})
        self.assertEqual(window.pages.currentIndex(), 0)
        window.close()

    def test_compact_window_uses_fitted_pages_without_scroll_area(self):
        from PyQt5.QtWidgets import QApplication, QScrollArea
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        self.assertEqual((window.width(), window.height()), (980, 600))
        self.assertEqual(window.minimumHeight(), 600)
        self.assertEqual(window.maximumHeight(), 600)
        self.assertFalse(window.findChildren(QScrollArea))
        self.assertFalse(hasattr(window, 'page_scroll'))
        self.assertIs(window.layout_root.itemAt(3).widget(), window.pages)
        window.close()

    def test_window_height_stays_constant_across_progress_and_recovery(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        window.show()
        app.processEvents()
        initial = window.height()
        window.start_activity('download')
        window.pages.hide()
        window.set_activity_centered(True)
        window.show_progress({'stage': 'authenticate', 'auth_state': 'waiting'})
        window.log_toggle.setChecked(True)
        app.processEvents()
        self.assertEqual(window.height(), initial)
        window.log_toggle.setChecked(False)
        window.pages.show()
        window.set_activity_centered(False)
        window.activity.hide()
        window.error_banner.setText('Steam authentication was interrupted. Retry sign-in.')
        window.error_banner.show()
        window.pages.setCurrentIndex(1)
        app.processEvents()
        self.assertEqual(window.height(), initial)
        window.pages.setCurrentIndex(3)
        window.error_banner.hide()
        app.processEvents()
        self.assertEqual(window.height(), initial)
        window.close()

    def test_processing_uses_one_progress_indicator_and_hides_wizard_page(self):
        from PyQt5.QtWidgets import QApplication, QProgressBar
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        assert not hasattr(window, 'progress')
        assert window.findChildren(QProgressBar) == [window.activity_bar]
        window.start_activity('deploy')
        window.pages.hide()
        window.set_activity_centered(True)
        assert window.activity.isVisibleTo(window)
        assert not window.pages.isVisibleTo(window)
        assert window.layout_root.stretch(0) == 1
        assert window.layout_root.stretch(4) == 1
        window.pages.show()
        window.set_activity_centered(False)
        assert window.layout_root.stretch(0) == 0
        assert window.layout_root.stretch(4) == 0
        window.close()

    def test_cancel_button_only_visible_during_active_operation(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        window.show()
        app.processEvents()
        self.assertTrue(window.cancel.isHidden())
        self.assertFalse(window.cancel.isEnabled())
        # No worker is needed to exercise the visible operation state.
        window.start_activity('download')
        window.cancel.setEnabled(True)
        window.cancel.show()
        app.processEvents()
        self.assertTrue(window.cancel.isVisible())
        self.assertTrue(window.cancel.isEnabled())
        window.cancel.setEnabled(False)
        window.cancel.hide()
        app.processEvents()
        self.assertTrue(window.cancel.isHidden())
        window.close()

    def test_steam_login_fields_have_font_aware_height(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        for field in (window.UsernameEntry, window.PasswordEntry):
            self.assertGreaterEqual(field.minimumHeight(), 40)
            self.assertGreaterEqual(field.minimumHeight(), field.fontMetrics().height() + 20)
        window.close()

    def test_steam_credentials_autofill_but_guard_prompts_inline(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        from queue import Queue
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        replies = Queue()
        window.start_activity('download')
        window.worker = SimpleNamespace(answers=replies)
        window.UsernameEntry.setText('example_user')
        window.prompt('username')
        self.assertEqual(replies.get_nowait(), 'example_user')
        self.assertTrue(window.auth_panel.isHidden())
        self.assertIn('Signing in', window.activity_detail.text())
        window.prompt('steam_guard')
        self.assertTrue(window.auth_panel.isVisibleTo(window))
        self.assertIn('Action required', window.activity_title.text())
        window.auth_entry.setText('12345')
        window.submit_auth()
        self.assertEqual(replies.get_nowait(), '12345')
        self.assertTrue(window.auth_panel.isHidden())
        window.worker = None
        window.close()

    def test_mobile_auth_guidance_visible_during_steam_login(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        window.start_activity('download')
        window.show_progress({'stage': 'authenticate', 'auth_state': 'waiting', 'message': 'Steam sign-in started.'})
        self.assertTrue(window.mobile_help.isHidden())
        self.assertTrue(window.auth_hint_timer.isActive())
        window.show_progress({'stage': 'authenticate', 'auth_state': 'mobile', 'message': 'Approve the login in Steam.'})
        self.assertFalse(window.mobile_help.isHidden())
        self.assertIn('mobile app', window.mobile_help.text())
        self.assertIn('check your phone', window.activity_title.text())
        window.prompt('steam_guard')
        self.assertTrue(window.mobile_help.isHidden())
        window.finish_activity(False, 'Authentication failed')
        self.assertTrue(window.mobile_help.isHidden())
        window.close()

    def test_failed_steam_download_returns_to_clean_login_with_retry(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        window.worker = SimpleNamespace(action='download')
        window.UsernameEntry.setText('sample_user')
        window.PasswordEntry.setText('sample_password')
        window.start_activity('download')
        window.pages.hide()
        window.set_activity_centered(True)
        window.failed({'error_code': 'AUTH_UNCONFIRMED', 'message': 'SteamCMD returned without a confirmed login.'})
        window.reset()
        self.assertEqual(window.pages.currentIndex(), 1)
        self.assertTrue(window.activity.isHidden())
        self.assertTrue(window.error_banner.isVisibleTo(window))
        self.assertTrue(window.pages.isVisibleTo(window))
        self.assertEqual(window.UsernameEntry.text(), 'sample_user')
        self.assertFalse(window.PasswordEntry.text())
        self.assertFalse(window.SubmitButton.isEnabled())
        self.assertIn('SteamCMD returned', window.error_banner.text())
        window.worker = None
        window.close()

    def test_failed_deploy_returns_to_ready_page(self):
        from PyQt5.QtWidgets import QApplication
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        window = Window(parser().parse_args([]))
        window.worker = SimpleNamespace(action='deploy')
        window.failed({'error_code': 'DEPLOY_INTERRUPTED', 'message': 'Write interrupted'})
        window.reset()
        self.assertEqual(window.pages.currentIndex(), 2)
        self.assertTrue(window.activity.isHidden())
        self.assertTrue(window.error_banner.isVisibleTo(window))
        window.worker = None
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

    def test_cleanup_prompt_is_opt_in_after_success(self):
        from unittest.mock import patch
        from PyQt5.QtWidgets import QApplication, QMessageBox
        from folon_downgrader.qt import Window
        from folon_downgrader.cli import parser
        app = QApplication.instance() or QApplication([])
        for answer in (QMessageBox.No, QMessageBox.Yes):
            window = Window(parser().parse_args([]))
            window.worker = SimpleNamespace(action='deploy')
            window.succeeded({'ok': True})
            with patch.object(QMessageBox, 'question', return_value=answer) as prompt, patch.object(window, 'run') as run:
                window.reset()
                prompt.assert_called_once()
                if answer == QMessageBox.Yes:
                    run.assert_called_once_with('cleanup-downloads')
                else:
                    run.assert_not_called()
                window.reset()
                prompt.assert_called_once()
            window.worker = None
            window.close()
