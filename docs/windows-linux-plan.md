# FOLON Fallout 4 Downgrader: Windows + Linux Engineering Fix Plan

**Document:** implementation and validation plan, v1.0  
**Date:** 2026-10-31  
**Target:** one maintained codebase and common downgrade engine, shipped for **Windows 10/11 (x64)** and **Linux x86-64**, including **Steam Deck / SteamOS** as an explicitly tested Linux profile.  
**Out of scope:** macOS; full Fallout: London installation; GOG Fallout 4 downgrading (not required by the standard Steam route); Vortex/MO2 installation support; third-party mod troubleshooting.  
**Status:** source-informed engineering proposal. **No patch has been built, executed, or proven to work on a user's machine.**

> **Executive decision:** do not merely compile the legacy Windows UI on Linux. Keep Python and SteamCMD if they pass the required verification tests; extract the Steam downgrade workflow into a shared, headless core and give Windows and Linux separate adapters for paths, SteamCMD bootstrap and packaging. Build the same tested core into a native Windows executable and a Linux executable/launcher. Steam Deck is a Linux installation target, not a third operating-system codebase.

---

## 1. Source evidence, applicability, and unresolved questions

### Sources reviewed

| Source | Status | What it supports |
|---|---|---|
| Team FOLON repository: https://github.com/Fallout-London/FOLON-FO4Downgrader | Public repository reviewed at `main`; **exact commit not pinned** | Existing Python application, Windows UI and Linux CLI, SteamCMD use, packaging and archival note |
| `WindowsDowngrader.py` | Source inspected | `SetupSteam`, `Install`, progress and workflow transitions, SteamCMD script/credentials, `MoveFiles` invocation |
| `LinuxDowngrader.py`, `Run.sh`, `FOLON-Downgrader.py` | Source inspected | Legacy Linux CLI, SteamCMD bootstrap, direct file move, recursive prompts, executable paths, Linux `--linux` entry |
| `Utility.py` | Source inspected | `MoveFiles(srcdir,dstdir)` directly moves nested files then removes source; no transaction journal |
| Maintainers' issue #32: https://github.com/Fallout-London/FOLON-FO4Downgrader/issues/32 | Public issue reviewed | Post-install file verification is already a recognized improvement proposal |
| Community repository: https://github.com/krupar101/f4london_steam_deck_ini | Repository and related `fallout.sh` content reviewed | A Linux/Steam Deck ecosystem exists with Steam library, microSD, SteamCMD, Proton, and update-path concerns |
| User-specified `FOLON_Linux_Downgrader.sh`: https://raw.githubusercontent.com/krupar101/f4london_steam_deck_ini/refs/heads/main/FOLON_Linux_Downgrader.sh | **File exists in repository listing; its raw body could not be fetched reliably during this review** | The file is a *required input* for detailed migration; **no exact behavior, command or security claim about this script is made without a pinned copy** |
| Two supplied Windows exception screenshots | Visually examined in conversation | `Install()` -> `subprocess.Popen` -> WinError 2; `MoveFiles()` -> missing `.../SteamFiles/steamapps/content/app_377160` -> WinError 3 |
| Supplied Team FOLON Discord support/solutions captures | Previously reviewed | Steam Guard problems, rate limiting, incorrect paths, SSL/TLS, stalled counters, incomplete depot downloads, traceback errors |

**Version caveat:** GitHub `main` content and the current download backend may change. Before implementation, pin exact upstream commits, hashes, supported Fallout 4 build, Steam app/depot manifest source, and supported release. The historical FOLON Steam route uses Fallout 4 app ID `377160` and pre-next-gen build `1.10.163.0`; treat these as a *release-specific manifest entry*, not arbitrary perpetual constants.

**Important limitation:** This is a specific plan for improving the **Steam Fallout 4 downgrader**. It does not establish native Linux Fallout: London support or replace the separate FOLON installer, Heroic/GOG installation, Proton setup, launch-configuration edits, or Steam Deck optimization scripts. Preserve those boundaries in the UI and documentation.

### What the existing code actually demonstrates

1. Windows `SetupSteam()` tests whether `<Fallout4>/SteamFiles` **directory** exists, not whether a working `steamcmd.exe` exists. Interrupted bootstrap can leave the folder without the executable (WinError 2 candidate).
2. Windows `Install()` constructs `<Fallout4>/SteamFiles/steamcmd.exe` but starts `+runscript ./DepotsList.txt` without an explicit `cwd` for that subprocess. The script is written into the SteamFiles folder; the relative argument is fragile.
3. Windows `Install()` writes `login "<username>" "<password>" [code]` into `DepotsList.txt`. This creates plaintext credential exposure and special-character parsing risks.
4. SteamCMD download advancement is insufficiently conditional on **verified expected depot contents**; subsequent `MoveFiles()` can access a directory that was never produced (WinError 3 candidate).
5. Windows progress passes `ProgressMax=117` for download and move operations. This value is not derived from a trusted completion manifest.
6. Worker-thread exception handling and progression are not a reliable single **success-only** contract; an exception should never trigger later deployment.
7. `Utility.MoveFiles()` mutates the real game installation directly and removes the source directory; it does not provide transaction journaling, rollback or recursive integrity proof.
8. Legacy Linux `LinuxDowngrader.py` removes an existing `SteamFiles` directory at startup, passes credentials as SteamCMD command arguments, includes recursive `Linux()` prompts, assumes `SteamFiles/linux32/steamapps/content/app_377160`, and begins moving files without a complete depot-validation gate.
9. Linux README/`Run.sh` still describe a Linux path, but existence of a script **does not prove current compatibility** on modern Linux or Steam Deck.

