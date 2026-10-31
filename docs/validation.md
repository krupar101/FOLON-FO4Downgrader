# Validation and remaining release gates

Status as of 2026-11-01. This is an implementation branch, not a certified release.
The original user plan remains in `windows-linux-plan.md`; later user decisions
require the same existing Qt UI on both platforms, with a Linux AppImage.

## Demonstrated locally

- `STATIC_SOURCE_REVIEW`: pinned baseline, full independent Linux script and
  targeted zerratar backend/manifest source reviewed; hashes in `source-audit.md`.
- `UNIT_PASS` / `MOCK_INTEGRATION_PASS`: synthetic missing executable/tree,
  missing/corrupt files, archive traversal/links, nondefault Steam libraries,
  explicit conflict resolution, process failures, cancellation, per-game locking,
  shared engine exception stop, missing manifest gate and target version mismatch.
- Deployment fault injection: disk-full mid-deploy and crash between file replace
  and journal update; fresh transaction object restores original file bytes;
  corrupt backups and subsequent user edits stop rollback before writes.
- Candidate inventory: depot IDs/counts are checked in Steam text exports;
  generation cannot turn on `inventory_complete`.
- GUI: four original FOLON page layouts construct offline; failed engine results
  do not advance pages. Fake piped SteamCMD prompts exercise username/password and
  per-depot completion; synthetic secret output is absent from emitted UI events.
- Native Linux SteamCMD bootstrap and anonymous stdin session succeeded. This
  proves bootstrap/transport only, not personal-account Steam Guard/depot access.

## Not demonstrated / release-blocking

| Area | Remaining work |
|---|---|
| Release metadata | Authenticated exports/downloads for all 14 depots, trustworthy full inventory, explicit overlapping-file ownership, exact recoverable cleanup list, independent target validation |
| Real authentication | Windows and Linux password/mobile approval/email/code flow validation; unexpected prompts and localized output; review SteamCMD-owned session/log persistence |
| Safety breadth | Full T01–T26 matrix, real process-death/cancel timing, Windows reparse-point tests, filesystem/power-loss tests and per-volume space estimates on actual installations |
| Preflight | Complete DLC entitlement/build evidence and library/runtime diagnostics; richer game/Steam process handling |
| Recovery UX | Selective depot repair and richer journal-driven resume; current interrupted deployment requires rollback, never blind continuation |
| Platforms | Windows 10/11, representative Linux desktops and Steam Deck internal SSD/microSD end-to-end tests |
| Packaging | Windows native artifact test, target-distro AppImage runs, full hash locks, pinned CI action SHAs, reproducibility/provenance and signing |
| Diagnostics | Reviewed exportable redacted support bundle; current results contain selected local paths and fixed messages, never raw backend output |

The tests are meaningful implementations of several plan cases; the test count
must not be described as completion of every numbered T01–T26 acceptance case.
No Windows device, Linux full-downgrade or Steam Deck certification is claimed.

## Current operational limitations

- Deployment is disabled by the bundled `inventory_complete: false` contract.
- Download completion requires per-depot SteamCMD success in GUI mode, then the
  trusted file verifier. Unknown/failed authentication never advances to deploy.
  The interactive CLI spike relies on final file verification and exit status;
  raw terminal authentication/output has not been certified as a release interface.
- GUI input is ephemeral in this Python app; raw SteamCMD output is never emitted
  to its GUI/logs. Backend-owned logs/cache are not isolated or certified secret-free.
- Native SteamCMD runtime dependencies remain external to the GUI AppImage.
- Staging/backup retention is deliberate. Automatic cleanup never removes the only
  rollback copy. Interrupted deployment recovery is rollback-first.
- Journal/manifest files are local trusted inputs, not signed remote policy. The
  path checks are conservative but are not protection against a privileged attacker
  racing filesystem operations. Do not deploy into concurrently modified installs.
- Old Utility.py/loading helpers are retained for source compatibility but are not
  imported by the shared application; legacy mutation flows are no longer reachable
  from either entry point. Their replacement should not be called a minimal hotfix.

## Build evidence

The local build host uses Python 3.14.8, Fedora-family Linux and glibc 2.43. A local
AppImage is a development/host smoke-test artifact, not proof of portability to
SteamOS. CI uses Python 3.12 on Windows 2022 and Ubuntu 22.04; these workflows are
prepared but have not been executed by this local session. No release was published.

Local result: **31 tests passed**, including the Qt offscreen smoke test. The
49 MiB development AppImage built successfully, `--help` exited 0, and its default
GUI stayed running for the offscreen startup test until deliberately terminated.
Artifact: `dist/FOLON-Downgrader-x86_64.AppImage`.
SHA-256: `fbf863e677e12bc725b064dcfadbe9a79179b457ba64699c6448f7966eb0cc93`.
No real game was downgraded by this session. Development work is on
`fix/cross-platform-downgrader` for review; publishing this branch is not a release.

Folder-chooser rendering fix: transparent styling is now limited to wizard page
surfaces. The Qt folder chooser uses an opaque dark background and explicit text/
selection colors. Its source-rendered dialog was visually inspected offscreen
(background alpha 255); the rebuilt AppImage passed GUI startup and all 31 tests.
Actual desktop compositor behavior still needs confirmation on the affected system.

Follow-up folder-header fix: removed inherited wizard padding from file-dialog
internal widgets and gave header sections explicit spacing. Visually checked the
chooser at a compact window size; header viewport fits its font metrics without
vertical clipping. Rebuilt the AppImage with this stylesheet.
