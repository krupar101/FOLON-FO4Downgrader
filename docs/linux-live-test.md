# Linux live validation — 2026-11-01

This is an incremental test record, not a release certification.

## Baseline and backup

- Clean Steam Fallout 4 installation on a secondary Btrfs Steam library.
- Executable version read by the packaged app: **1.11.240.0**.
- Steam build ID: **24564252**; appmanifest StateFlags: **4**.
- Six DLC masters present: Automatron, Far Harbor, Nuka-World and Workshop 1–3.
  Presence is not proof of entitlement or complete DLC integrity.
- Independent Btrfs reflink backup includes the game, appmanifest and Proton prefix.
  **971 regular files / 40,713,320,450 bytes** were compared with SHA-256;
  **1,381 symlinks** were preserved without following external targets.
- At preflight, the live executable and appmanifest hashes still matched that backup.

## Packaged application checks

- Automatic Steam library discovery returned the correct secondary-library game path.
- Explicit-path preflight succeeded on the actual host (with host process visibility).
- Target version is 1.10.163.0; bundled inventory remains incomplete.
- Dedicated test SteamCMD, staging and rollback directories are separate from the
  game and the clean baseline backup. Approximately 300 GiB remained free.
- Packaged `--setup-steamcmd` succeeded; game files were not modified.
- Packaged GUI launched on the real desktop with the test paths preselected.

## Pending

User-driven account login, Steam Guard and all 14 depot downloads have now succeeded.
Passwords/codes must remain in the application, not in this report or chat.
Deployment and rollback passed on a disposable copy as recorded below. Game
launch, Steam Deck and Windows validation remain pending. The bundled inventory
verification gate remains enabled.

## First login attempt: startup parser regression

The GUI stopped before Steam Guard or a depot-download message, reporting
DEPOT_DOWNLOAD_FAILED. A fresh unauthenticated SteamCMD installation reproduced
optional ILocalize::AddFile translation warnings containing the word "failed"
while SteamCMD exited 0. The old classifier incorrectly marked that successful
startup as a download failure.

The classifier now matches explicit error records rather than bare "failed"
substrings. Real failures still stop the workflow; file verification remains
mandatory. Error messages identify startup/login/depot-download phases without
exposing raw backend output. A piped fake SteamCMD test includes the startup
warning before login, and separate regression tests cover account names with
"failed", nonzero exit status, and error messages following Steam Guard chatter.
The startup fix passed 35 local tests. The subsequent authenticated retry succeeded.

## Download inventory verification

- User completed mobile approval; GUI confirmed all 14 pinned depot downloads.
- All 117 file records (116 distinct paths, 38,901,837,727 bytes across depots)
  match cached Steam manifest sizes and SHA-1 values. SHA-256 values are recorded
  in `manifests/fo4-1.10.163.0-en.candidate.json`.
- All 14 cache payload CRC checks passed; IDs match the pinned release matrix.
  Cache signature verification is explicitly not claimed.
- Downloaded executable version: **1.10.163.0**. Active installed executable
  still matched the clean baseline at the start of the deployment rehearsal.
- `Data/Fallout4 - Meshes.ba2` differs between depots 377161 and 377163. The
  candidate explicitly selects 377163, matching the pinned community reference.
- The current official depot manifest confirms all 51 exact CC cleanup paths.
  26 downloaded CC files remain subject to download integrity verification but
  are excluded from deployment. Cleanup is journaled/restoreable, not wildcard.
- Candidate remains disabled for general deployment; a separate local manifest
  enables only the disposable-copy rehearsal. The active installation and clean
  baseline backup are outside that rehearsal's game/staging/rollback roots.
- 46 local tests pass, including cache framing/truncation/CRC checks and
  deployment exclusion/cleanup rollback regressions.

## Disposable-copy deployment and rollback

The retained report in
`FOLON-Testing/deployment-rehearsal-qqgla12c/rehearsal-report.json` records a pass.
The rehearsal used a separate Steam library copied from the clean backup and a
local test manifest; it did not deploy into the active Steam installation.

- Deployment completed with 90 installed files verified by SHA-256 and executable
  version **1.10.163.0**.
- Rollback completed and restored executable version **1.11.240.0**.
- All **143 game files** in the restored tree were SHA-256 checked against the
  baseline; the file set matched. This is a content check, not a claim that all
  filesystem metadata was restored.
- On follow-up, the active installation's executable and appmanifest still
  matched the clean backup by SHA-256.
- Deployment/rollback results, staging and rollback data remain in the rehearsal
  directory. No game launch was performed.

Next validation is a downgraded-game launch through Proton, followed by testing
the packaged GUI with the reviewed inventory. The bundled inventory remains
disabled; this rehearsal alone does not establish Windows or Steam Deck support.
