# Obtain the release inventory

Depot IDs identify versions; they are not a complete list of expected files.
The two community references corroborate the English depot matrix. The zerratar
implementation retrieves sizes/checksums from Steam rather than embedding a full
inventory. Its DepotDownloader backend can export this information without first
downloading every game file.

1. Use an authorized Steam account owning Fallout 4 and the required DLC.
2. Obtain authenticated manifest exports for **all 14 pinned depot/manifest
   pairs** in `manifests/fo4-1.10.163.0-en.json`. Official DepotDownloader supports
   `-manifest-only`. For example, the executable depot is:

   ```sh
   DepotDownloader -app 377160 -depot 377162 -manifest 5847529232406005096 -manifest-only -username YOUR_ACCOUNT -dir ./manifest-exports
   ```

   Enter passwords/Guard responses interactively, never in command arguments.
   This is a maintainer acquisition tool, not a replacement runtime backend.
   Record its exact release/hash and the authenticated acquisition provenance.
   The account name is visible in argv for this external command. Do not enable
   debug logging or share Steam session/cache files. No password is needed in chat.

3. Download the pinned game depots using SteamCMD through the shared GUI (or
   `--download` CLI). Retain each `depot_ID` folder beneath `app_377160`.
4. Place the exports named `manifest_DEPOT_MANIFEST.txt` in one directory and run:

   ```sh
   python -m folon_downgrader.inventory \
     --manifest manifests/fo4-1.10.163.0-en.json \
     --content-root /path/to/app_377160 \
     --steam-manifests /path/to/manifest-exports \
     --output /path/to/candidate.json
   ```

The importer checks IDs, the declared entry count, every exported regular file's
size and Steam SHA-1, then computes SHA-256 and checks the executable version.
It records the export hashes. It **always leaves `inventory_complete: false`**.
Without `--steam-manifests`, it only inventories local bytes: this helps inspection
but does not prove completeness. Neither mode automatically establishes provenance.

Review collisions (especially `Data/Fallout4 - Meshes.ba2`), assign explicit owners
in `overrides`, and decide exact recoverable CC/HD removals. Validate the contract
against an independently verified installation and the intended FOLON release.
Only then commit the reviewed inventory with `inventory_complete: true` and run
the real-device acceptance matrix. Do not redistribute game files in this repo.

[DepotDownloader parameters](https://github.com/SteamRE/DepotDownloader#parameters).
The importer format reference and source hashes are in [source-audit.md](source-audit.md).

## Existing SteamCMD download: use the local manifest cache

SteamCMD may leave the exact unencrypted manifests in the Steam client's
`depotcache` directory, even when its executable and downloads are on another
drive. The live Linux test found all 14 there, so no additional account login
or DepotDownloader invocation was needed.

```sh
python -m folon_downgrader.inventory \
  --manifest manifests/fo4-1.10.163.0-en.json \
  --content-root /path/to/app_377160 \
  --steam-cache ~/.local/share/Steam/depotcache \
  --output /path/to/candidate.json
```

The cache reader checks complete framing, exact depot/manifest IDs, unencrypted
filenames and the available payload CRC (which covers the length plus payload).
Every regular file is then checked against its Steam size and SHA-1 while SHA-256
is computed. Cached signature sections may be empty: this is not independent
signature verification. Source provenance and cache hashes remain recorded.

`fo4-1.10.163.0-en.candidate.json` records the live test's verified 117 file records,
explicit meshes owner, and exact cleanup paths. It remains disabled for general
deployment. The `exclude` list prevents selected official CC assets from being
installed, while still requiring their downloaded bytes to verify. `remove` names
the exact destination files to back up/remove; no runtime wildcard is used.
