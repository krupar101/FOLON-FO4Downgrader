import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from folon_downgrader.errors import DowngradeError
from folon_downgrader.steam_manifest import cached_manifest, PAYLOAD, METADATA, SIGNATURE, END


def varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def field(tag, value):
    if isinstance(value, bytes):
        return varint(tag * 8 + 2) + varint(len(value)) + value
    return varint(tag * 8) + varint(value)


def fixture(names=('Fallout4.exe',), encrypted=0, flags=0):
    payload = b''.join(field(1, field(1, name.encode()) + field(2, 4) + field(3, flags)
                            + field(5, hashlib.sha1(b'game').digest())) for name in names)
    crc = zlib.crc32(struct.pack('<I', len(payload)) + payload)
    meta = field(1, 377162) + field(2, 5847529232406005096) + field(4, encrypted) + field(9, crc)
    return b''.join(struct.pack('<II', magic, len(body)) + body for magic, body in
                    ((PAYLOAD, payload), (METADATA, meta), (SIGNATURE, b''))) + struct.pack('<I', END)


class CachedManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.manifest'

    def read(self, data, depot=377162, manifest=5847529232406005096):
        self.path.write_bytes(data)
        return cached_manifest(self.path, depot, manifest)

    def test_valid_cache_records_checksum_and_provenance_limit(self):
        files, evidence = self.read(fixture())
        self.assertEqual(files['Fallout4.exe'], {'size': 4, 'sha1': hashlib.sha1(b'game').hexdigest()})
        self.assertTrue(evidence['payload_crc_checked'])
        self.assertFalse(evidence['signature_verified'])

    def test_wrong_ids_are_rejected(self):
        for depot, manifest in ((377161, 5847529232406005096), (377162, 123)):
            with self.assertRaises(DowngradeError):
                self.read(fixture(), depot, manifest)

    def test_every_truncation_is_rejected(self):
        data = fixture()
        for end in range(len(data)):
            with self.subTest(end=end), self.assertRaises(DowngradeError):
                self.read(data[:end])

    def test_payload_corruption_is_rejected(self):
        data = fixture().replace(b'Fallout4.exe', b'Fallout5.exe')
        with self.assertRaises(DowngradeError):
            self.read(data)

    def test_trailing_bytes_rejected(self):
        with self.assertRaises(DowngradeError):
            self.read(fixture() + b'junk')

    def test_encrypted_filenames_are_not_treated_as_paths(self):
        with self.assertRaises(DowngradeError) as caught:
            self.read(fixture(encrypted=1))
        self.assertEqual(caught.exception.code, 'MANIFEST_ENCRYPTED')

    def test_symlinks_and_escaped_paths_rejected(self):
        for data in (fixture(flags=512), fixture(names=('../Fallout4.exe',))):
            with self.assertRaises(DowngradeError):
                self.read(data)

    def test_case_aliases_are_rejected(self):
        with self.assertRaises(DowngradeError):
            self.read(fixture(names=('Fallout4.exe', 'fallout4.exe')))