These are **static findings and plausible causal mechanisms**. To assert an actual bug fix, reproduce with a captured baseline and then pass the matching regression test after implementation.

---

## 2. Goals and non-goals

### Goals (release-blocking)

- One **shared** downgrade algorithm and manifest/validation contract for Windows and Linux.
- A Windows x64 downloadable binary and a Linux x86-64 downloadable application with **no requirement to install Python manually**. Prefer CLI as the first stable Linux surface; optionally share a Qt GUI after engine stabilization.
- Steam Deck/SteamOS support demonstrated through real-device tests, with secondary library/microSD and Proton path discovery explicitly covered.
- Handle authentication challenges, missing executable/downloads, interrupted operations and filesystem errors with typed, actionable errors **rather than Python tracebacks**.
- Never begin modifying Fallout 4 unless all required source files are present and validated.
- Preserve an existing install if a downgrade fails; support tested rollback when deployment is interrupted.
- No Steam credentials, Steam Guard codes or tokens in persistent scripts, diagnostic logs, telemetry, temporary build artifacts or crash dialogs.
- Show success only after verifying the target executable and release-specific expected content.
- Make the game root, staging root and SteamCMD install root independent, configurable and clearly reported.

### Non-goals (avoid scope creep)

- Rewriting SteamCMD or bypassing Steam's authentication/rate limiting/TLS rules.
- Claiming to repair every possible Steam CDN, OS certificate, disk or account problem.
- Installing Fallout: London itself, Heroic, game-specific performance mods or modifying Proton launchers in the downgrader core.
- Running SteamOS-specific `fallout.sh` steps as hidden downgrader side effects.
- Automatically deleting user saves, INIs, third-party mods or arbitrary Creation Club content. Any required official cleanup must be explicitly allowlisted and recoverable.
- Advertising Linux ARM64 until SteamCMD, packaging and target-game path compatibility are independently proven; initial Linux release is x86-64 only.
- macOS support.

---

## 3. Proposed architecture

```text
Windows exe / Qt GUI      Linux executable / CLI       (optional Linux Qt GUI)
         \                        |                         /
          \---------------- shared application API --------/
                                |
                downgrade_core (platform-neutral)
                ├── task/state engine
                ├── game/manifest validator
                ├── SteamCMD command runner + auth adapter
                ├── depot inventory/hash verifier
                ├── staging/resume journal
                ├── deploy/rollback transaction manager
                ├── structured errors and redacted diagnostics
                └── progress event interface
                                |
                 platform_services / adapters
                ├── Windows: Steam libraries, paths, subprocess,
                │            permissions, executable version
                └── Linux: Steam libraries, native SteamCMD,
                             Steam Deck / SteamOS mounts, Proton paths
```

**Suggested repository structure (not a requirement to over-fragment):**

```text
src/folon_downgrader/
    core/{state,models,manifest,steamcmd,verification,deployment,errors,logging}.py
    platforms/{windows,linux,steam_library}.py
    ui/{cli,qt}.py
    cli.py
manifests/<supported-release>.json
tests/{unit,integration,fixtures,system}/
packaging/{windows,linux}/
.github/workflows/{test,build,release}.yml
```

### Typed API (suggested)

```python
@dataclass(frozen=True)
class DowngradeRequest:
    game_root: Path
    staging_root: Path
    steamcmd_root: Path
    target_manifest_id: str
    platform: Literal["windows", "linux"]
    dry_run: bool = False

class Stage(Enum):
    PREFLIGHT = "preflight"
    BOOTSTRAP_STEAMCMD = "bootstrap_steamcmd"
    AUTHENTICATE = "authenticate"
    DOWNLOAD = "download"
    VERIFY_DOWNLOAD = "verify_download"
    PREPARE_DEPLOYMENT = "prepare_deployment"
    DEPLOY = "deploy"
    VERIFY_TARGET = "verify_target"
    COMPLETE = "complete"

@dataclass(frozen=True)
class StageResult:
    stage: Stage
    ok: bool
    error_code: str | None = None
    message: str | None = None
```

State transitions are explicit: `PREFLIGHT -> BOOTSTRAP -> AUTH -> DOWNLOAD -> VERIFY_DOWNLOAD -> PREPARE -> DEPLOY -> VERIFY_TARGET -> COMPLETE`. On a failed result the controller transitions to `FAILED`/`CANCELLED`/`ROLLBACK_REQUIRED`, **never** silently to the next stage. `COMPLETE` requires a persisted verification report. UI progress is downstream of real engine events rather than the authority for state.

