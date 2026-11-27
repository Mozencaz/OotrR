"""BYML string tables: same strings as before, read in linear time."""
import _src_path  # noqa: F401
import time
import unittest

from byml_fixture import fixture
from oot_rando.formats import byml_codec
from oot_rando.formats.byml_codec import c_string
from oot_rando.formats.inspect_resources import Byml


class StringTableTests(unittest.TestCase):
    def test_c_string_stops_at_the_terminator_or_the_end(self):
        self.assertEqual(c_string(b'ab\0cd\0', 0), 'ab')
        self.assertEqual(c_string(b'ab\0cd\0', 3), 'cd')
        self.assertEqual(c_string(b'ab\0cd', 3), 'cd')
        self.assertEqual(c_string(b'\0', 0), '')

    def test_both_readers_agree_on_many_strings(self):
        actors = [{'Gyaml': f'Actor_{i:05d}', 'Name': f'Instance {i} é'} for i in range(3000)]
        raw = fixture(actors)
        self.assertEqual(Byml(raw).root['Actors'], actors)
        self.assertEqual(byml_codec.load(raw)['root']['Actors'], actors)

    def test_large_tables_load_in_linear_time(self):
        # 20 000 strings: the former per-string copy of the rest of the buffer took
        # about 4 s for both readers here; a linear read takes a few hundredths.
        actors = [{'Gyaml': f'Actor_{i:06d}_' + 'x' * 24} for i in range(20000)]
        raw = fixture(actors)
        start = time.perf_counter()
        document = byml_codec.load(raw)
        Byml(raw)
        self.assertLess(time.perf_counter() - start, 1)
        self.assertEqual(len(document['root']['Actors']), 20000)


if __name__ == '__main__':
    unittest.main()
