import os
import unittest
from unittest.mock import patch

from folon_downgrader.qt_platform import configure_display


class DisplaySelectionTests(unittest.TestCase):
    def test_gnome_wayland_uses_native_backend(self):
        with patch('sys.platform', 'linux'), patch.dict(os.environ, {
            'XDG_CURRENT_DESKTOP': 'GNOME', 'XDG_SESSION_TYPE': 'wayland',
            'WAYLAND_DISPLAY': 'wayland-0', 'DISPLAY': ':0',
        }, clear=True):
            configure_display()
            self.assertEqual(os.environ['QT_QPA_PLATFORM'], 'wayland')

    def test_preserves_explicit_platform(self):
        for backend in ('offscreen', 'xcb', 'wayland', 'wayland;xcb'):
            with self.subTest(backend=backend), patch('sys.platform', 'linux'), patch.dict(os.environ, {
                'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
                'QT_QPA_PLATFORM': backend,
            }, clear=True):
                configure_display()
                self.assertEqual(os.environ['QT_QPA_PLATFORM'], backend)

    def test_leaves_other_sessions_to_qt(self):
        for platform, env in (
            ('win32', {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0'}),
            ('linux', {'XDG_SESSION_TYPE': 'x11', 'DISPLAY': ':0'}),
            ('linux', {'XDG_SESSION_TYPE': 'x11', 'WAYLAND_DISPLAY': 'wayland-0'}),
            ('linux', {'XDG_SESSION_TYPE': 'wayland'}),
            ('linux', {}),
        ):
            with self.subTest(platform=platform, env=env), patch('sys.platform', platform), patch.dict(os.environ, env, clear=True):
                configure_display()
                self.assertNotIn('QT_QPA_PLATFORM', os.environ)