**Backend decision:** retain SteamCMD for initial implementation because it is already used in both code paths and the community approach. Only replace it after a pinned, legitimate alternative passes authentication, depot and error-contract tests; do not make a rewrite a prerequisite.

---

## 4. P0: Immediate correctness, confidentiality and data-safety fixes

### P0-01. Prevent WinError 2: SteamCMD bootstrap and absolute paths

**Current observed failure:** `FileNotFoundError [WinError 2]` from `WindowsDowngrader.Install()` when invoking subprocess.

**Implementation:**

1. Create a dedicated `SteamCmdProvider.ensure_available()` with platform-specific trusted download URLs, version detection, integrity checks where an authoritative checksum/signature exists, and bounded bootstrap retries.
2. Check the **actual executable**: Windows `steamcmd.exe`; Linux `steamcmd.sh` plus its required loader/binary and 32-bit libraries. An existing directory is *not* a success condition.
3. Keep bootstrap in a dedicated cache under a writable application-data/staging directory, rather than assuming the game root can store tools.
4. Launch with an **absolute executable path**, `cwd=steamcmd_root` and an absolute script/input path where supported.
5. On missing executable, show `STEAMCMD_NOT_FOUND` with expected location and `Retry setup`; on blocked extraction/permissions, show distinct codes and affected path.
6. Do not use `shell=True`; validate installed backend and error out safely if bootstrap incomplete.

**Proof:** recreate a `SteamFiles` directory without `steamcmd.exe`, rerun preflight, and confirm repair or a clean error. Launch from a completely unrelated current working directory and one containing Unicode/spaces. Never show an uncaught traceback.

### P0-02. Prevent WinError 3: validate expected depot tree before moving

**Current observed failure:** `FileNotFoundError [WinError 3]` for `<game-root>/SteamFiles/steamapps/content/app_377160` inside `MoveFiles()`.

**Implementation:**

1. Resolve the **actual SteamCMD content root from backend output and verified stage configuration**, not from an assumed single `linux32` or Windows path. A platform adapter may offer expected candidate roots but the chosen path must pass validation.
2. Capture SteamCMD exit code **and** recognized per-depot failure records. Do not treat absence of a recognized failure string as success.
3. Generate expected depot IDs/files from a **pinned and reviewed version manifest**, not a guessed total (`117`) or only a root directory's existence.
4. Before deployment, verify every required depot exists and its expected files have correct sizes/hashes where trustworthy reference values are provided. When full hashes are unavailable, require stricter evidence of required files and record verification level; never claim cryptographic integrity without hashes.
5. If anything is missing: stop; report `DEPOT_TREE_MISSING`, `DEPOT_INCOMPLETE` or `DEPOT_HASH_MISMATCH`, preserve downloaded files for repair, and permit selective retry.

**Proof:** fake SteamCMD `0` exit with missing `app_377160`, empty depot directory, and one incomplete depot: all fail **before the first game-directory write**. The user's WinError 3 must become a readable download-verification error, not an exception.

### P0-03. Replace "success unless recognized error" handling

- Use `SteamCmdRunResult` containing process exit, bounded stdout/stderr observations, recognized authentication status, expected-depot postconditions, execution time, cancellation state and classified errors.
- Treat a zero return code as **necessary but not sufficient**.
- Handle nonzero return, nonmatching/unexpected output, per-depot failure, certificate failure, rate limit, Steam Guard prompt, and timeout separately.
- Replace `@ShutdownOnFailedCommand 0` behavior or compensate with explicit command-by-command verification. Test the effect of any SteamCMD flag change; do not assume the flag alone enforces all depots.
- Downstream code must require `result.ok && verified_download_manifest`.

**Proof:** scripted fixtures for all output/result combinations; no unexpected text can authorize deployment.

### P0-04. Secure Steam authentication, logs and temporary files

**Current risk:** Windows writes credentials into `DepotsList.txt`; Linux passes credentials in process arguments. Do not claim that deletion alone eliminates exposure.

**Implementation choices (validate the actual SteamCMD-supported interfaces first):**

1. Prefer a SteamCMD-supported authentication flow reusing a legitimate session or interactive prompt, without storing username/password in scripts or command-line arguments. **Spike and verify** whether the backend can perform all required depot downloads this way on Windows and Linux.
2. If SteamCMD requires input via a file or argument on a target platform, document the limitation, reduce lifetime and exposure, use restrictive temporary permissions, redact all persisted outputs, and **do not call the risk fully solved**. Decide release acceptance against this remaining threat.
3. Never log or transmit secrets; clear input widgets after use; disable automatic crash dumps containing credentials where feasible; use a dedicated redaction pipeline on logs and exceptions.
4. Treat Steam Guard mobile approval, mobile code and email code as distinct challenge states; support cancel, retry, pending approval and rate-limit cooldown. Do not bypass Steam security.
5. Avoid leaking secrets through CI, command preview dialogs, exception stack locals or `ps`/Task Manager process lists.

**Proof:** synthetic secret strings with spaces, double quotes, backslashes and Unicode do not appear in retained script, process command line (where supported), logs, error UI or support bundle. Real authentication is tested with a dedicated authorized test account and no saved credentials in test artifacts.

