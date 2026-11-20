"""Soul logic: dungeon entry souls, Phantom Ganon's soul, missing souls in the tracker."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.game.remake_world import enemy_mechanics
from oot_rando.patching.soul_adapter import family_of, is_mechanical, plan_souls


def link(dst):
    return {'Dst': dst, 'Name': 'Reference', 'Gyaml': 'Reference'}


class EnemyMechanicsTests(unittest.TestCase):
    def test_enemy_spawning_a_chest_is_mechanical(self):
        # Ganon's Tower: an EventRequestActor links the chest, a shutter and the
        # counter of the two Iron Knuckles.
        root = {'Actors': [
            {'Gyaml': 'EventRequestActor', 'Hash': 1, 'Links': [link(2), link(3), link(4)]},
            {'Gyaml': 'Obj_TBox_A_03_NoBake', 'Hash': 2},
            {'Gyaml': 'Obj_SwitchShutter_A_02', 'Hash': 3},
            {'Gyaml': 'Obj_EnemyCounter_A_01', 'Hash': 4, 'Links': [link(5)]},
            {'Gyaml': 'Enemy_IronKnuckle_Black', 'Hash': 5}]}
        self.assertEqual(enemy_mechanics(root)[5], ['Obj_TBox_A_03_NoBake'])

    def test_room_lock_and_anchors_are_not_mechanics(self):
        root = {'Actors': [
            {'Gyaml': 'EventRequestActor', 'Hash': 1, 'Links': [link(3), link(4)]},
            {'Gyaml': 'Obj_SwitchShutter_A_02', 'Hash': 3},
            {'Gyaml': 'Obj_EnemyCounter_A_01', 'Hash': 4, 'Links': [link(5)]},
            {'Gyaml': 'Enemy_Keese', 'Hash': 5, 'Links': [link(6)]},
            {'Gyaml': 'DestinationAnchor', 'Hash': 6},
            {'Gyaml': 'Enemy_Bubble', 'Hash': 7}]}
        mechanics = enemy_mechanics(root)
        self.assertEqual((mechanics[5], mechanics[7]), ([], []))

    def test_event_parameters_are_mechanics(self):
        root = {'Actors': [
            {'Gyaml': 'Enemy_MiddleBoss_BigOcto', 'Hash': 1, 'Dynamic': {'IsIntendedForEventAppear': True}},
            {'Gyaml': 'Enemy_Scrub_Deku_Brothers', 'Hash': 2, 'Dynamic': {'DefeatedOrder': 2}},
            {'Gyaml': 'Enemy_Tentacle', 'Hash': 3, 'Links': [link(4)]},
            {'Gyaml': 'Land_InsideJabu_Jabu_TentacleFuse_Red_A_02', 'Hash': 4}]}
        mechanics = enemy_mechanics(root)
        self.assertEqual(mechanics[1], ['param:IsIntendedForEventAppear'])
        self.assertEqual(mechanics[2], ['param:DefeatedOrder'])
        self.assertEqual(mechanics[3], ['Land_InsideJabu_Jabu_TentacleFuse_Red_A_02'])


def enemy(hash_, actor, folder, mechanics=None):
    entry = {'resource': f'Banc/{folder}/{folder}_Static.bcett.byml.zs', 'index': int(hash_), 'actor': actor,
             'folder': folder, 'hash': hash_, 'presence': None, 'locks': []}
    if mechanics is not None:
        entry['mechanics'] = mechanics
    return entry


REGIONS = [
    {'region_name': 'Outside', 'exits': {'Lobby': 'True'}},
    {'region_name': 'Lobby', 'dungeon': 'Ganons Castle', 'exits': {'Outside': 'True'}},
]


class DungeonEntryTests(unittest.TestCase):
    def test_only_mechanical_souls_gate_the_entrance(self):
        enemies = [enemy('1', 'Enemy_IronKnuckle_Black', 'InsideGanonCastle', ['Obj_TBox_A_03_NoBake']),
                   enemy('2', 'Enemy_Keese', 'InsideGanonCastle', []),
                   enemy('3', 'Enemy_MiddleBoss_DarkLink', 'InsideGanonCastle', [])]
        plan = plan_souls('all', enemies, REGIONS)
        self.assertEqual(plan['items'], ['Soul (DarkLink)', 'Soul (IronKnuckle)', 'Soul (Keese)'])
        self.assertEqual(plan['exit_requirements'], {('Outside', 'Lobby'): {'Soul (IronKnuckle)', 'Soul (DarkLink)'}})

    def test_enemies_scanned_without_mechanics_keep_every_soul(self):
        # Older Archipelago catalogs: the strict rule of before.
        self.assertTrue(is_mechanical({'actor': 'Enemy_Keese'}))
        plan = plan_souls('all', [enemy('2', 'Enemy_Keese', 'InsideGanonCastle')], REGIONS)
        self.assertEqual(plan['exit_requirements'], {('Outside', 'Lobby'): {'Soul (Keese)'}})

    def test_mechanics_stay_out_of_the_scan_fingerprint(self):
        from oot_rando.archipelago.bridge import scan_fingerprint
        before = [{'hash': '1', 'locks': []}]
        after = [{'hash': '1', 'locks': [], 'mechanics': ['Obj_TBox']}]
        self.assertEqual(scan_fingerprint([], after, {}), scan_fingerprint([], before, {}))


class PhantomGanonTests(unittest.TestCase):
    def test_phantom_ganon_has_a_soul(self):
        self.assertEqual(family_of('Enemy_DungeonBoss_PhantomGanon'), 'PhantomGanon')
        for excluded in ('Enemy_DungeonBoss_PhantomGanon_Dictionary', 'Enemy_GhostPicturePerformer_PhantomGanon',
                         'Enemy_PhantomGanonHorse_Dictionary', 'Enemy_DungeonBoss_Ganondorf',
                         'Enemy_DungeonBoss_Ganon'):
            self.assertIsNone(family_of(excluded), excluded)

    def test_boss_soul_gates_its_room(self):
        regions = [{'region_name': 'Forest Temple Boss Door', 'dungeon': 'Forest Temple',
                    'exits': {'Phantom Ganon Boss Room': 'True'}},
                   {'region_name': 'Phantom Ganon Boss Room', 'is_boss_room': 'True', 'exits': {}}]
        plan = plan_souls('bosses', [enemy('1', 'Enemy_DungeonBoss_PhantomGanon', 'ForestTemple', [])], regions)
        self.assertEqual(plan['exit_requirements'],
                         {('Forest Temple Boss Door', 'Phantom Ganon Boss Room'): {'Soul (PhantomGanon)'}})


class FakeLogic:
    """Each location needs the listed items (all of them)."""
    def __init__(self, needs):
        self.needs = needs
        self.referenced = {i for items in needs.values() for i in items}

    def new_state(self, counts):
        return counts

    def sweep(self, placements, state):
        return state, {l for l, items in self.needs.items() if all(state.get(i) for i in items)}, []


class MissingSoulsTests(unittest.TestCase):
    def session(self):
        from oot_rando.tracker.auto_tracker import TrackerSession
        return TrackerSession.__new__(TrackerSession)

    def test_names_the_souls_that_alone_open_a_check(self):
        logic = FakeLogic({'Chest A': ['Soul (IronKnuckle)'],
                           'Chest B': ['Soul (Keese)', 'Soul (Stalfos)', 'Hookshot'],
                           'Chest C': ['Soul (Keese)', 'Soul (Stalfos)']})
        metadata = {'checks': {'a': {'logic': 'exact', 'location': 'Chest A'},
                               'b': {'logic': 'exact', 'location': 'Chest B'},
                               'c': {'logic': 'exact', 'location': 'Chest C'}},
                    'souls': [{'item': 'Soul (IronKnuckle)'}, {'item': 'Soul (Keese)'}, {'item': 'Soul (Stalfos)'}]}
        placements = {'Chest A': None, 'Chest B': None, 'Chest C': None}
        access = {'a': 'blocked', 'b': 'blocked', 'c': 'blocked'}
        reasons = self.session()._missing_souls(logic, placements, {'Soul (Stalfos)': 1}, set(), metadata, access)
        # B also needs the Hookshot: souls alone do not open it.
        self.assertEqual(reasons, {'a': ['Soul (IronKnuckle)'], 'c': ['Soul (Keese)']})

    def test_nothing_when_every_soul_is_owned(self):
        logic = FakeLogic({'Chest A': ['Soul (IronKnuckle)']})
        metadata = {'checks': {'a': {'logic': 'exact', 'location': 'Chest A'}},
                    'souls': [{'item': 'Soul (IronKnuckle)'}]}
        reasons = self.session()._missing_souls(logic, {'Chest A': None}, {'Soul (IronKnuckle)': 1}, set(),
                                                metadata, {'a': 'available'})
        self.assertEqual(reasons, {})


if __name__ == '__main__':
    unittest.main()
