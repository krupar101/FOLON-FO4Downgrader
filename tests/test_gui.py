import importlib.util
import os
import unittest

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
        self.assertEqual(window.PasswordEntry.echoMode(), window.PasswordEntry.Password)
        window.failed({'error_code': 'DEPOT_INCOMPLETE', 'message': 'Missing file', 'rollback_required': False})
        self.assertEqual(window.pages.currentIndex(), 0)
        window.close()