### P0-05. Make game deployment recoverable

**Current risk:** `Utility.MoveFiles()` moves data directly into the game and removes its source; a later failure can leave an incomplete installation.

1. Download to durable staging separate from the target. Never mutate Fallout 4 during download.
2. Build a transaction plan listing each destination and existing-file backup; confirm sufficient free space for staged files, rollback and destination.
3. Back up each file that will be overwritten to a controlled rollback directory on the same relevant filesystem when practical; record SHA-256, size, destination and restoration information.
4. Restrict operations to allowlisted paths inside the validated Fallout 4 root. Reject symlink/junction/path-traversal escapes, conflicting files and ambiguous target root. Prefer `Path.resolve()`/`realpath()` boundary checks with platform-specific reparse-point handling.
5. Commit files using a copy-then-verify-then-atomic-replace pattern when supported, journaling each step. Do not assume directory-tree operations are atomic, especially across drives.
6. If interrupted, offer **resume or rollback** based on a durable journal; never delete the only valid backup automatically.
7. Creation Club and HD Texture Pack cleanup (where required by the version-matched official downgrade contract) must use explicit lists and backup/restore; no unbounded delete-by-prefix as default.

**Proof:** inject process death/access-denied/disk-full in the middle of deployment; prior game files either remain intact or can be restored via a tested idempotent rollback. Validate rollback bytes/hashes, not only UI success.

### P0-06. Worker exceptions must stop the state machine

- Wrap all worker operations in structured `try/except` that maps errors to `StageResult`; capture sanitized details and stop.
- In Qt, distinguish `succeeded`, `failed` and `cancelled` signals. Do not use generic thread `finished` as semantic success.
- Remove recursive calls as the Linux prompt/error recovery strategy; use iterative state transitions with bounded retries.
- Ensure a stage cannot run twice concurrently (idempotency/lock + stage token).

**Proof:** force exception at every stage; subsequent stage never starts, no unexpected mutation occurs, and the failure message includes exact stage and sanitized diagnostics.

---

## 5. P1: Reliability and cross-platform support

### P1-01. Shared game discovery and preflight

**Windows adapter:** inspect Steam libraries, installed app manifests (`appmanifest_377160.acf`), selected `Fallout4.exe`, actual build and DLC evidence. Support nondefault drives/libraries, folder names with spaces/Unicode, Windows 10/11, OneDrive-managed folders, existing game processes, permissions and sufficient disk space.

**Linux adapter:** inspect Steam library configuration/manifests, the native installed Windows Fallout 4 content (not a hypothetical Linux Fallout 4 binary), Steam Deck internal SSD and removable/microSD Steam library, Flatpak/native Steam path differences where observed, symlinks/mount availability, ext4/btrfs/other tested filesystems, executable permissions and available 32-bit runtime libraries. Keep SteamCMD cache outside read-only/immutable system areas.

**Both:** no game-root write before user confirmation. `--game-path` overrides auto-discovery after validation; ambiguous multi-copy scenarios must prompt selection. Output the resolved paths separately for *game*, *SteamCMD*, *download staging*, *backups*, *Proton prefix* (Linux diagnostic only), *logs*.

**Preflight return fields:** `OS`, `arch`, `storefront` (Steam-only downgrade), `game_root`, `target_build`, `current_build`, `DLC evidence`, `writable`, `temp_space`, `target_space`, `steamcmd_usable`, `game_not_running`, `staging_reusable`.

### P1-02. Review and integrate the independent Linux downgrader

**Mandatory prerequisite:** save the exact contents of `FOLON_Linux_Downgrader.sh` at a pinned Git commit and record SHA-256 and license/permission before copying code. The raw script was **not** reliably retrievable for this document; detailed behavior must not be assumed.

Perform a line-by-line comparison against the legacy `LinuxDowngrader.py` and shared engine:

| Review dimension | Questions to answer before reuse |
|---|---|
| Bootstrap/dependencies | How is SteamCMD obtained; checksums/TLS; 32-bit libraries; shell packages; paths? |
| Authentication | How are login, Steam Guard and retries performed; secrets in logs/processes/history? |
| Depot manifest | Which exact depot IDs/manifest IDs; source/version; completeness proof? |
| Linux Steam paths | How are alternate libraries, Steam Deck/microSD, sandboxed/native clients detected? |
| Download output | Where does SteamCMD place `app_377160`; is `cwd` managed; actual success check? |
| Installation mutation | Which files are overwritten/removed; any checkpoints, backups and rollback? |
| Resume/idempotency | What happens after interruption, repeated run, empty staging or partial depot? |
| Shell safety | Quote every path; strict mode; traps; `mktemp`; trap semantics; avoid `eval` and destructive wildcards |
| Dependencies/licensing | License, attribution, executable prerequisites, safety implications |

**Integration rule:** port verified **behavior** and test fixtures into the common Python core. Keep shell script as a **reference/optional compatibility adapter**, not a second competing source of downgrade manifests or business rules. Do not merge the full Steam Deck installer (`fallout.sh`) into the downgrader: it also performs FOLON installation, Heroic and launcher/INI work.

