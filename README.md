# FOLON Fallout 4 Downgrader — Windows and Linux development branch

One Python engine and the original FOLON Qt pages on Windows x64 and Linux x86-64.
The Linux release format is an **AppImage opening the same GUI as Windows**.
macOS is out of scope. This tool downgrades Steam Fallout 4; it does not install
Fallout: London, configure Proton, or install mods.

**This branch is a development preview, not a finished downgrade release.**
The bundled manifest pins the 14 documented English depots for Fallout 4
1.10.163.0 but lacks a complete trusted file inventory. Real deployment stops with
`MANIFEST_UNVERIFIED` until that inventory is obtained and reviewed. Do not toggle
the flag to bypass review. See [inventory acquisition](docs/inventory.md) and
[validation status](docs/validation.md).

## Run

Downloaded builds include Python and Qt. Open `FOLON-Downgrader.exe` on Windows,
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

`--staging-root`, `--steamcmd-root`, `--backup-root` and `--content-root` let you
select separate writable locations, including secondary drives. Defaults are in
`%LOCALAPPDATA%/FOLON-Downgrader` or `$XDG_DATA_HOME/folon-downgrader`
(`~/.local/share/folon-downgrader` if unset). The game stays in its Steam library.
SteamCMD downloads into its own content tree. Deployment uses those files directly,
without a second staging copy. Downloads are hash-verified once per app session;
changed files or a restarted app require fresh verification. Copying checks hashes
in a bounded 1 MiB buffer, and the installed files are verified afterward. Allow
space for downloads, any installation growth and one temporary replacement file.

`--deploy --yes` explicitly confirms modifying the supplied `--game-path`.
Backups are **off by default**. Select “Keep a backup for restoration” in the GUI
or pass `--backup` to preserve affected original files, requiring additional disk
space. `--rollback --yes` restores that journaled backup. Retain it until no longer
needed. Interrupted deployments with backups require rollback first; without
backups, retry the downgrade or restore the game through Steam. The small
transaction journal is retained even when file backups are disabled.

The GUI asks before requesting Steam's normal shutdown and waits for it to exit.
It never force-kills Steam. CLI deployment requires Steam to be closed manually.
CLI download uses interactive SteamCMD; normal GUI use does not need a terminal.

There is no wildcard CC/HD deletion and no automatic Steam update blocking.
Only exact removals in a reviewed manifest are applied; backups follow your selected option. Saves,
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
