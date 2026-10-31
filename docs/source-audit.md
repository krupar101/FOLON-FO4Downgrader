# Pinned source audit

Reviewed on 2026-11-01. Reference implementations inform the shared engine;
no community shell or GPL C# implementation was copied into it.

## Team FOLON baseline

- Commit: `c53629d8dd3034776b6f58010e60bfa4cb52abe2` (MIT).
- `manifests/fo4-1.10.163.0-en.json` records the SHA-256 of `Manually.md` and
  its 14 English depot/manifest pairs. Its empty file inventories are deliberate.
- Original `tab1UI`–`tab4UI` layouts are retained in `folon_downgrader/views.py`;
  resource paths and backend connections are adapted. No network font download
  is required at startup; unavailable Overseer fonts use Qt's fallback font.
- Both screenshot paths were reproduced against extracted baseline methods:
  failed process output advanced the state to MoveFiles; missing executables
  escaped the Install method. Synthetic test data only, no real game changes.

## Community Linux script

[Immutable source](https://github.com/krupar101/f4london_steam_deck_ini/blob/3525d0dd3f09523ed91449b2e909954e27cb191d/FOLON_Linux_Downgrader.sh)

SHA-256: `f3c357c8574e96b23c55cc62a6d3df629c1f72c93677c4aca4bb05cd1fb813ae`.
GitHub's license endpoint returned 404; no source code is redistributed here.

Reviewed the full 21,234-byte script. Useful behaviors: native Linux SteamCMD,
internal/microSD selection, user-selected game path, all 14 pinned English
manifests, and a required-file existence gate before moving files. Limitations:

- `findmnt` may return multiple media mounts; a single combined string is not a
  Steam library discovery contract. The new adapter reads libraryfolders.vdf.
- `curl | tar` extraction has no whole-archive boundary validation.
- Password is a command-line argument; a claim that details are not stored does
  not address process visibility or SteamCMD's own logs/cache.
- The expected-file list proves presence, not size, checksum or full completeness.
- `linux32/steamapps/content` is assumed. The new core verifies candidate roots.
- `rsync --remove-source-files`, a special meshes move, prefix-based CC deletion
  and recursive tool-directory cleanup do not provide recoverable deployment.
- The meshes special case establishes overlapping depot files as a real concern.
  The new release contract requires an explicit owner when hashes disagree.

## zerratar/fallout4-downgrader

[Immutable FO4Down tree](https://github.com/zerratar/fallout4-downgrader/tree/9123b12ed8d1fb463bba96fa6e862d7a320d8c13/src/FO4Down)

The repository root license is GPL v3. Reviewed as a reference; no source copied.

| File | SHA-256 |
|---|---|
| DepotManager.cs | `287b78d4b3c8339fd12c49a4197dd98f99cbe8a35719ffc0638d329a9fcb8721` |
| FO4Downgrader.cs | `5297366b2e63bd378787c7e76d0eff841df39d9c703e98aaec3a8ade732e706a` |
| Steam/DepotDownloader/ContentDownloader.cs | `a06cb7a2a25190d33bf9154f3290ce71107d574de155146d1b5b26a355fad1e0` |
| Steam/DepotDownloader/ProtoManifest.cs | `950206a50706ed54add058f69fd4d80ff5266fec82b9a0ac9a70b9c4ba2ec8c3` |
| Steam/SteamKit2/Types/DepotManifest.cs | `f8b442ea26eb1fe83da9da226fc8a289ac630d50fe6dede39a4f0fd602166574` |

DepotManager corroborates all 14 pinned English depot IDs/manifests. The downloader
fetches file names, sizes and content checksums from Steam manifests at runtime;
there is no complete checked-in Fallout 4 inventory in the inspected tree.
`DumpManifestToTextFile` exports depot ID, manifest ID, entry count, sizes, SHA-1,
flags and paths. This is the format accepted by our independent candidate importer.
A local text export is not a signed trust root: its authenticated acquisition must
be recorded/reviewed. The runtime core still uses SteamCMD.

The reference handles collisions in last-depot-wins order. We require explicit
release-owned overrides instead of relying on filesystem listing order. Its
binary-patch path and support-mod installation are outside this task.

## Native Linux bootstrap experiment

Valve's HTTPS Linux archive was safely extracted under `/tmp/folon-steamcmd-spike`.
Native `steamcmd.sh +quit` bootstrapped/updated and exited 0; reported SteamCMD
version `1792617903`. An anonymous `login anonymous` / `quit` session through stdin
also exited 0, demonstrating pipe transport (not authenticated Fallout downloads).
SteamCMD wrote logs under the user's Steam directory despite its separate tool
root. The GUI deliberately does not retain raw backend output; this does not
establish confidentiality of SteamCMD-owned state. No personal login was used.

## AppImage build tool

Official `AppImage/appimagetool`, asset `appimagetool-x86_64.AppImage`, continuous
release inspected 2026-11-01. SHA-256, also supplied by GitHub's asset digest:
`ac7fd56feade6002c2f57db39587113275d351fce911a5fbb29ea84cd0666cab`.
The build script verifies this hash before executing the tool. The continuous URL
may change; a changed digest must fail until deliberately reviewed.

AppImage type2 runtime `continuous/runtime-x86_64` was downloaded separately and
verified against GitHub's asset digest:
`617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46`.
The packager receives it via `--runtime-file`, avoiding implicit network downloads.