**Go/no-go:** until the pinned Linux script is fully inspected, Linux-target design can proceed, but a claim of behavior-equivalence to that script is **blocked**.

### P1-03. SteamCMD lifecycle, network and certificates

- Download SteamCMD from Valve's documented source over verified TLS. Download to `.partial`, validate archive shape, then extract to a controlled cache; prevent zip/tar path traversal and symlink escape.
- Use Python standard library or pinned audited libraries. Avoid loading downloaded assets (including optional fonts) as a startup prerequisite; permit an offline fallback theme.
- Identify missing Linux 32-bit loader/libraries and present distro-neutral diagnostics; package what may be redistributed, but do not blindly copy system libraries.
- Timeouts: connect vs no-output vs process-running vs no-network-progress; show which stage is affected. A busy process is not automatically hung.
- Retry only transient errors with backoff/jitter and a ceiling; preserve valid completed downloads. Respect Steam rate limits; do not repeatedly request new login codes in a loop.
- SSL validation must remain enabled. For `CERTIFICATE_VERIFY_FAILED`, report sanitized certificate/trust details and official OS network/trust checks; never implement `verify=False`.
- Capture `stdout` and `stderr` concurrently without deadlocks and redact tokens/passwords before persistence.

### P1-04. Pinned release manifest and depot verification

Use a signed or otherwise verified release-owned manifest such as:

```json
{
  "schema": 1,
  "id": "FO4_PRE_NEXT_GEN_EXAMPLE_ONLY",
  "steam_app_id": 377160,
  "target_exe_version": "1.10.163.0",
  "depot_manifest_source_commit": "PIN_BEFORE_RELEASE",
  "depots": [
    {"id": "AUTHORITATIVE_DEPOT_ID", "manifest": "AUTHORITATIVE_MANIFEST_ID", "required": true}
  ],
  "files": [
    {"path": "Fallout4.exe", "sha256": "PIN_TRUSTED_SHA256_BEFORE_RELEASE"}
  ]
}
```

**The example is a schema sketch, not a valid deployable manifest.** Populate only with authoritative release metadata and verified file hashes. Store the source commit, expected count, supported language/content branch and target version. Include a mechanism to verify required DLC but do not silently replace valid user DLC. Never guess depot IDs or SHA values.

### P1-05. Resume, cancellation, retries and progress

- Persist a journal in an application-owned cache with version, game-root fingerprint, manifest ID/hash, completed-depot IDs and file verification state. Resume only after confirming identity and matching hashes.
- Explicit `--resume`, `--repair`, `--rollback`, `--dry-run`, `--verify-only` commands; all must have well-defined idempotency.
- On Ctrl+C/closing UI, cancel SteamCMD child process tree, stop before unsafe write boundaries and retain resumable staging/rollback journal.
- Progress based on completed *verified tasks*; show indeterminate progress when byte totals are unavailable. Never display `118/117` or arbitrary percentages. Report current depot, bytes/download rate when verifiably available, stage and last activity.
- Allow the user to copy a redacted troubleshooting report even when the UI itself crashes.

### P1-06. Linux UX, Steam Deck integration and packaging

**Minimum Linux deliverable:** a CLI application installable as a self-contained x86-64 release artifact where practical, with `--help`, `--preflight`, `--game-path`, `--resume`, `--verify-only`, `--rollback`, structured output and exit codes. Evaluate PyInstaller one-folder versus a portable Python virtual-environment launcher **against SteamOS realities**; choose only after testing dependencies, dynamic libraries, UI and self-update behavior.

**Steam Deck:** support Desktop Mode and Konsole, internal SSD and microSD Steam libraries, `~/.steam` symlinks, expected Steam client layout, SteamOS read-only system constraints, native SteamCMD and the Windows game's Proton prefix (only when needed for display/diagnostics). Do not require modifying the immutable system partition. Do not claim Gaming Mode desktop integration unless tested.

**GUI choice:** preserve existing PyQt styling on Windows behind the shared core; release Linux CLI first or in parallel. A shared Qt GUI is optional after tests prove the same core and error states. Do not let font/network downloads block startup.

**Linux safety:** do not rely on `sudo` as the normal path; do not disable filesystem protections; avoid `tar.extractall` on untrusted archives without traversal/symlink validation; do not delete SteamCMD staging on every invocation.

### P1-07. Diagnostics and UX

User-facing error object should report:

```text
Error code: DEPOT_TREE_MISSING
Stage: VERIFY_DOWNLOAD
Game folder: <sanitized path or user-approved full path>
SteamCMD folder: <resolved path>
Expected: required Fallout 4 depot content for the selected manifest
Observed: download output root absent
What happened: SteamCMD did not produce the required files
Next action: Retry failed depots / Inspect redacted log / Change staging folder
Game files modified: NO
```

