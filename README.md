# Downgrader 2.0

Version **2.0.0 by FOLON Team**. The same Python/Qt application runs on Windows
x64 and Linux x86-64, with an AppImage for Linux. It downgrades Steam Fallout 4
to **1.10.163.0**; it does not install Fallout: London or configure Proton.

The bundled English inventory covers all 14 pinned depots, with 117 verified
file records, 90 selected installation files and an exact 51-file Creation Club
cleanup list. It was checked against authenticated SteamCMD downloads and cached
Steam metadata, then exercised on a disposable installation. Deployment is enabled.
End-to-end Windows/Linux game testing is ongoing; no release has been published.
See [validation status](docs/validation.md) for evidence and remaining tests.

## Run

Downloaded builds include Python and Qt. Open `Downgrader-2.0.exe` on Windows,
or make the Linux AppImage executable and open it. Both launch the same GUI.
Linux additionally needs the native SteamCMD 32-bit runtime; see [Linux notes](LinuxDeps.md).

For development, use Python 3.12 or newer:

```sh
python -m venv .venv
# Linux:
. .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python FOLON-Downgrader.py
```

The original folder, Steam login, downgrade and completion pages are shared.
SteamCMD input is piped from the GUI; credentials are not written to the command
line or generated scripts. SteamCMD itself owns private logs/session files, and
real-account authentication remains a release gate. No runtime font download is
required. Overseer falls back to the system font if unavailable.

## Optional diagnostics

```sh
python FOLON-Downgrader.py --discover
python FOLON-Downgrader.py --game-path "/library/steamapps/common/Fallout 4" --preflight --json
python FOLON-Downgrader.py --game-path "/library/steamapps/common/Fallout 4" --verify-download
python FOLON-Downgrader.py --game-path "/library/steamapps/common/Fallout 4" --verify-only
```

`--staging-root`, `--steamcmd-root`, `--state-root` and `--content-root` let you
select separate writable locations, including secondary drives. Defaults are in
`%LOCALAPPDATA%/FOLON-Downgrader` or `$XDG_DATA_HOME/folon-downgrader`
(`~/.local/share/folon-downgrader` if unset). The game stays in its Steam library.
SteamCMD downloads into its own content tree. Deployment uses those files directly,
without a second staging copy. Downloads are hash-verified once per app session;
changed files or a restarted app require fresh verification. Copying checks hashes
in a bounded 1 MiB buffer, and the installed files are verified afterward. Allow
space for downloads, any installation growth and one temporary replacement file.

`--deploy --yes` explicitly confirms modifying the supplied `--game-path`.
The tool does not create game backups or offer restoration. A small transaction
record tracks progress; an interrupted downgrade can be retried using the retained
downloads. Steam can restore the current game through its own file verification.

After a successful, verified downgrade, the GUI asks whether to remove downloaded
game files. Keeping them is the default. Cleanup removes only inventory-listed
depot files, leaving the installed game, SteamCMD and unrelated files intact.
Failed or cancelled downgrades keep their downloads for retrying.

The GUI asks before requesting Steam's normal shutdown and waits for it to exit.
It never force-kills Steam. CLI deployment requires Steam to be closed manually.
CLI download uses interactive SteamCMD; normal GUI use does not need a terminal.

There is no wildcard CC/HD deletion and no automatic Steam update blocking.
Only exact removals in a reviewed manifest are applied. Saves,
Proton configuration, launchers and unrelated mods are outside the engine's scope.

## Develop

```sh
python -m unittest discover -s tests -v
```

Tests use synthetic files and fake SteamCMD processes. They never download games
or require personal Steam accounts. [Build instructions](build.md),
[source audit](docs/source-audit.md), and [original engineering plan](docs/windows-linux-plan.md).
The plan's CLI-first Linux proposal is superseded by the shared-GUI requirement.

Original upstream: [Fallout-London/FOLON-FO4Downgrader](https://github.com/Fallout-London/FOLON-FO4Downgrader).
See the MIT [license](LICENSE). Thanks to the original Team FOLON contributors,
SteamRE, and the referenced community implementations. This development branch
has not been endorsed or released by Team FOLON.
