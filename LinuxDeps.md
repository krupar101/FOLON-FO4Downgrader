# Linux and Steam Deck

The AppImage bundles Python, the shared FOLON GUI and Qt. It does **not** turn
Windows Fallout 4 into a native Linux game: select its Steam library directory;
Proton remains Steam's responsibility. No sudo or immutable-system changes are
part of the application workflow.

SteamCMD is Valve's native Linux x86 backend and still requires a compatible
32-bit glibc loader (`/lib/ld-linux.so.2`) and its runtime libraries. Missing loader,
missing executable and noexec/permission problems produce typed errors. The
current preflight checks the loader, not every library version; startup may expose
additional missing libraries. Do not claim SteamOS support until device tests pass.

Steam paths are read from native/Flatpak Steam roots and `libraryfolders.vdf`.
This supports mounted microSD/secondary libraries through their registered paths;
missing or ambiguous installations require explicit selection. Steam root symlinks
are resolved, but managed game-file symlinks/junctions are rejected.

AppImage portability depends on the build baseline and host graphics libraries.
The local build is a development artifact on a newer Fedora/glibc host. Use the
Ubuntu 22.04 CI build for a broader baseline, then test actual target distributions.
FUSE-less launch can be tried with `--appimage-extract-and-run`; availability and
space must be verified on Steam Deck. No Gaming Mode integration is claimed.

On a Wayland session with `WAYLAND_DISPLAY` set, the GUI selects native Wayland.
This avoids Qt 5's GNOME default of using XWayland and its GLX graphics path.
Explicit `QT_QPA_PLATFORM` settings are respected; X11 sessions keep Qt's default.
For older AppImages that report `Ignoring XDG_SESSION_TYPE=wayland on Gnome`
followed by a GLX error, test native Wayland explicitly:

```sh
QT_QPA_PLATFORM=wayland ./FOLON-Downgrader-2.0.0-Linux-x86_64.AppImage
```

If it still crashes, retain the terminal output and report the desktop, graphics
hardware/driver and AppImage version. A GLX error identifies the failing graphics
path; it does not by itself establish the cause of every resize/workspace crash.