Other codes: `STEAMCMD_NOT_FOUND`, `STEAMCMD_BOOTSTRAP_FAILED`, `GAME_NOT_FOUND`, `WRONG_GAME_BUILD`, `MISSING_DLC`, `AUTH_PENDING`, `AUTH_DENIED`, `RATE_LIMITED`, `NETWORK_TIMEOUT`, `TLS_VERIFY_FAILED`, `DEPOT_DOWNLOAD_FAILED`, `DEPOT_INCOMPLETE`, `HASH_MISMATCH`, `PERMISSION_DENIED`, `INSUFFICIENT_SPACE`, `GAME_RUNNING`, `DEPLOYMENT_FAILED`, `ROLLBACK_FAILED`, `TARGET_VERIFY_FAILED`, `CANCELLED`.

Never display raw stack traces as the primary error message; developers may inspect **sanitized** stack traces in local diagnostic logs.

---

## 6. P2: Maintainability, distribution and documentation

1. Pin dependencies with reproducible environment files and lock/hashes; monitor Qt/Python and SteamCMD integration compatibility.
2. Provide cross-platform version/about UI: **downgrader version**, target Fallout 4 version, SteamCMD platform/build, manifest revision, platform/architecture.
3. Build native artifacts independently on Windows and Linux runners. Do not cross-compile a Windows PyInstaller binary to claim a Linux executable.
4. Add checksums and provenance for release artifacts; consider signing Windows binaries and publication attestation for Linux packages. Never assert signing is present before implementing it.
5. Use a versioned errors/diagnostics contract shared by CLI, Qt UI and docs.
6. Produce clear separate guides for (a) Windows + Steam, (b) Linux desktop + Steam/Proton, (c) Steam Deck + Steam/Proton; include limits and common failures.
7. Add issue templates with error code, distro/Windows version, Steam library path type (redacted), current/target build, precise stage, redacted diagnostics and reproduction steps. Never ask for passwords or Steam Guard codes.
8. Clarify relationship with Team FOLON's archived main repository: get maintainer approval for upstream changes or maintain a clearly labeled fork. Follow repository license and third-party component licenses.

---

## 7. Implementation work packages and dependencies

| ID | Priority | Deliverable | Depends on | Done when |
|---|---|---|---|---|
| W01 | P0 | Pin upstream source snapshots + target manifest contract | None | Immutable source IDs/hashes and manifest evidence recorded |
| W02 | P0 | Typed core state machine + error codes | W01 | No implicit advancement; failure injection tests pass |
| W03 | P0 | SteamCMD executable/bootstrap checker (WinError 2) | W02 | Missing `steamcmd.exe` handled and repaired/diagnosed |
| W04 | P0 | Absolute subprocess paths/cwd and output handling | W02, W03 | Launch works from arbitrary cwd and logs are sanitized |
| W05 | P0 | Verified depot-download gate (WinError 3) | W01, W02, W04 | Missing/incomplete depot blocks any game mutation |
| W06 | P0 | Authentication threat model + safe auth prototype | W04 | Supported Steam Guard states and documented credential exposure |
| W07 | P0 | Staged transactional deployment + rollback | W05 | Forced mid-copy failure can be restored byte-for-byte |
| W08 | P0 | Qt worker success/error/cancel signals | W02 | Exceptions cannot trigger next phase |
| W09 | P1 | Shared Steam library/path discovery + preflight | W01 | Windows and Linux nondefault libraries resolved |
| W10 | P1 | Linux script source pin + feature/security comparison | W01 | Exact `FOLON_Linux_Downgrader.sh` reviewed and mapped |
| W11 | P1 | Native Linux SteamCMD adapter and dependency checks | W02, W04, W09, W10 | Linux CLI works on supported distro, target game untouched on failures |
| W12 | P1 | Persistent resume/repair and truthful progress | W05, W07 | Interrupted download resumes only verified data |
| W13 | P1 | Linux/Steam Deck x86-64 release build | W11, W12 | Installs/runs in tested Linux/SteamOS profile |
| W14 | P1 | Structured diagnostic bundles and documentation | W02, W08, W11 | Redacted useful error codes and support steps |
| W15 | P2 | Linux Qt GUI (optional) | W13 | Shared core, identical stage/error semantics |
| W16 | P2 | CI/release provenance and signed artifacts where available | W01-W14 | Reproducible two-platform pipeline and checksum manifest |

**Recommended order:** W01 → W02 → W03/W04 → W05/W06 → W07/W08 → W09/W10/W11 → W12/W13 → W14/W16. Linux discovery, script audit and core tests can run in parallel, but *do not start Linux release certification before W10 is complete*.

### Suggested delivery increments (no calendar commitment)

- **Milestone A - safe Windows hotfix:** W01-W08; directly prevents the two screenshot traceback families and blocks incomplete installations. Linux source closure W10 can occur alongside.
- **Milestone B - unified engine + Linux CLI:** W09-W13; retire duplicate Linux download/move logic; test Steam Deck as a distinct Linux environment.
- **Milestone C - production hardening:** W14/W16 plus optional W15; security review, build provenance, documentation and acceptance matrix.

Do not call Milestone A "cross-platform support" and do not publish Milestone B as Steam Deck validated without real Steam Deck testing.

---

## 8. Test plan and release gates

### 8.1 Unit and mocked integration tests (CI, no live Steam credentials)

