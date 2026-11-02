"""Choose the native Linux display backend before QApplication starts."""
import os
import sys


def configure_display():
    # Qt 5 defaults to XWayland on GNOME, even in a Wayland session. Avoid
    # that GLX path when the session supplies a native Wayland display.
    # Keep explicit selections (including offscreen for CI) and X11 defaults.
    if (sys.platform == 'linux'
            and not os.environ.get('QT_QPA_PLATFORM')
            and os.environ.get('XDG_SESSION_TYPE', '').lower() == 'wayland'
            and os.environ.get('WAYLAND_DISPLAY')):
        os.environ['QT_QPA_PLATFORM'] = 'wayland'
