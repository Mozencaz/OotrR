import _src_path  # noqa: F401  (src on sys.path)
import struct
import unittest
import zlib

from oot_rando.game.resource_allocations import grow_resources


def table(crc_entries, named_entries=()):
    data = bytearray(b'RESTBL' + struct.pack('<4I', 1, 160, len(crc_entries), len(named_entries)))
    for name, size in crc_entries:
        data.extend(struct.pack('<II', zlib.crc32(name.encode()), size))
    for name, size in named_entries:
        data.extend(name.encode().ljust(160, b'\0') + struct.pack('<I', size))
    return bytes(data)


class AllocationTests(unittest.TestCase):
    def test_named_collision_wins_and_other_allocations_stay_identical(self):
        raw = table([('map.byml', 100), ('other.byml', 200)], [('map.byml', 300)])
        out, records = grow_resources(raw, {'map.byml.zs': 4096, 'other.byml.zs': 1})
        self.assertEqual(struct.unpack_from('<I', out, 26)[0], 100)
        self.assertEqual(struct.unpack_from('<I', out, 34)[0], 4096)
        self.assertEqual(struct.unpack_from('<I', out, 198)[0], 8192)
        self.assertEqual(len(raw), len(out))
        self.assertEqual(len(records), 2)

    def test_missing_ambiguous_negative_or_duplicate_targets_fail(self):
        raw = table([('map.byml', 100)])
        for growths in ({'absent': 1}, {'map.byml': -1}, {'map.byml': 2, 'map.byml.zs': 2}):
            with self.subTest(growths=growths), self.assertRaises(ValueError):
                grow_resources(raw, growths)
        with self.assertRaises(ValueError):
            grow_resources(table([('map.byml', 100), ('map.byml', 100)]), {'map.byml': 1})
