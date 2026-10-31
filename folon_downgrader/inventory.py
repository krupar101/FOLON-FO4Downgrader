"""Maintainer tool: derive a reviewable inventory, never silently approve it."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

from .errors import DowngradeError, fail
from .files import digest, inside, is_link, relative_name
from .manifest import Manifest, executable_version


def steam_text(path, depot_id, manifest_id):
    """Read the documented DepotDownloader text export, validating IDs/counts.

    Format reference is pinned in docs/source-audit.md. No reference source code
    is bundled or executed. An export's origin must still be reviewed.
    """
    text = Path(path).read_text(encoding='utf-8-sig')
    depot = re.search(r'^Content Manifest for Depot (\d+)\s*$', text, re.M)
    manifest = re.search(r'^Manifest ID / date\s*:\s*(\d+)\s*/', text, re.M)
    count = re.search(r'^Total number of files\s*:\s*(\d+)\s*$', text, re.M)
    if not depot or not manifest or not count or depot[1] != str(depot_id) or manifest[1] != str(manifest_id):
        fail('MANIFEST_INVALID', 'Steam export IDs/count do not match the pinned depot selection.')
    lines = text.splitlines()
    headers = [i for i, line in enumerate(lines) if re.fullmatch(r'\s*Size\s+Chunks\s+File SHA\s+Flags\s+Name\s*', line)]
    if len(headers) != 1:
        fail('MANIFEST_INVALID', 'Unknown Steam text export format.')
    rows = [line for line in lines[headers[0]+1:] if line.strip()]
    if len(rows) != int(count[1]):
        fail('MANIFEST_INVALID', 'Steam export file count is incomplete.')
    files = {}
    names = set()
    for line in rows:
        match = re.fullmatch(r'\s*(\d+)\s+(\d+)\s+([a-fA-F0-9]{40}|)\s+([a-fA-F0-9]+)\s+(.+?)\s*', line)
        if not match:
            fail('MANIFEST_INVALID', 'Unrecognized Steam manifest file record.')
        size, _, sha1, flags, name = match.groups()
        name = name.replace('\\', '/')
        relative_name(name)
        if name.casefold() in names:
            fail('MANIFEST_INVALID', 'Duplicate Steam manifest path.')
        names.add(name.casefold())
        flags = int(flags, 16)
        if flags & 512:  # Steam EDepotFileFlag.Symlink
            fail('UNSAFE_PATH', 'A depot contains a symlink; this release contract supports regular files only.')
        if flags & 64:  # Steam EDepotFileFlag.Directory
            continue
        if len(sha1) != 40:
            fail('MANIFEST_INVALID', 'A regular file has no Steam content checksum.')
        files[name] = {'size': int(size), 'sha1': sha1.lower()}
    if not files:
        fail('MANIFEST_INVALID', 'A required depot has no regular files.')
    return files


def candidate(manifest, content, exports=None):
    result = copy.deepcopy(manifest.data)
    result['inventory_complete'] = False
    result['inventory_evidence'] = {'status': 'candidate_requires_review', 'base_manifest_sha256': manifest.sha256,
                                    'steam_exports': []}
    for depot in result['depots']:
        root = inside(content, f"depot_{depot['id']}")
        if not root.is_dir():
            fail('DEPOT_TREE_MISSING', 'Download every pinned depot before generating an inventory candidate.')
        expected = None
        if exports:
            export = inside(exports, f"manifest_{depot['id']}_{depot['manifest']}.txt")
            expected = steam_text(export, depot['id'], depot['manifest'])
            result['inventory_evidence']['steam_exports'].append({'depot': depot['id'], 'sha256': digest(export)})
        names = []
        if expected:
            names = list(expected)
        else:
            for path in root.rglob('*'):
                if is_link(path):
                    fail('UNSAFE_PATH', 'Links cannot be included in a release inventory.')
                if path.is_file():
                    names.append(path.relative_to(root).as_posix())
        if not names:
            fail('DEPOT_INCOMPLETE', 'A required depot is empty.')
        depot['files'] = []
        for name in sorted(names):
            path = inside(root, name)
            if not path.is_file():
                fail('DEPOT_INCOMPLETE', 'A Steam manifest file is missing from the download.')
            size = path.stat().st_size
            if expected:
                with path.open('rb') as stream:
                    sha1 = hashlib.file_digest(stream, 'sha1').hexdigest()
                if size != expected[name]['size'] or sha1 != expected[name]['sha1']:
                    fail('HASH_MISMATCH', 'Downloaded bytes do not match the Steam manifest.')
            depot['files'].append({'path': name, 'size': size, 'sha256': digest(path)})
    executables = [inside(content, f"depot_{d['id']}/Fallout4.exe") for d in result['depots']
                   if any(f['path'] == 'Fallout4.exe' for f in d['files'])]
    if len(executables) != 1 or executable_version(executables[0]) != result['target_exe_version']:
        fail('WRONG_GAME_BUILD', 'The candidate must contain exactly one executable of the target version.')
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--content-root', type=Path, required=True)
    p.add_argument('--steam-manifests', type=Path, help='Directory of authenticated DepotDownloader -manifest-only exports')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = candidate(Manifest(args.manifest), args.content_root.absolute(), args.steam_manifests)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
        print('Candidate written. It remains disabled pending provenance, overlap and cleanup review.')
        return 0
    except DowngradeError as error:
        print(str(error))
    except OSError:
        print('FILESYSTEM_ERROR: Cannot read inputs or create a new output file. Existing files were not overwritten.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