Use a **fake SteamCMD** executable emitting controlled outputs, exit codes, delayed/silent behavior and a synthetic depot tree. Include:

| ID | Test case | Required result |
|---|---|---|
| T01 | `SteamFiles` exists but `steamcmd.exe` missing (Windows screenshot WinError 2) | Bootstrap or `STEAMCMD_NOT_FOUND`; no uncaught exception |
| T02 | executable exists, runs from unrelated cwd, script path has spaces/Unicode | Correct absolute `cwd`/script use |
| T03 | SteamCMD `0` exit but `app_377160` missing (WinError 3) | `DEPOT_TREE_MISSING`; **zero game writes** |
| T04 | depot folder present but one required file missing | `DEPOT_INCOMPLETE`; zero game writes |
| T05 | one required file corrupted | `HASH_MISMATCH`; staged selective repair or stop |
| T06 | SteamCMD nonzero exit | `DEPOT_DOWNLOAD_FAILED`; no advance |
| T07 | SteamCMD zero exit with per-command failure text | No advance unless all content verifies |
| T08 | no Steam Guard code, email/mobile pending | Explicit pending state; no false success or infinite retry |
| T09 | incorrect password and rate limit | Distinct error/cooldown; no secret leakage |
| T10 | TLS certificate verification failure | TLS-specific error; never insecure bypass |
| T11 | partial download interrupted | Resume verified data; never erase all staging |
| T12 | destination copy fails halfway | Transaction journal; rollback passes hash compare |
| T13 | disk full or access denied during deployment | Recoverable failure, clear stage and path |
| T14 | repeated run after successful downgrade | Idempotent verify/repair; no destructive unnecessary reapply |
| T15 | second running instance | Lock prevents overlapping operations |
| T16 | symlink/junction/path traversal in staging | Reject escaped path before write |
| T17 | stdout/stderr contains synthetic password/code | Logs and error dialogs redacted |
| T18 | cancel while downloading and while committing | Correct cancellation or rollback-required state |
| T19 | progress operations >117 | No fixed denominator; cannot display >100% |
| T20 | missing Linux 32-bit loader/library | Dependency error rather than stack trace |
| T21 | distro/SteamOS mount or Steam library not present | Proper discovery failure; no fabricated default |
| T22 | required DLC absent | No false-ready result; targeted evidence and next step |
| T23 | final executable version incorrect | `TARGET_VERIFY_FAILED` even after successful copy |
| T24 | fresh installation with no previous staging | Successful mock end-to-end transition to `COMPLETE` |
| T25 | bad zip/tar entry attempting `../` extraction | Reject archive securely |
| T26 | unexpected worker exception | Error transition only; no downstream callback |

All game-directory mutation tests use synthetic temp fixtures; CI must never download real game depots or require personal Steam accounts.

### 8.2 Platform matrix: actual machines / authorized controlled accounts

| Profile | Scope | Mandatory coverage |
|---|---|---|
| Windows 10 x64 | Normal + secondary Steam library | SteamCMD bootstrapping, auth, full downgrade, restore |
| Windows 11 x64 | Normal + secondary library and Unicode/OneDrive path | Two screenshot regressions, permissions, TLS error reporting |
| Linux desktop x86-64 (e.g. Ubuntu family) | Native Steam with Fallout 4 Windows content under Proton | Native SteamCMD, 32-bit runtime, depot root, stage/rollback |
| Linux desktop x86-64 (second distro or packaging environment) | Native Steam/alternate library | Dependency and path portability |
| Steam Deck SteamOS x86-64 | Internal SSD Steam library | Native CLI/build and end-to-end downgrade |
| Steam Deck SteamOS x86-64 | microSD Steam library | Mount detection, space, writing and resume |

**For real integration:** authenticated authorized account, correct Fallout 4 entitlement, no credentials stored in traces, backups of installed game and saves, measured postconditions, safe network usage respecting Steam limits. Observe real SteamCMD output before fixing parser behavior. A mock pass is not a real-device pass.

### 8.3 Hard release gates

Release **must not** ship if any of these fail:

1. **Artifact/provenance:** exact code commit, release manifest and build artifact hashes recorded; Windows and Linux artifacts identify the same shared engine revision.
2. **Security:** documented, reviewed credential-handling mechanism; no accidental secret exposure in logs/process persistence/support bundles; known residual SteamCMD limitations explicitly disclosed.
3. **Safety:** no game-directory writes before depot validation; interruption/rollback tests pass; neither screenshot error becomes an unhandled traceback.
4. **Correctness:** target `Fallout4.exe` version and release-owned expected assets validated after deployment; old/incorrect target versions never show success.
5. **Platform:** Windows 10/11 and at least one Linux desktop **and** Steam Deck end-to-end installation tests completed. If Steam Deck does not pass, label the release **Linux desktop beta**, not Steam Deck supported.
6. **Regression:** T01-T26 pass in applicable mocked profiles; representative native tests pass in each platform profile; no critical regression from baseline.
7. **Clarity:** users know this tool **downgrades Steam Fallout 4**; it does not install Fallout: London, GOG One-Click, Overwolf, Proton configurations or unrelated mods.
8. **Source closure:** independent Linux script revision reviewed; reused behavior/license documented; no unsupported claim of equivalence.

