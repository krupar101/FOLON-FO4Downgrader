"""Read unencrypted Steam depotcache manifests for offline inventory review.

Protocol references: SteamRE/SteamKit DepotManifest.cs and SteamDatabase/Protobufs
steam/content_manifest.proto. This is an independent bounded wire-format reader,
not Steam authentication or signature validation. Local cache provenance matters.
"""
import hashlib
from pathlib import Path
import struct
import zlib

from .errors import fail
from .files import relative_name

PAYLOAD = 0x71F617D0
METADATA = 0x1F4812BE
SIGNATURE = 0x1B81B817
END = 0x32C415AB


def _invalid():
    fail('MANIFEST_INVALID', 'Malformed, incomplete or unsupported cached Steam manifest.')


def _varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            _invalid()
        byte = data[pos]
        pos += 1
        if shift == 63 and byte > 1:
            _invalid()
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, pos
    _invalid()


def _fields(data):
    fields = {}
    pos = 0
    while pos < len(data):
        key, pos = _varint(data, pos)
        tag, wire = key >> 3, key & 7
        if not tag:
            _invalid()
        if wire == 0:
            value, pos = _varint(data, pos)
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            if pos + length > len(data):
                _invalid()
            value = int.from_bytes(data[pos:pos+length], 'little')
            pos += length
        elif wire == 2:
            length, pos = _varint(data, pos)
            if pos + length > len(data):
                _invalid()
            value = data[pos:pos+length]
            pos += length
        else:
            _invalid()
        fields.setdefault(tag, []).append(value)
    return fields


def _one(fields, tag, kind, default=None):
    values = fields.get(tag, [default])
    if len(values) != 1 or not isinstance(values[0], kind):
        _invalid()
    return values[0]


def cached_manifest(path, depot_id, manifest_id):
    path = Path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        _invalid()
    data = path.read_bytes()
    pos = 0
    sections = {}
    while True:
        if pos + 4 > len(data):
            _invalid()
        magic = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        if magic == END:
            break
        if magic not in (PAYLOAD, METADATA, SIGNATURE) or magic in sections or pos + 4 > len(data):
            _invalid()
        size = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        if pos + size > len(data):
            _invalid()
        sections[magic] = data[pos:pos+size]
        pos += size
    if pos != len(data) or set(sections) != {PAYLOAD, METADATA, SIGNATURE}:
        _invalid()
    meta = _fields(sections[METADATA])
    if _one(meta, 1, int) != int(depot_id) or _one(meta, 2, int) != int(manifest_id):
        fail('MANIFEST_INVALID', 'Cached Steam manifest IDs do not match the pinned depot selection.')
    if _one(meta, 4, int, 0):
        fail('MANIFEST_ENCRYPTED', 'Cached filenames are encrypted. Use an authenticated, decrypted manifest export.')
    crc = _one(meta, 9, int, 0)
    if crc and zlib.crc32(struct.pack('<I', len(sections[PAYLOAD])) + sections[PAYLOAD]) != crc:
        fail('MANIFEST_INVALID', 'Cached Steam manifest payload checksum does not match.')
    mappings = _fields(sections[PAYLOAD]).get(1, [])
    if not mappings or len(mappings) > 100000:
        _invalid()
    files = {}
    names = set()
    for mapping in mappings:
        if not isinstance(mapping, bytes):
            _invalid()
        record = _fields(mapping)
        try:
            name = _one(record, 1, bytes).decode('utf-8').replace('\\', '/')
        except UnicodeError:
            _invalid()
        relative_name(name)
        if name.casefold() in names:
            fail('MANIFEST_INVALID', 'Cached manifest contains duplicate or case-conflicting paths.')
        names.add(name.casefold())
        flags = _one(record, 3, int, 0)
        if flags & 512 or _one(record, 7, bytes, b''):
            fail('UNSAFE_PATH', 'Symlink depot entries are not supported by this release contract.')
        if flags & 64:
            continue
        size = _one(record, 2, int, 0)
        sha1 = _one(record, 5, bytes)
        if len(sha1) != 20:
            _invalid()
        files[name] = {'size': size, 'sha1': sha1.hex()}
    if not files:
        _invalid()
    return files, {
        'depot': int(depot_id), 'manifest': str(manifest_id),
        'sha256': hashlib.sha256(data).hexdigest(),
        'entries': len(mappings), 'regular_files': len(files),
        'payload_crc_checked': bool(crc),
        'signature_verified': False,
    }
