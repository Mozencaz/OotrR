import _src_path  # noqa: F401  (src on sys.path)
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oot_rando.tracker.save_reader import (decode_progress, load_snapshot, SaveFormatError, SaveChangedError,
                         MAGIC, FORMAT_VERSION, PROGRESS_TYPE_HASH)


def fixture(flags=(10, 2**63 + 25), boolean=1, name='KokiriForest_Child'):
    records = {0: [(100, boolean)], 2: [(200, 0xffffffff)], 20: [(201, 0xffffffff)],
               16: [(300, None)], 32: [(PROGRESS_TYPE_HASH, None)]}
    table_end = 32 + 8 * (33 + sum(map(len, records.values())))
    raw_text = name.encode('utf-8')
    text = raw_text + bytes(64 - len(raw_text))
    sparse = b''.join(struct.pack('<Q', key) for key in flags) + bytes(8)
    records[16] = [(300, table_end)]
    records[32] = [(PROGRESS_TYPE_HASH, table_end + len(text))]
    header = struct.pack('<III', MAGIC, FORMAT_VERSION, table_end) + bytes(20)
    table = b''
    for typ in range(33):
        table += struct.pack('<II', 0, typ)
        table += b''.join(struct.pack('<II', key, value) for key, value in records.get(typ, ()))
    return header + table + text + sparse


class SaveReaderTests(unittest.TestCase):
    def test_typed_values_and_sparse_64bit_flags_are_decoded(self):
        data = fixture()
        result = decode_progress(data)
        self.assertEqual(result['bool'], {100: True})
        self.assertEqual(result['int'], {200: -1, 201: 0xffffffff})
        self.assertEqual(result['bool64'], {10: True, 2**63 + 25: True})
        self.assertTrue(result['bool64_complete'])
        self.assertEqual(result['strings'], {300: 'KokiriForest_Child'})
        self.assertEqual(result['sha256'], hashlib.sha256(data).hexdigest())

    def test_empty_sparse_table_is_valid(self):
        self.assertEqual(decode_progress(fixture(flags=()))['bool64'], {})

    def test_truncation_bad_sentinel_and_bool_are_rejected(self):
        data = fixture()
        for bad in (data[:24], data[:-8], fixture(boolean=2), data[:32] + struct.pack('<II', 0, 2) + data[40:]):
            with self.subTest(size=len(bad)), self.assertRaises(SaveFormatError):
                decode_progress(bad)

    def test_invalid_text_pointer_and_unterminated_string_are_rejected(self):
        data = bytearray(fixture())
        table_end = struct.unpack_from('<I', data, 8)[0]
        # Locate the single type16 record structurally in this fixture.
        text_record = data.index(struct.pack('<II', 300, table_end), 32, table_end)
        bad = bytearray(data)
        struct.pack_into('<I', bad, text_record + 4, len(data) + 4)
        with self.assertRaises(SaveFormatError):
            decode_progress(bytes(bad))
        data[table_end:table_end + 64] = b'x' * 64
        with self.assertRaises(SaveFormatError):
            decode_progress(bytes(data))

    def test_unsorted_duplicate_flags_and_nonzero_tail_are_rejected(self):
        for bad in (fixture(flags=(20, 10)), fixture(flags=(10, 10)), fixture() + b'not padding'):
            with self.assertRaises(SaveFormatError):
                decode_progress(bad)

    def test_stable_file_load_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'progress.sav'
            data = fixture()
            path.write_bytes(data)
            before = path.stat()
            result = load_snapshot(path)
            self.assertEqual(result['path'], str(path.resolve()))
            self.assertEqual(result['mtime_ns'], before.st_mtime_ns)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)

    def test_changing_file_is_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'progress.sav'
            path.write_bytes(fixture())
            stat = path.stat()
            with patch('oot_rando.tracker.save_reader._read_once', side_effect=[(fixture(), stat), (fixture(boolean=0), stat)]):
                with self.assertRaises(SaveChangedError):
                    load_snapshot(path, attempts=1)


if __name__ == '__main__':
    unittest.main()