### 8.4 Measurement and report

Maintain distinct states: `STATIC_SOURCE_REVIEW`, `UNIT_PASS`, `MOCK_INTEGRATION_PASS`, `WINDOWS_DEVICE_PASS`, `LINUX_DEVICE_PASS`, `STEAM_DECK_PASS`, `SECURITY_REVIEW_PASS`. Never convert one into the next. For each failing case report first failing stage, root-cause confidence, exact error, game-modified flag, rollback status, OS/backend versions and sanitized trace. Retain baseline vs candidate tests so a UI improvement cannot mask a correctness regression.

---

## 9. Risks and important design decisions

| Risk | Why it matters | Mitigation / decision |
|---|---|---|
| SteamCMD authentication API/CLI limits | Secure credentials may not be fully achievable without a supported non-CLI auth mechanism | Prototype first, record residual exposure, do not claim full fix without proof |
| Depot manifest changes | Steam content IDs/manifests can change over time; wrong matrix can corrupt installs | Pin reviewed manifest and release, fail closed on unknown versions |
| SteamCMD exit status reliability | A process can exit zero despite partial download | Verify required files and hashes independently |
| Windows game and Linux host path differences | Game is Windows build launched through Proton on Linux | Separate platform adapters; do not reuse absolute Windows paths on Linux |
| Steam Deck mutable storage | SteamOS immutable root, microSD hot-unplug, Flatpak paths | Use user writable dirs, mount verification, device tests |
| Rollback disk space/cross-device rename | Large game installations and non-atomic directory moves | Preflight free-space calculation, file journal, incremental verified commit |
| Python one-file packaging | Qt/SteamCMD libraries and antivirus/SteamOS compatibility | Test one-folder/AppImage/portable launcher alternatives; no assumed universal build |
| Full Steam Deck installer overlap | Overkill scripts do more than downgrade | Separate downgrade responsibility; optional documented handoff only |
| Community script access/version | User-supplied raw link not fully inspected in this review | Pin/fetch source in implementation, hash, audit and license-check before porting |
| Archived upstream repository | Maintainer may not accept feature additions | Seek upstream agreement or label maintained fork; preserve provenance |

---

## 10. Implementation definition of done / handoff to developers

### Each pull request must include

- Problem statement and source/bug ID; whether fact is reproduced or hypothetical.
- Changed files and stage contract; no unrelated platform-specific behavior moved into shared core.
- Typed error and user-safe message; `game_modified` status and rollback path.
- Security, idempotency, file/path/symlink and cancellation considerations.
- Unit tests plus a failure-injection test, especially for state-changing changes.
- Documentation updates and platform-specific applicability.
- Source/manifest hash changes; downgrade success verification proof.

### First three developer tasks

1. **W01 + W02:** fork/pin source and release manifest; implement explicit states/error codes and a fake SteamCMD test harness.
2. **W03 + W04 + W05:** repair missing SteamCMD and cwd issues and enforce depot validation. Reproduce the screenshots as T01 and T03; show both resolved without modifying files on failure.
3. **W06 + W07:** resolve credential exposure to the feasible SteamCMD boundary, then implement staging, backup and rollback before enabling real deployment tests.

### Final acceptance statement

A successful release is **one validated Steam Fallout 4 downgrader for Windows and Linux, with Steam Deck independently verified**, not merely two executables that compile. It authenticates legitimately, downloads/validates the exact required version, changes files safely, survives interruption, explains failures without stack traces, never leaks credentials in its own retained artifacts, and reports success only after end-state verification.

---

## 11. Primary engineering reference links

- Team FOLON downgrader repository: https://github.com/Fallout-London/FOLON-FO4Downgrader
- Windows source: https://github.com/Fallout-London/FOLON-FO4Downgrader/blob/main/WindowsDowngrader.py
- Legacy Linux source: https://github.com/Fallout-London/FOLON-FO4Downgrader/blob/main/LinuxDowngrader.py
- Shared utility: https://github.com/Fallout-London/FOLON-FO4Downgrader/blob/main/Utility.py
- Main CLI entry: https://github.com/Fallout-London/FOLON-FO4Downgrader/blob/main/FOLON-Downgrader.py
- Linux launcher: https://github.com/Fallout-London/FOLON-FO4Downgrader/blob/main/Run.sh
- Official manual downgrade reference: https://github.com/Fallout-London/FOLON-FO4Downgrader/blob/main/Manually.md
- Validation request #32: https://github.com/Fallout-London/FOLON-FO4Downgrader/issues/32
- User-provided Linux downgrader (exact source must be pinned/inspected): https://raw.githubusercontent.com/krupar101/f4london_steam_deck_ini/refs/heads/main/FOLON_Linux_Downgrader.sh
- Community Steam Deck repository: https://github.com/krupar101/f4london_steam_deck_ini
- Related Overkill Steam Deck installer: https://github.com/overkillwtf/folon-steamdeck-installer
- Official Team FOLON release instructions: https://fallout4london.com/release/

**End of plan.**
