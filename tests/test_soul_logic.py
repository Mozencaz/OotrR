"""Soul logic: dungeon entry souls, Phantom Ganon's soul, missing souls in the tracker."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest
import os

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

    def test_combat_evidence_invalidates_old_archipelago_placements(self):
        from oot_rando.archipelago.bridge import scan_fingerprint
        before = [{'hash': '1', 'locks': []}]
        after = [{'hash': '1', 'locks': [], 'combat': [{'id': 'native-fight'}]}]
        self.assertNotEqual(scan_fingerprint([], after, {}), scan_fingerprint([], before, {}))


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


class CombatProgressionTests(unittest.TestCase):
    def test_nested_defeat_module_and_counter_only_group_are_scanned(self):
        from oot_rando.game.combat import combat_dependencies
        root = {'Actors': [{'Hash': 1, 'Gyaml': 'Enemy_Spike'},
                           {'Hash': 2, 'Gyaml': 'Obj_EnemyCounter_A_01', 'Links': [link(1)]}],
                'AiGroups': [{'Hash': 3, 'Logic': 'Parent.logic.module.ain',
                              'References': [{'Reference': 2}]}]}
        modules = {
            'Logic/Parent.logic.module.ainb': {'Nodes': [{'Name': 'Child.logic.module', 'Flags': ['Is Module']}]},
            'Logic/Child.logic.module.ainb': {'Nodes': [{'Name': 'ActorLogicEnemySpike',
                'Parameters': {'Outputs': {'Bool': [{'Name': 'Dead', 'Is Output': True}]}}}]},
        }
        combat = combat_dependencies('map', root, modules.__getitem__)
        self.assertIn(1, combat)
        self.assertIn('Logic/Child.logic.module.ainb:ActorLogicEnemySpike.Dead', combat[1][0]['signals'])
        self.assertEqual(combat[1][0]['targets'], ['2'])

    def test_royal_tomb_song_requires_keese_soul_before_adult_access(self):
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        data = World()
        bat = enemy('1', 'Enemy_Keese', 'Graveyard', [])
        door = {'resource': bat['resource'], 'index': 2, 'hash': '2',
                'actor': 'Obj_SwitchShutter_A_02', 'presence': None}
        bat['locks'] = [{'counter': bat['resource'] + '#3', 'doors': [door]}]
        plan = plan_souls('all', [bat], data.regions)
        logic = Logic(data, extra_exit_requirements=plan['exit_requirements'],
                      extra_location_requirements=plan['location_requirements'])
        state = logic.new_state({'Kokiri Sword': 1})
        state.reached['child'].add('Graveyard Royal Familys Tomb')
        self.assertFalse(logic.accessible(state, 'Song from Royal Familys Tomb'))
        state.add('Soul (Keese)')
        self.assertTrue(logic.accessible(state, 'Song from Royal Familys Tomb'))

    def test_scripted_chest_without_spawn_type_requires_its_combat_soul(self):
        from oot_rando.game.combat import combat_dependencies
        from oot_rando.patching.soul_adapter import chest_requirements
        bat = enemy('1', 'Enemy_Wolfos', 'SacredForestMeadow', [])
        root = {'Actors': [{'Hash': 1, 'Gyaml': 'Enemy_Wolfos'},
                           {'Hash': 2, 'Gyaml': 'Obj_TBox_A_01_NoBake'}],
                'AiGroups': [{'Hash': 3, 'Logic': 'Logic/Module/Hole.logic.module.ain',
                              'References': [{'Reference': 1}, {'Reference': 2}]}]}
        # Native Wolfos/Dinolfos use ActorLogicSimpleActor, not an Enemy node.
        module = {'Nodes': [{'Name': 'ActorLogicSimpleActor',
                            'Properties': {'String': [{'Name': 'InstanceName', 'Default Value': 'Enemy_Wolfos_52d3'}]},
                            'Parameters': {'Outputs': {'Bool': [{'Name': 'Dead', 'Is Output': True}]}}}]}
        bat['combat'] = combat_dependencies(bat['resource'], root, lambda _: module)[1]
        self.assertTrue(bat['combat'][0]['signals'][0].endswith(':ActorLogicSimpleActor.Dead'))
        plan = plan_souls('all', [bat], REGIONS)
        chest = {'id': 'merged-chest', 'folder': bat['folder'],
                 'variants': [{'hash': '2', 'resource': bat['resource'], 'dynamic': {}}]}
        self.assertEqual(chest_requirements(plan, chest, ()), {'Soul (Wolfos)'})
        regional = plan_souls('regional', [bat], REGIONS)
        self.assertEqual(chest_requirements(regional, chest, ()), {'Soul (Region:SacredForestMeadow)'})
        self.assertEqual(chest_requirements(plan_souls('bosses', [bat], REGIONS), chest, ()), set())

    def test_target_practice_requires_its_scripted_enemy_even_when_unshuffled(self):
        leaf = enemy('1', 'Enemy_Scrub_Deku_Leaf', 'LostWood', ['NPC_Scrub_Deku_TargetPractice'])
        plan = plan_souls('all', [leaf], REGIONS)
        self.assertEqual(plan['location_requirements']['LW Target in Woods'], {'Soul (DekuScrub)'})
        plan = plan_souls('regional', [leaf], REGIONS)
        self.assertEqual(plan['location_requirements']['LW Target in Woods'], {'Soul (Region:LostWood)'})

    def test_native_baba_resources_need_the_regional_soul_too(self):
        baba = enemy('1', 'Enemy_Dekubaba', 'KokiriForest', [])
        for mode, item in (('all', 'Soul (DekuBaba)'), ('regional', 'Soul (Region:KokiriForest)')):
            plan = plan_souls(mode, [baba], REGIONS)
            for location in ('Deku Baba Sticks', 'Deku Baba Nuts'):
                self.assertEqual(plan['location_requirements'][location], {item})

    def test_a_soul_hidden_after_the_first_adult_visit_blocks_the_tomb_song(self):
        from oot_rando.logic import rando_options
        from oot_rando.logic.world import World
        from oot_rando.randomizer import full_randomizer as r
        from test_map_ages import map_sources, KF_CHILD, KF_ADULT
        bat = enemy('1', 'Enemy_Keese', 'Graveyard', [])
        door = {'resource': bat['resource'], 'index': 2, 'hash': '2',
                'actor': 'Obj_SwitchShutter_A_02', 'presence': None}
        bat['locks'] = [{'counter': bat['resource'] + '#3', 'doors': [door]}]
        options = rando_options.validate(dict(shuffle_rocks=True, shuffle_enemy_spawns='all',
            door_of_time_requirement='song', start_inventory_from_pool={
                'Ocarina': 1, 'Zeldas Lullaby': 1, 'Kokiri Sword': 1}))
        c = r.prepare(World(), options, {}, [bat], 'tomb-soul-cycle', extra=map_sources())
        for location, item in list(c.base.items()):
            if item == 'Song of Time':
                c.base[location] = None
        c.base['Song from Royal Familys Tomb'] = 'Song of Time'
        state, _, _ = c.sweep({KF_ADULT: 'Soul (Keese)'})
        self.assertFalse(state.has('Song of Time'))
        self.assertFalse(state.has('Time Travel'))
        self.assertFalse(state.has('Soul (Keese)'))
        self.assertEqual(r.child_door_missing(c, {KF_ADULT: 'Soul (Keese)'}), ['Song of Time'])
        state, _, _ = c.sweep({KF_CHILD: 'Soul (Keese)'})
        self.assertTrue(state.has('Song of Time'))
        self.assertTrue(state.has('Time Travel'))
        self.assertEqual(r.child_door_missing(c, {KF_CHILD: 'Soul (Keese)'}), [])

    def test_replay_rejects_unreachable_souls_even_if_victory_is_available(self):
        from unittest.mock import patch
        from oot_rando.logic import rando_options
        from oot_rando.logic.world import World
        from oot_rando.randomizer import full_randomizer as r
        from test_map_ages import map_sources, KF_CHILD
        bat = enemy('1', 'Enemy_Keese', 'Graveyard', [])
        options = rando_options.validate(dict(shuffle_rocks=True, shuffle_enemy_spawns='all',
                                             open_door_of_time=True, accessibility='minimal'))
        c = r.prepare(World(), options, {}, [bat], 'soul-self-lock', extra=map_sources())
        c.starting['Triforce'] = 1
        c.logic.virtual[r.vname(KF_CHILD)].append('Souls|Soul (Keese)')
        with patch.object(r, 'prepare', return_value=c):
            result = r.plan(c.data, options, {}, [bat], 'replay', forced={KF_CHILD: 'Soul (Keese)'})
        self.assertFalse(result['beatable'])
        self.assertEqual(result['unreachable_souls'], ['Soul (Keese)'])
        c.pool = ['Rupees (5)'] * len(c.shuffled)
        c.progression = []
        with patch.object(r, 'prepare', return_value=c), patch.object(r, 'MAX_ATTEMPTS', 1):
            with self.assertRaisesRegex(r.FillError, 'Unreachable enemy souls: Soul \\(Keese\\)'):
                r.plan(c.data, options, {}, [bat], 'invalid-soul-route')


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


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class NativeCombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from game_fixture import scan_maps
        from oot_rando.logic.world import World
        cls.maps, cls.groups, cls.enemies = scan_maps()
        cls.data = World()

    def test_native_ai_only_grotto_fights_guard_chests_without_spawn_type(self):
        from oot_rando.patching.soul_adapter import chest_requirements
        plan = plan_souls('all', self.enemies, self.data.regions)
        for module, item in (('HidingHole_Level_Hole_25', 'Soul (Lizalfos)'),
                             ('HidingHole_Level_Hole_21', 'Soul (Wolfos)'),
                             ('HidingHole_Level_Hole_01', 'Soul (DekuScrub)'),
                             ('HidingHole_Level_Hole_05', 'Soul (ReDead)')):
            targets = {target for e in self.enemies for c in e.get('combat', ())
                       if module in c['logic'] for target in c['targets']}
            groups = [(gid, variants) for gid, variants in self.groups.items()
                      if any(v['hash'] in targets for v in variants)]
            self.assertTrue(groups, module)
            for gid, variants in groups:
                with self.subTest(module=module, chest=gid):
                    self.assertNotEqual(variants[0]['dynamic'].get('SpawnType'), 1)
                    self.assertIn(item, chest_requirements(plan, {
                        'id': gid, 'folder': variants[0]['folder'], 'variants': variants}, ()))

    def test_water_room_counter_resolves_enemies_in_another_ai_group(self):
        found = [e for e in self.enemies if any('WaterTemple_Level_Room_17' in c['logic']
                                               for c in e.get('combat', ()))]
        self.assertEqual(len(found), 2)
        self.assertTrue(all(e['actor'] == 'Enemy_Spike' for e in found))

    def test_soul_requirements_cannot_be_bypassed_by_another_graph_entrance(self):
        from oot_rando.logic.rules import Logic
        for mode in ('bosses', 'regional', 'all'):
            plan = plan_souls(mode, self.enemies, self.data.regions)
            logic = Logic(self.data, extra_exit_requirements=plan['exit_requirements'],
                          extra_location_requirements=plan['location_requirements'])
            all_items = {item: 200 for item in logic.referenced | set(plan['items'])}
            for item in sorted({item for needs in plan['exit_requirements'].values() for item in needs}):
                state, _, _ = logic.sweep({}, logic.new_state({k: v for k, v in all_items.items() if k != item}))
                for (_, target), needs in plan['exit_requirements'].items():
                    if item in needs:
                        with self.subTest(mode=mode, soul=item, target=target):
                            self.assertNotIn(target, state.reached['child'] | state.reached['adult'])


if __name__ == '__main__':
    unittest.main()
