import _src_path  # noqa: F401  (src on sys.path)
import os
from pathlib import Path
import struct
import unittest
from collections import Counter

from oot_rando.formats.byml_writer import patch_strings
from oot_rando.formats.inspect_resources import Byml, dictionaries
from oot_rando.formats.inspect_nup import Nup
from byml_fixture import fixture
from oot_rando.game.world_maps import build_world


def big_endian_fixture():
    data = bytearray(b'BY\x00\x07' + bytes(12))
    def table(text):
        data.extend(bytes(-len(data) % 4))
        start = len(data)
        encoded = text.encode() + b'\0'
        data.extend(b'\xc2\x00\x00\x01' + struct.pack('>II', 12, 12 + len(encoded)) + encoded)
        return start
    key, string = table('Key'), table('Before')
    data.extend(bytes(-len(data) % 4))
    root = len(data)
    data.extend(b'\xc1\x00\x00\x01\x00\x00\x00\xa0' + bytes(4))
    struct.pack_into('>III', data, 4, key, string, root)
    return bytes(data)


class WriterTests(unittest.TestCase):
    def test_unsafe_categories_are_rejected_before_reading_game(self):
        from unittest.mock import Mock
        nup = Mock()
        with self.assertRaisesRegex(ValueError, 'disabled'):
            build_world(nup, {}, {'trees': True}, 'test')
        nup.read.assert_not_called()
    def test_adds_new_keys_and_dynamic_without_losing_uint64(self):
        raw = fixture([{'Hash': (1 << 64) - 1, 'Gyaml': 'Pot'}])
        out = patch_strings(raw, [{'path': ('Actors', 0, 'Dynamic', 'Drop__DropActor'),
                                   'before': None, 'after': 'Obj_Rupee_Red'}])
        self.assertEqual(Byml(out).root, {'Actors': [{'Hash': (1 << 64) - 1, 'Gyaml': 'Pot',
                         'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Red'}}]})
        self.assertEqual(Byml(out).keys, sorted(Byml(out).keys))

    def test_shared_nodes_do_not_share_edits(self):
        shared = {'Drop__DropActor': 'Blue'}
        raw = fixture([{'Hash': 1, 'Gyaml': 'Pot', 'Dynamic': shared},
                       {'Hash': 2, 'Gyaml': 'Pot', 'Dynamic': shared}])
        changes = [{'path': ('Actors', 0, 'Dynamic', 'Drop__DropActor'), 'before': 'Blue', 'after': 'Red'}]
        result = patch_strings(raw, changes)
        self.assertEqual([a['Dynamic']['Drop__DropActor'] for a in Byml(result).root['Actors']], ['Red', 'Blue'])
        self.assertEqual(result, patch_strings(raw, changes))

    def test_big_endian_addition_and_replacement(self):
        raw = big_endian_fixture()
        self.assertEqual(Byml(raw).root, {'Key': 'Before'})
        result = patch_strings(raw, [{'path': ('Key',), 'before': 'Before', 'after': 'After'},
                                     {'path': ('Added',), 'before': None, 'after': 'New'}])
        self.assertEqual(result[:2], b'BY')
        self.assertEqual(Byml(result).root, {'Key': 'After', 'Added': 'New'})

    def test_preconditions_and_overlap_are_rejected(self):
        raw = big_endian_fixture()
        for edits in ([{'path': ('Key',), 'before': 'wrong', 'after': 'new'}],
                      [{'path': ('Key',), 'before': None, 'after': 'new'}],
                      [{'path': ('Missing',), 'before': 'wrong', 'after': 'new'}],
                      [{'path': ('Key',), 'before': 'Before', 'after': 'new'}] * 2):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                patch_strings(raw, edits)


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'Set OOT_NUP for local world integration')
class LocalWorldTests(unittest.TestCase):
    def test_safe_world_chests_preserve_progression_and_report_exclusions(self):
        nup = Nup(Path(os.environ['OOT_NUP']))
        try:
            result = build_world(nup, dictionaries(nup), {'world_chests': True}, 'world-test')
            self.assertTrue(result['raw_maps'])
            self.assertTrue(result['placements'])
            self.assertEqual(Counter(p['before'] for p in result['placements']),
                             Counter(p['after'] for p in result['placements']))
            from oot_rando.game.world_maps import SAFE_CHESTS
            for placement in result['placements']:
                self.assertIn(placement['before'], SAFE_CHESTS)
                self.assertIn(placement['after'], SAFE_CHESTS)
                self.assertNotEqual(placement['before'], placement['after'])
                self.assertFalse(placement['repeatable'])
            coverage = result['coverage']['world_chests']
            self.assertFalse(coverage['complete'])
            self.assertGreater(coverage['skipped']['progression_or_unknown_reward_preserved'], 0)
            self.assertEqual(set(result['raw_maps']), set(result['sources']))
            self.assertEqual(set(result['raw_maps']), set(result['source_members']))
            print('World chest coverage:', coverage)
        finally:
            nup.stream.close()


if __name__ == '__main__':
    unittest.main()
