"""Readable check names (game/check_names.py), on small hand-made maps."""
import _src_path  # noqa: F401  (src on sys.path)
import json
import unittest
from unittest import mock

from oot_rando.game import check_names as cn
from oot_rando.randomizer.full_randomizer import check_name, covered_locations


def actor(gyaml, position, **extra):
    return dict({'Gyaml': gyaml, 'Translate': list(position)}, **extra)


class Names(unittest.TestCase):
    """Labelling rules, independent of label_overrides.json: renaming a check there
    must never break these tests, so the overrides are emptied for each test."""

    def setUp(self):
        patcher = mock.patch.object(cn, '_LABEL_OVERRIDES', {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_snake_and_entrances(self):
        self.assertEqual(cn.snake('DodongoCavernSide'), 'dodongo_cavern_side')
        self.assertEqual(cn._entrance_label('MountainTrail_DodongoCavernSide'), 'dodongo_cavern_entrance')

    def test_rooms_owners_areas_and_numbering(self):
        path = 'Banc/KokiriForest/KokiriForest_Child_Static.bcett.byml.zs'
        props = [actor('Land_Kokiri_Interior_A_01', (x, 0, 0)) for x in (0, 2, 4)]
        props += [actor('Land_Kokiri_Interior_A_01', (100 + x, 0, 0)) for x in (0, 2, 4)]
        maps = {path: {'root': {'Actors': props + [
            actor('Npc_Kokiri_Saria_Child', (2, 0, 1)),
            actor('LocationArea', (300, 0, 0), Scale=[10, 10, 10], Dynamic={'Location': 'LakeHylia'})]}}}
        pot = lambda gid, pos: {'source': 'pots', 'before': 'Obj_Rupee_Green',
                                'variants': [{'resource': path, 'index': 0, 'position': list(pos)}]}
        extra = {'a': pot('a', (3, 0, 0)), 'b': pot('b', (1, 0, 0)), 'c': pot('c', (101, 0, 0)),
                 'd': pot('d', (305, 0, 0)), 'e': pot('e', (50, 0, 0))}
        cn.label_entries(maps, {}, extra)
        names = {gid: cn.entry_label(entry) for gid, entry in extra.items()}
        self.assertEqual(names['b'], 'KF_saria_house_pot_1')      # west to east
        self.assertEqual(names['a'], 'KF_saria_house_pot_2')
        self.assertEqual(names['c'], 'KF_house_pot_1')            # nobody lives there
        self.assertEqual(names['d'], 'LH_pot_1')                  # LocationArea of another zone
        self.assertEqual(names['e'], 'KF_pot_1')                  # open ground

    def test_dungeon_rooms(self):
        path = 'Banc/InsideTheDekuTree/InsideTheDekuTree_Static.bcett.byml.zs'
        maps = {path: {'root': {'Actors': [actor('Obj_Pot', (0, 0, 0), Dynamic={'DefaultDungeonRoomIndex': 3})]}}}
        groups = {'g': [{'resource': path, 'index': 0, 'position': [0, 0, 0], 'folder': 'InsideTheDekuTree',
                         'dynamic': {'DefaultDungeonRoomIndex': 3}, 'before': 'TBox'}]}
        cn.label_entries(maps, groups, {})
        self.assertEqual(groups['g'][0]['label'], 'DT_room3_chest_1')

    def test_check_name_and_coverage(self):
        exact = {'kind': 'exact', 'ap': ['KF Midos Top Left Chest'], 'variants': [{'label': 'KF_midos_house_chest_1'}]}
        self.assertEqual(check_name(exact, 'x'), 'KF Midos Top Left Chest')   # AP name first
        area = {'kind': 'area', 'ap': ['KF Links House Pot'], 'variants': [{'label': 'KF_pot_3'}]}
        self.assertEqual(check_name(area, 'x'), 'KF_pot_3')
        npc = {'kind': 'junk', 'ap': [], 'variants': []}
        self.assertEqual(check_name(npc, 'npc#Kak 10 Gold Skulltula Reward'), 'Kak 10 Gold Skulltula Reward')
        self.assertEqual(covered_locations(npc, 'npc#Kak 10 Gold Skulltula Reward'), {'Kak 10 Gold Skulltula Reward'})
        self.assertEqual(covered_locations(area, 'x'), {'KF Links House Pot'})


class Overrides(unittest.TestCase):
    """label_overrides.json renames checks; tested with a fake table, not the real one."""

    FAKE = {'KF_pot_3': 'Pot Renamed', 'KF_gs_1 (child)': 'GS Renamed',
            'KF Midos Top Left Chest': 'Chest Renamed'}

    def setUp(self):
        patcher = mock.patch.object(cn, '_LABEL_OVERRIDES', dict(self.FAKE))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_entry_label_override(self):
        self.assertEqual(cn.entry_label({'variants': [{'label': 'KF_pot_3'}]}), 'Pot Renamed')
        self.assertEqual(cn.entry_label({'variants': [{'label': 'KF_gs_1'}]}), 'GS Renamed')  # age suffix key
        self.assertEqual(cn.entry_label({'variants': [{'label': 'KF_pot_9'}]}), 'KF_pot_9')   # no override
        self.assertIsNone(cn.entry_label({'variants': []}))

    def test_check_name_override(self):
        exact = {'kind': 'exact', 'ap': ['KF Midos Top Left Chest'], 'variants': []}
        self.assertEqual(check_name(exact, 'x'), 'Chest Renamed')
        area = {'kind': 'area', 'ap': ['KF Links House Pot'], 'variants': [{'label': 'KF_pot_3'}]}
        self.assertEqual(check_name(area, 'x'), 'Pot Renamed')

    def test_real_file_is_well_formed(self):
        from oot_rando.paths import resource
        table = json.loads(resource('game', 'label_overrides.json').read_text(encoding='utf-8'))
        self.assertIsInstance(table, dict)
        for key, value in table.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)
            self.assertTrue(value.strip(), key)


if __name__ == '__main__':
    unittest.main()
