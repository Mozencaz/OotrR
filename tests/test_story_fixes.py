"""Story locks of the remake (patching/story_fixes.py). NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest
from unittest import mock

from oot_rando.formats import byml_codec
from oot_rando.formats.byml_writer import patch_strings
from oot_rando.formats.inspect_resources import Byml
from oot_rando.logic import rando_options
from oot_rando.patching import story_fixes as s
from oot_rando.formats.evfl_tools import links_to, params_by_event, parse_flow

NUP = os.environ.get('OOT_NUP')


class ZoraRiverWallUnits(unittest.TestCase):
    @mock.patch.object(s, 'ZORA_RIVER_WALLS', tuple(range(10, 17)))   # 32-bit hashes in the fixture
    def test_river_mouth_walls_become_child_only(self):
        actors = [{'Gyaml': 'Obj_BrokenRock_A_01', 'Hash': 1}]
        actors += [{'Gyaml': s.ZORA_RIVER_WALL, 'Hash': h} for h in s.ZORA_RIVER_WALLS]
        actors.append({'Gyaml': s.ZORA_RIVER_WALL, 'Hash': 2})     # another wall of the map
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': actors}})
        edits, indices = s.zora_river_wall_edits(Byml(raw).root)
        self.assertEqual(indices, list(range(1, 1 + len(s.ZORA_RIVER_WALLS))))
        root = Byml(patch_strings(raw, edits)).root
        for index in indices:
            self.assertEqual(root['Actors'][index]['Presence'], s.ZORA_RIVER_WALL_PRESENCE_ENTRY)
        self.assertNotIn('Presence', root['Actors'][0])
        self.assertNotIn('Presence', root['Actors'][-1])
        with self.assertRaises(ValueError):    # never applied twice
            s.zora_river_wall_edits(root)
        with self.assertRaises(ValueError):    # a wall missing
            s.zora_river_wall_edits({'Actors': actors[:3]})


class LakeTreeWallUnits(unittest.TestCase):
    @mock.patch.object(s, 'LAKE_TREE_WALL_HASH', 10)   # 32-bit hash in the fixture
    def test_island_tree_wall_becomes_child_only(self):
        actors = [{'Gyaml': 'Land_LakeHrl_Tree_A_01', 'Hash': 1},
                  {'Gyaml': s.LAKE_TREE_WALL, 'Hash': 10, 'Presence': dict(s.LAKE_TREE_WALL_VANILLA)},
                  {'Gyaml': s.LAKE_TREE_WALL, 'Hash': 2}]
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': actors}})
        edits, index = s.lake_tree_wall_edits(Byml(raw).root)
        self.assertEqual(index, 1)
        root = Byml(patch_strings(raw, edits)).root
        self.assertEqual(root['Actors'][1]['Presence'], s.LAKE_TREE_WALL_PRESENCE_ENTRY)
        self.assertEqual(root['Actors'][0], actors[0])
        self.assertEqual(root['Actors'][2], actors[2])
        with self.assertRaises(ValueError):    # never applied twice
            s.lake_tree_wall_edits(root)
        with self.assertRaises(ValueError):    # wall missing
            s.lake_tree_wall_edits({'Actors': actors[:1]})


class KakarikoBurningUnits(unittest.TestCase):
    @staticmethod
    def gamedata(programs, medals=s.KAKARIKO_MEDALS):
        from oot_rando.patching.soul_adapter import murmur3
        U32, U64 = byml_codec.U32, byml_codec.U64
        data = {'Bool': [{'Hash': U32(murmur3(n)), 'DefaultValue': False, 'ResetTypeValue': 0, 'SaveFileIndex': 0}
                         for n in medals],
                'BoolExp': [{'Hash': U32(murmur3(n)), 'ResetTypeValue': 0, 'SaveFileIndex': -1,
                             'Values': [[U64(v) for v in step] for step in p]} for n, p in programs.items()]}
        return byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Data': data}})

    def test_burning_and_burnt_banc_read_the_three_medallions(self):
        from oot_rando.patching.soul_adapter import murmur3
        vanilla = {name: pair[0] for name, pair in s._kakariko_programs().items()}
        raw = self.gamedata(vanilla)
        self.assertFalse(s.kakariko_burning_applied(raw))
        patched, report = s.kakariko_burning_on_medallions(raw)
        self.assertTrue(s.kakariko_burning_applied(patched))
        self.assertEqual(report['medallions'], list(s.KAKARIKO_MEDALS))
        programs = {int(e['Hash']): [[int(v) for v in st] for st in e['Values']]
                    for e in byml_codec.load(patched)['root']['Data']['BoolExp']}
        medals = [[0, murmur3(n)] for n in s.KAKARIKO_MEDALS] + [[3], [3]]
        adult = [[0, murmur3('Sequence_IsChildhood')], [5]]
        self.assertEqual(programs[murmur3(s.KAKARIKO_ALTERNATIVE)], adult + medals + [[3]])
        burning = programs[murmur3(s.KAKARIKO_BURNING)]
        self.assertEqual(burning[:len(adult) + len(medals)], adult + medals)
        self.assertNotIn([10, s.KAKARIKO_SAGES], burning)
        with self.assertRaises(ValueError):    # never applied twice
            s.kakariko_burning_on_medallions(patched)
        with self.assertRaises(ValueError):    # a medallion flag missing
            s.kakariko_burning_on_medallions(self.gamedata(vanilla, s.KAKARIKO_MEDALS[:2]))


class EscapeStoneUnits(unittest.TestCase):
    def test_the_option_picks_the_stones_zelda_asks_for(self):
        self.assertEqual(s.STONE_SETS['all'], ('Item_Stone_Forest', 'Item_Stone_Fire', 'Item_Stone_Water'))
        self.assertEqual(s.STONE_SETS['vanilla'], ('Item_Stone_Fire', 'Item_Stone_Water'))   # the native check's
        self.assertEqual(set(s.STONE_SETS), set(rando_options.BY_NAME['door_of_time_requirement'].allowed()))
        for value, stones in s.STONE_SETS.items():
            self.assertEqual(s.escape_stones({'spiritual_stones': 'door', 'door_of_time_requirement': value}), stones)

    def test_stored_options_without_the_option_ask_for_every_stone(self):
        # Seeds made before the option (upstream's) asked for the three stones.
        self.assertEqual(s.escape_stones({}), s.STONE_SETS['all'])
        self.assertEqual(s.escape_stones(rando_options.recorded(rando_options.defaults())), s.STONE_SETS['all'])

    def test_the_story_fixes_carry_the_chosen_stones(self):
        for value, stones in s.STONE_SETS.items():
            fixes = {key: fix for _, key, fix in s.flow_fixes(stones)}
            for key in ('zelda_escape', 'zelda_talk_stones'):
                self.assertEqual(fixes[key].keywords, {'stones': stones}, (value, key))
        self.assertEqual([key for _, key, _ in s.flow_fixes(s.STONE_SETS['all'])],
                         [key for _, key, _ in s.flow_fixes(s.STONE_SETS['vanilla'])])


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class GameFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        return self.decompress(self.nup.read(self.nup.latest('romfs/' + path)), self.d)

    def chart(self, raw):
        return {e.name: e for e in parse_flow(raw).flowchart.events}

    def check_kept(self, source, raw):
        before, after = params_by_event(parse_flow(source)), params_by_event(parse_flow(raw))
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)

    def test_darunia_gift_while_never_played(self):
        source = self.read(s.FIRE_STONE_FLOW)
        raw, _ = s.darunia_gift_after_dungeon(source)
        events = self.chart(raw)
        check = events['Event39'].data            # past SariaMelodyPlay (quest done)...
        given = check.cases[0].v
        self.assertEqual(given.name, 'RandoDaruniaGiftGiven')
        self.assertEqual(given.data.params.data, {'GameDataName': s.DARUNIA_GIFT_PLAYED, 'Index': -1})
        self.assertEqual(given.data.cases[1].v.name, 'Event31')        # ...gift scene if never played
        self.assertEqual(given.data.cases[1].v.data.params.data['EventName'], 'Dm_Goron_0030')
        self.assertEqual(check.cases[1].v.name, 'Event31')             # vanilla path unchanged
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.darunia_gift_after_dungeon(raw)

    def test_gift_scene_never_moves_the_quest_back(self):
        source = self.read(s.DARUNIA_GIFT_FLOW)
        raw, report = s.keep_fire_quest_forward(source)
        events = self.chart(raw)
        guard = next(e for e in events.values()
                     if getattr(e.data, 'nxt', None) is not None and e.data.nxt.v is not None
                     and e.data.nxt.v.name == 'RandoFireQuestForward')
        self.assertIsNotNone(guard)
        cases = events['RandoFireQuestForward'].data.cases
        self.assertEqual(cases[1].v.name, 'Event121')                  # vanilla: still before the step
        self.assertEqual(cases[0].v.name, report['skip_to'])           # quest already further
        self.check_kept(source, raw)

    def test_second_malon_waits_for_talon(self):
        source = self.read(s.EPONA_FLOW)
        raw, _ = s.second_malon_after_talon(source)
        events = self.chart(raw)
        awake = events['Event38'].data.cases[1].v
        self.assertEqual(awake.name, 'RandoTalonAwake')
        self.assertEqual(awake.data.params.data, {'GameDataName': s.TALON_AWAKE, 'Index': -1})
        self.assertEqual(awake.data.cases[0].v.name, 'Event36')
        away = awake.data.cases[1].v
        self.assertEqual(away.data.params.data, {'GameDataName': s.SECOND_MALON, 'Value': False, 'Index': -1})
        self.check_kept(source, raw)

    def test_bombchu_bowling_open(self):
        source = self.read(s.BOWLING_FLOW)
        raw, _ = s.open_bombchu_bowling(source)
        cases = self.chart(raw)['Event137'].data.cases
        self.assertIs(cases[0].v, cases[1].v)
        self.check_kept(source, raw)

    def test_great_fairies_open(self):
        source = self.read(s.FAIRY_CALL_FLOW)
        raw, report = s.open_great_fairies(source)
        cases = self.chart(raw)['Event8'].data.cases
        self.assertIs(cases[0].v, cases[1].v)
        self.assertNotEqual(cases[1].v.name, report['refusal'])
        self.check_kept(source, raw)

    def test_great_fairies_counted_by_their_flags(self):
        raw, report = s.open_and_count_great_fairies(self.read(s.FAIRY_CALL_FLOW))
        events = self.chart(raw)
        names = {events[e].data.params.data['GameDataName'] for e in report['queries']}
        self.assertEqual(names, set(s.fairy_flags().values()))
        self.assertIs(events['Event8'].data.cases[0].v, events['Event8'].data.cases[1].v)

    def test_great_fairy_reward_sets_her_own_flag(self):
        for name, reward, actor in s.GREAT_FAIRIES:
            with self.subTest(name):
                source = self.read(s.fairy_flow(name))
                raw, report = s._fairy_reward_flag(name, reward, actor)(source)
                events = self.chart(raw)
                given = events['RandoGreatFairyGiven']
                self.assertEqual(given.data.params.data,
                                 {'GameDataName': s.GREAT_FAIRY_FLAG_PREFIX + name, 'Value': True, 'Index': -1})
                self.assertEqual(given.data.nxt.v.name, reward)
                queried = {e.data.params.data.get('GameDataName') for e in events.values()
                           if type(e.data).__name__ == 'SwitchEvent' and e.data.params is not None}
                self.assertNotIn('IsGet.' + actor, queried)
                self.assertIn(s.GREAT_FAIRY_FLAG_PREFIX + name, queried)
                self.assertFalse(queried & {'IsGet.' + a for _, _, a in s.GREAT_FAIRIES})

    def test_great_fairy_reward_accepts_a_song_silent_add(self):
        # A song on a Great Fairy: song_adapter's text_get turned her pose into a silent add.
        name, reward, actor = s.GREAT_FAIRIES[0]
        flow = s._Chart(self.read(s.fairy_flow(name)))
        gift = flow.event(reward, 'SubFlowEvent')
        gift.data.res_flowchart_name, gift.data.entry_point_name = 'GetPouchContent', 'GetPouchContentByActorName'
        gift.data.params.data = {'ActorName': 'Item_Melody_StormSong'}
        flow.expected[reward] = {'ActorName': 'Item_Melody_StormSong'}
        source, _ = flow.write()
        raw, _ = s._fairy_reward_flag(name, reward, actor)(source)
        events = self.chart(raw)
        self.assertEqual(events['RandoGreatFairyGiven'].data.nxt.v.name, reward)
        self.assertEqual(events[reward].data.entry_point_name, 'GetPouchContentByActorName')

    def test_great_fairy_flags_unique(self):
        self.assertEqual(len(s.great_fairy_saved_flags()), 6)

    def test_zora_river_walls(self):
        raw = self.read(s.ZORA_RIVER_MAP)
        before = Byml(raw).root
        edits, indices = s.zora_river_wall_edits(before)
        root = Byml(patch_strings(raw, edits)).root
        walls = [a for a in root['Actors'] if a.get('Hash') in s.ZORA_RIVER_WALLS]
        self.assertEqual(len(walls), 7)
        self.assertTrue(all(a['Presence'] == s.ZORA_RIVER_WALL_PRESENCE_ENTRY for a in walls))
        # Same walls as the boulders' simultaneous group; nothing else changes.
        group = next(g for g in before['SimultaneousGroups'] if set(s.ZORA_RIVER_WALLS) <= set(g))
        self.assertEqual(len(group), 9)
        for index, (a, b) in enumerate(zip(before['Actors'], root['Actors'])):
            if index not in indices:
                self.assertEqual(a, b)

    def test_zora_river_child_walls(self):
        # The same seven walls in the child map: same places, adult-only there.
        adult = {tuple(round(x, 1) for x in a['Translate']) for a in Byml(self.read(s.ZORA_RIVER_MAP)).root['Actors']
                 if a.get('Hash') in s.ZORA_RIVER_WALLS}
        raw = self.read(s.ZORA_RIVER_CHILD_MAP)
        before = Byml(raw).root
        edits, indices = s.zora_river_child_wall_edits(before)
        root = Byml(patch_strings(raw, edits)).root
        walls = [a for a in root['Actors'] if a.get('Hash') in s.ZORA_RIVER_CHILD_WALLS]
        self.assertEqual({tuple(round(x, 1) for x in a['Translate']) for a in walls}, adult)
        self.assertTrue(all(a['Presence'] == {'FlagName': 'Sequence_IsChildhood', 'IsCheckLazy': False,
                                              'IsNegation': True} for a in walls))
        for index, (a, b) in enumerate(zip(before['Actors'], root['Actors'])):
            if index not in indices:
                self.assertEqual(a, b)

    def test_lake_tree_wall(self):
        raw = self.read(s.LAKE_TREE_MAP)
        before = Byml(raw).root
        edits, index = s.lake_tree_wall_edits(before)
        root = Byml(patch_strings(raw, edits)).root
        self.assertEqual(root['Actors'][index]['Presence'], s.LAKE_TREE_WALL_PRESENCE_ENTRY)
        self.assertEqual(root['Actors'][index]['Translate'], before['Actors'][index]['Translate'])
        for position, (a, b) in enumerate(zip(before['Actors'], root['Actors'])):
            if position != index:
                self.assertEqual(a, b)

    def test_pedestal_open_from_first_adult_arrival(self):
        # 15-16/11: adult Link could not go back to child before the Forest Temple.
        import ainb
        raw = self.nup.read(self.nup.latest('romfs/' + s.PEDESTAL_MODULE))
        patched, report = s.pedestal_after_first_adult_arrival(raw)
        before, after = (ainb.AINB.from_binary(x).as_dict() for x in (raw, patched))
        gate = after['Nodes'][0]['Parameters']['Inputs']['String'][0]
        self.assertEqual((gate['Name'], gate['Default Value']), ('GameDataNameBoolExp', s.PEDESTAL_GATE))
        before['Nodes'][0]['Parameters']['Inputs']['String'][0]['Default Value'] = s.PEDESTAL_GATE
        self.assertEqual(before, after)
        self.assertEqual(report['before'], s.PEDESTAL_BEFORE)
        with self.assertRaises(ValueError):    # never applied twice
            s.pedestal_after_first_adult_arrival(patched)

    def test_temple_sheik_leaves_the_pedestal_between_his_scenes(self):
        # 20/11: Sheik stood at the pedestal until the Prelude: no put-in prompt.
        import ainb
        import copy
        from oot_rando.patching.game_defaults import GAMEDATA
        from oot_rando.patching.soul_adapter import murmur3
        raw = self.nup.read(self.nup.latest('romfs/' + s.SHEIK_TEMPLE_MODULE))
        patched, report = s.sheik_leaves_the_pedestal(raw)
        before, after = (ainb.AINB.from_binary(x).as_dict() for x in (raw, patched))
        expected = copy.deepcopy(before)
        npc, prelude, reader = expected['Nodes']
        next(p for p in npc['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Delete')['Node Index'] = 2
        npc['Queries'], npc['Plugs'] = [2], {'Generic': [{'Node Index': 2, 'Name': 'Logic_Delete'}]}
        reader['Parameters']['Inputs']['String'][0]['Default Value'] = s.SHEIK_TEMPLE_GONE
        reader['Parameters']['Outputs']['Bool'][0]['Is Output'] = True
        prelude['Parameters']['Outputs']['Bool'][0]['Is Output'] = False
        self.assertEqual(after, expected)
        with self.assertRaises(ValueError):
            s.sheik_leaves_the_pedestal(patched)
        gamedata = self.read(GAMEDATA)
        with_exp, _ = s.sheik_temple_expression(gamedata)
        self.assertTrue(s.sheik_temple_applied(with_exp))
        self.assertFalse(s.sheik_temple_applied(gamedata))
        old, new = (byml_codec.load(x)['root']['Data'] for x in (gamedata, with_exp))
        self.assertEqual(new['BoolExp'][:-1], old['BoolExp'])
        self.assertEqual(int(new['BoolExp'][-1]['Hash']), murmur3(s.SHEIK_TEMPLE_GONE))
        with self.assertRaises(ValueError):
            s.sheik_temple_expression(with_exp)
        # Sheik stands beside the sword in the adult temple map.
        root = Byml(self.read(s.TEMPLE_MAP)).root
        sheik = next(a for a in root['Actors'] if a.get('Gyaml') == s.SHEIK)
        sword = next(a for a in root['Actors'] if a.get('Gyaml') == 'Obj_TimeTemple_MasterSword_A_01')
        self.assertLess(sum((a - b) ** 2 for a, b in zip(sheik['Translate'], sword['Translate'])) ** 0.5, 1.6)

    def test_prelude_requires_forest_medallion_and_preserves_native_one_shot(self):
        import ainb
        import copy
        raw = self.nup.read(self.nup.latest('romfs/' + s.PRELUDE_MODULE))
        patched, report = s.prelude_on_forest_medallion(raw)
        before = ainb.AINB.from_binary(raw).as_dict()
        after = ainb.AINB.from_binary(patched).as_dict()
        expected = copy.deepcopy(before)
        node = expected['Nodes'][3]
        node['Name'] = 'HoldGameDataGetBoolSimple'
        node['Parameters']['Inputs']['String'][0].update(
            {'Name': 'GameDataNameBool', 'Default Value': s.PRELUDE_MEDAL})
        node['Parameters']['Inputs']['Int'] = [{'Name': 'GameDataArrayIndex', 'Default Value': -1,
            'Node Index': -1, 'Output Index': 0, 'Flags': ['Uses Default', 'Is Output']}]
        self.assertEqual(after, expected)
        self.assertEqual(report['medallion'], s.PRELUDE_MEDAL)
        # Native area disappears after teaching, regardless of the shuffled song.
        root = Byml(self.read(s.TEMPLE_MAP)).root
        area = next(a for a in root['Actors'] if a['Hash'] == 3406708549665898725)
        self.assertEqual(area['Presence'], {'FlagName': 'Market_Adult_GetLightPrelude',
                                          'IsCheckLazy': False, 'IsNegation': True})
        with self.assertRaises(ValueError):
            s.prelude_on_forest_medallion(patched)

    def test_kakariko_burning_on_medallions_in_game_data(self):
        from oot_rando.patching.game_defaults import GAMEDATA
        raw = self.read(GAMEDATA)
        patched, report = s.kakariko_burning_on_medallions(raw)
        self.assertTrue(s.kakariko_burning_applied(patched))
        self.assertEqual(report['expressions'], [s.KAKARIKO_BURNING, s.KAKARIKO_ALTERNATIVE])
        before = byml_codec.load(raw)['root']['Data']
        after = byml_codec.load(patched)['root']['Data']
        # Only the two programs change; the sages' expression itself stays for its other readers.
        self.assertEqual(len(before['BoolExp']), len(after['BoolExp']))
        from oot_rando.patching.soul_adapter import murmur3
        changed = {murmur3(s.KAKARIKO_BURNING), murmur3(s.KAKARIKO_ALTERNATIVE)}
        for old, new in zip(before['BoolExp'], after['BoolExp']):
            if int(old['Hash']) not in changed:
                self.assertEqual(old, new)
        self.assertEqual(before['Bool'], after['Bool'])
        with self.assertRaises(ValueError):
            s.kakariko_burning_on_medallions(patched)

    def test_prelude_does_not_roll_back_later_sages(self):
        raw = self.read('Event/EventFlow/AllSage.bfevfl.zs')
        patched, report = s.prelude_keeps_later_sage_progress(raw)
        events = self.chart(patched)
        gate = events['Event37'].data.nxt.v
        self.assertEqual(gate.data.params.data, {'GameDataName': s.PRELUDE_LATER_STEP})
        self.assertNotIn(0, gate.data.cases)     # later progress: finish after teaching
        self.assertIs(gate.data.cases[1].v, events['Event34'])
        self.assertEqual(report['rollback'], 'Event34')
        with self.assertRaises(ValueError):
            s.prelude_keeps_later_sage_progress(patched)

    def test_light_arrows_require_both_medallions_and_only_play_once(self):
        import ainb
        import itertools
        raw = self.nup.read(self.nup.latest('romfs/' + s.LIGHT_ARROWS_MODULE))
        patched, report = s.light_arrows_on_medallions(raw)
        nodes = ainb.AINB.from_binary(patched).as_dict()['Nodes']
        self.assertEqual(nodes[8]['Plugs']['Generic'], [{'Node Index': 5, 'Name': 'BoolMulti'}])

        def evaluate(index, output, flags, touching):
            node = nodes[index]
            if node['Name'] == 'HoldGameDataGetBoolSimple':
                return flags[node['Parameters']['Inputs']['String'][0]['Default Value']]
            if node['Name'] == 'HoldActorObserverBySensorHitInfo':
                return touching
            if node['Name'] == 'InvBool.module':
                return not evaluate(2, 0, flags, touching)
            if node['Name'] == 'OperateAND':
                sources = node['Parameters']['Inputs']['Bool'][0]['Sources']
                value = all(evaluate(p['Node Index'], p['Output Index'], flags, touching) for p in sources)
                return value if output == 1 else not value
            raise AssertionError(node['Name'])

        for shadow, spirit, played, touching in itertools.product((False, True), repeat=4):
            flags = dict(zip((*s.LIGHT_ARROWS_MEDALS, s.LIGHT_ARROWS_PLAYED), (shadow, spirit, played)))
            with self.subTest(flags=flags, touching=touching):
                area = next(p for p in nodes[1]['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Create')
                request = next(p for p in nodes[0]['Parameters']['Inputs']['Bool'] if p['Name'] == 'EventRequestTrigger')
                self.assertEqual(evaluate(area['Node Index'], area['Output Index'], flags, touching),
                                 shadow and spirit and not played)
                self.assertEqual(evaluate(request['Node Index'], request['Output Index'], flags, touching),
                                 shadow and spirit and not played and touching)
        self.assertEqual(report['medallions'], list(s.LIGHT_ARROWS_MEDALS))
        # Geometry, event binding and collision test are untouched.
        before = ainb.AINB.from_binary(raw).as_dict()['Nodes']
        for index in (0, 3):
            self.assertEqual(before[index], nodes[index])
        with self.assertRaises(ValueError):
            s.light_arrows_on_medallions(patched)

    def for_each_stone_set(self, check):
        for value, stones in s.STONE_SETS.items():
            with self.subTest(spiritual_stones=value):
                check(stones)

    def test_zelda_escape_on_stones_at_item_get(self):
        self.for_each_stone_set(self.check_escape_at_item_get)

    def check_escape_at_item_get(self, stones):
        from oot_rando.patching.qol_patches import ocarina_guide_on_get
        source = ocarina_guide_on_get(self.read(s.ACTION_GUIDE_FLOW))[0]
        raw, report = s.zelda_escape_on_item_get(source, stones)
        self.assertEqual(report['stones'], list(stones))
        events = self.chart(raw)
        started = events['RandoDoorStonesStarted'].data
        self.assertEqual(started.params.data, {'GameDataName': s.DOOR_STARTED})
        before = started.cases[0].v.data                       # send-off done...
        self.assertEqual(before.params.data, {'GameDataName': s.DOOR_BEFORE_ESCAPE})
        check, held = before.cases[1].v, []                    # ...and Step03 not reached
        while check.name.startswith('RandoDoorStonesStone'):
            params = check.data.params.data            # the saved flag, not the pouch
            self.assertEqual(params['Index'], -1)
            held.append(params['GameDataName'].removeprefix(s.STONE_FLAG_PREFIX))
            check = check.data.cases[0].v
        self.assertEqual(held, list(stones))
        native_step03 = self.chart(self.read(s.DOOR_FLOW))['Event37'].data.params.data
        self.assertEqual(check.data.params.data, native_step03)       # the native request, IsWaitEnd too
        bridge = check.data.nxt.v
        self.assertEqual(bridge.data.params.data, {'GameDataName': s.BRIDGE_CLOSED, 'Value': True, 'Index': -1})
        self.assertEqual(bridge.data.nxt.v.data.nxt.v.name, 'RandoOcarinaHeld')   # then the vanilla get
        self.check_kept(source, raw)

    def test_door_flow_send_off_and_native_check(self):
        self.for_each_stone_set(self.check_door_flow)

    def check_door_flow(self, stones):
        source = self.read(s.DOOR_FLOW)
        raw, _ = s.zelda_escape_door_flow(source, stones)
        events = self.chart(raw)
        guard = events['RandoDoorCheckForward'].data
        self.assertEqual(set(guard.cases), {1})                # Step03 reached: nothing
        # Dungeon end: the stones first, then the native dungeon check.
        dungeon_end = guard.cases[1].v
        self.assertEqual(dungeon_end.name, 'RandoDungeonEndStonesStarted')
        self.assertEqual(dungeon_end.data.cases[1].v.name, 'Event38')     # send-off not done: native
        check = dungeon_end.data.cases[0].v.data.cases[1].v                # before Step03: the stones
        while check.name.startswith('RandoDungeonEndStonesStone'):
            self.assertEqual(check.data.cases[1].v.name, 'Event38')        # one missing: native
            check = check.data.cases[0].v
        self.assertEqual(check.data.params.data, events['Event37'].data.params.data)
        self.assertIsNone(events['RandoDungeonEndStonesCount'].data.nxt.v)  # Step03: native skipped
        self.assertEqual(sum(name.startswith('RandoSendOffStonesStone') for name in events), len(stones))
        # The native check reads the Fire and Water quests alone (never the Kokiri Emerald)...
        fire, both = events['Event38'], events['Event39']
        self.assertEqual(fire.data.params.data, {'GameDataName': 'Get_StoneOfFire_IsCompleted_Exp'})
        self.assertIs(fire.data.cases[0].v, both)
        # ...and, 17/11: both dungeon quests done no longer give Step03 without the stones.
        self.assertEqual(both.data.params.data, {'GameDataName': 'Get_StoneOfWater_IsCompleted_Exp'})
        self.assertEqual({k: v.v.name for k, v in both.data.cases.items()}, {1: 'Event147'})
        started = events['Event7'].data.nxt.v.data             # after Step02 of the send-off
        self.assertEqual(started.params.data, {'GameDataName': s.FIRE_QUEST_STARTED})
        self.assertEqual(started.cases[1].v.name, 'Event62')   # fire quest moved only if not started
        self.assertEqual(started.cases[0].v.name, 'RandoSendOffStonesStarted')
        self.assertEqual(events['Event62'].data.nxt.v.name, 'RandoSendOffStonesStarted')
        self.check_kept(source, raw)

    def test_zelda_escape_on_stones_at_zelda_talk(self):
        self.for_each_stone_set(self.check_escape_at_zelda_talk)

    def check_escape_at_zelda_talk(self, stones):
        # 17/11: the last stone got after the send-off; talking to Zelda checks them again.
        source, _ = s.door_of_time_forward(self.read(s.ZELDA_FLOW))
        raw, report = s.zelda_escape_on_talk(source, stones)
        self.assertEqual(report['start'], 'RandoTalkStonesStarted')
        events = self.chart(raw)
        started = events['RandoTalkStonesStarted'].data
        self.assertEqual(started.params.data, {'GameDataName': s.DOOR_STARTED})
        self.assertEqual(started.cases[1].v.name, 'Event99')                  # before the send-off: vanilla talk
        before = started.cases[0].v.data
        self.assertEqual(before.params.data, {'GameDataName': s.DOOR_BEFORE_ESCAPE})
        self.assertEqual(before.cases[0].v.name, 'Event99')                   # Step03 reached: vanilla talk
        check, held = before.cases[1].v, []
        while check.name.startswith('RandoTalkStonesStone'):
            self.assertEqual(check.data.cases[1].v.name, 'Event99')           # one missing: vanilla talk
            held.append(check.data.params.data['GameDataName'].removeprefix(s.STONE_FLAG_PREFIX))
            check = check.data.cases[0].v
        self.assertEqual(held, list(stones))
        self.assertEqual(check.data.params.data, self.chart(self.read(s.DOOR_FLOW))['Event37'].data.params.data)
        self.assertEqual(events['RandoTalkStonesCount'].data.nxt.v.name, 'Event99')   # then the talk
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.zelda_escape_on_talk(raw, stones)

    def test_gohma_scene_skips_stone_menu_presentation(self):
        # 15/11: the first-stone menu presentation showed the stones, then none.
        source = self.read(s.GOHMA_STONE_FLOW)
        self.assertEqual(self.chart(source)['Event56'].data.nxt.v.name, 'Event52')
        raw, report = s.skip_stone_menu_presentation(source)
        self.assertEqual(report['skipped'], 'Event52')
        self.assertIsNone(self.chart(raw)['Event56'].data.nxt.v)
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.skip_stone_menu_presentation(raw)

    def test_dampe_first_race_until_its_prize_is_opened(self):
        # 17/11: with the Hookshot found elsewhere, the first race (and its chest) was skipped.
        source = self.read(s.DAMPE_FLOW)
        raw, report = s.dampe_first_race_until_prize(source)
        events = self.chart(raw)
        self.assertEqual(report['checks'], sorted(s.DAMPE_HOOKSHOT_CHECKS))
        start = events['RandoDampeEvent129']
        self.assertEqual(dict(start.data.params.data), {'GameDataName': s.DAMPE_FIRST_PRIZE, 'Index': -1})
        self.assertEqual({k: v.v.name for k, v in start.data.cases.items()}, {0: 'Event131', 1: 'Event287'})
        self.assertIs(events['Event462'].data.nxt.v, start)
        self.assertEqual(events['RandoDampeEvent18'].data.cases[1].v.name, 'RandoDampeEvent0')
        self.assertEqual(events['RandoDampeEvent262'].data.cases[1].v.name, 'RandoDampeEvent260')
        # Until the first prize is opened, the result shows the Hookshot chest whatever
        # ClearCount holds (saves where the first race already counted as cleared).
        gate = events['RandoDampeResult']
        self.assertEqual({k: v.v.name for k, v in gate.data.cases.items()}, {0: 'Event275', 1: 'Event277'})
        result = next(e for e in parse_flow(raw).flowchart.entry_points if e.name == 'Result')
        self.assertEqual(result.main_event.v.name, 'RandoDampeResult')
        # The race finish counts a clear only once the first prize is opened.
        finish = events['Event31'].data.nxt.v
        self.assertEqual(finish.name, 'RandoDampeEvent442')
        self.assertEqual({k: v.v.name for k, v in finish.data.cases.items()}, {0: 'Event379', 1: 'Event33'})
        mark = events['Event201'].data.nxt.v
        self.assertEqual((mark.name, dict(mark.data.params.data)['GameDataName']),
                         ('RandoDampeFirstPrizeOpened', s.DAMPE_FIRST_PRIZE))
        self.assertEqual(mark.data.nxt.v.name, 'Event95')
        # No live link reaches a Hookshot/Longshot check any more.
        chart = parse_flow(raw).flowchart
        live = {e.name for e in chart.events if e.name not in s.DAMPE_HOOKSHOT_CHECKS}
        for name in s.DAMPE_HOOKSHOT_CHECKS:
            old = next(e for e in chart.events if e.name == name)
            self.assertFalse([l for l in links_to(chart, old) if getattr(l[0], 'name', None) in live], name)
        # No reachable event of the race reads the Hookshot or Longshot any more.
        reachable, todo = set(), [p.main_event.v for p in chart.entry_points if p.main_event.v]
        while todo:
            e = todo.pop()
            if e.name in reachable:
                continue
            reachable.add(e.name)
            data = e.data
            for link in [getattr(data, 'nxt', None)] + list((getattr(data, 'cases', None) or {}).values())                     + list(getattr(data, 'forks', None) or []) + [getattr(data, 'join', None)]:
                if link is not None and getattr(link, 'v', None) is not None:
                    todo.append(link.v)
        readers = [e.name for e in chart.events if e.name in reachable and getattr(e.data, 'params', None) is not None
                   and {v for v in dict(e.data.params.data).values() if isinstance(v, str)} & {'Item_Hookshot', 'Item_Longshot'}]
        self.assertEqual(readers, [])
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.dampe_first_race_until_prize(raw)
        self.assertEqual(s.dampe_saved_flags(), {s.DAMPE_FIRST_PRIZE: False})

    def test_kokiri_exit_guard_lowers_wall_after_deku_tree(self):
        # 16/11: Zelda met before the Deku Tree, the guard's last schedule state hid the
        # only talk that lowers the bridge wall.
        source = self.read(s.KOKIRI_EXIT_FLOW)
        raw, report = s.kokiri_exit_guard_steps_aside(source)
        entries = {e.name: e for e in parse_flow(raw).flowchart.entry_points}
        first = entries['KokiriForest_Npc_Kokiri_007_Child_BlockEnd_Talk'].main_event.v
        self.assertEqual((first.name, report['flag']), ('RandoExitWallUp', s.KOKIRI_EXIT_WALL))
        self.assertEqual(dict(first.data.params.data), {'GameDataName': s.KOKIRI_EXIT_WALL, 'Index': -1})
        done = first.data.cases[0].v
        self.assertEqual(dict(done.data.params.data), {'GameDataName': s.DEKU_TREE_DONE})
        self.assertEqual({k: v.v.name for k, v in done.data.cases.items()}, {0: 'Event10', 1: 'Event60'})
        self.assertEqual(first.data.cases[1].v.name, 'Event60')
        self.assertEqual(entries['Get_StoneOfForest_IsCompleted_Exp_Talk'].main_event.v.name, 'Event10')
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.kokiri_exit_guard_steps_aside(raw)

    def test_link_goron_gives_tunic_outside_his_quest_step(self):
        # 19/11: the tunic only came at SageOfFire TalkDaruniaJr: never after the crater
        # (Bolero) moved the quest on, nor before Dodongo's Cavern.
        source = self.read(s.LINK_GORON_FLOW)
        raw, report = s.link_goron_gives_tunic(source)
        flow = parse_flow(raw).flowchart
        entry = {e.name: e for e in flow.entry_points}[s.LINK_GORON_TALK]
        has = entry.main_event.v
        self.assertEqual(dict(has.data.params.data), {'Actor': s.GORON_TUNIC, 'Num': 1})
        give = has.data.cases[1].v
        self.assertEqual((give.data.res_flowchart_name, give.data.entry_point_name),
                         ('Dm_SY_GetInEvent', 'GetInEvent_NotTurn_NotNpc'))
        self.assertEqual(give.data.params.data['ActorName'], s.GORON_TUNIC_GIFT)
        self.assertEqual((has.data.cases[0].v.name, give.data.nxt.v.name), ('Event99', 'Event99'))
        self.assertIn(flow.events.index(give), entry._sub_flow_event_indices)
        self.assertEqual(report['gift'], 'Obj_Armor_Goron')
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.link_goron_gives_tunic(raw)

    def steps(self):
        from oot_rando.patching.quest_guard import CHALLENGES, challenge_steps
        return challenge_steps(self.read(CHALLENGES))

    def test_door_of_time_steps_match_the_table(self):
        self.assertEqual(tuple(self.steps()['DoorOfTime']), s.DOOR_STEPS)

    def test_zelda_and_saria_never_move_door_of_time_back(self):
        # 16/11: Zelda's talk (Fire quest done) and Saria's Song set DoorOfTime back to
        # Srep2_1_1 from Step03: the drawbridge area (current step = Step03) vanished.
        for path, request in ((s.ZELDA_FLOW, 'Event42'), (s.SARIA_SONG_FLOW, 'Event172')):
            with self.subTest(path=path):
                source = self.read(path)
                raw, report = s.door_of_time_forward(source)
                self.assertEqual([(e, step) for e, step, _ in report['guarded']], [(request, 'Srep2_1_1')])
                events = self.chart(raw)
                guard = events['RandoDoorForward_0'].data
                self.assertEqual(guard.params.data, {'GameDataName': s.DOOR_PAST_SREP})
                self.assertEqual(guard.cases[1].v.name, request)         # before: vanilla request
                self.assertNotIn(0, guard.cases)                         # past: nothing (request ended the flow)
                self.check_kept(source, raw)
                with self.assertRaises(ValueError):
                    s.door_of_time_forward(raw)

    def test_zora_domain_arrival_keeps_king_zora_moved(self):
        # Discord 15/11: Zora's Domain reached from Lake Hylia, the letter delivered,
        # then the first arrival from Zora River set the quest back to Step03.
        source = self.read(s.ARRIVE_FLOW)
        raw, guarded = s.first_arrival_forward(s.ARRIVE_FLOW, source, self.steps())
        events = self.chart(raw)
        # Impa met or not, then: past the step? complete? only then the request.
        choice = events['Event46'].data
        for case, step, event in ((0, 'Step03_Impa', 'Event45'), (1, 'Step03', 'Event44')):
            after = choice.cases[case].v.data
            self.assertEqual(after.params.data, {'GameDataName': f'Get_StoneOfWater_IsAfter_{step}_Exp'})
            done = after.cases[1].v.data
            self.assertEqual(done.params.data, {'GameDataName': 'Get_StoneOfWater_IsCompleted_Exp'})
            self.assertEqual(done.cases[1].v.name, event)
            self.assertNotEqual(after.cases[0].v.name, event)    # past it: skipped
        colossus = events['Event82'].data.nxt.v.data             # after the Colossus presentation
        self.assertEqual(colossus.params.data, {'GameDataName': 'SageOfSpirit_IsAfter_Step04_Exp'})
        self.assertEqual({e for e, _, _ in guarded}, {'Event44', 'Event45', 'Event76'})
        self.check_kept(source, raw)

    def test_water_quest_never_moves_back_past_the_letter(self):
        # Discord 19/11: King Zora back in front of the fountain after leaving the
        # domain (Impa met late, Zora River owl, diving game won after the letter).
        from oot_rando.patching.quest_guard import step_requests
        source = self.read(s.WATER_FLOW)
        raw, guarded = s.first_arrival_forward(s.WATER_FLOW, source, self.steps())
        early = {e for e, step in step_requests(source, 'Get_StoneOfWater') if step in s.WATER_EARLY_STEPS}
        self.assertTrue({'Event64', 'Event80', 'Event45'} <= early)
        self.assertEqual({e for e, _, _ in guarded}, early)
        events = self.chart(raw)
        for event, step in (('Event64', 'Step01'), ('Event80', 'Step02'), ('Event45', 'Step05')):
            with self.subTest(event=event):
                guards = [e for e in events.values() if e.name.startswith(s.FORWARD_PREFIX)
                          and any(c.v.name == event for c in e.data.cases.values())]
                self.assertEqual([g.data.params.data for g in guards],
                                 [{'GameDataName': 'Get_StoneOfWater_IsCompleted_Exp'}])
                before = [e for e in events.values() if e.name.startswith(s.FORWARD_PREFIX)
                          and any(c.v is guards[0] for c in e.data.cases.values())]
                self.assertEqual([g.data.params.data for g in before],
                                 [{'GameDataName': f'Get_StoneOfWater_IsAfter_{step}_Exp'}])
        self.check_kept(source, raw)

    def test_trail_and_market_arrivals_keep_their_quests(self):
        steps = self.steps()
        for path, event in ((s.FIRE_STONE_FLOW, 'Event156'), (s.CASTLE_FLOW, 'Event51')):
            with self.subTest(path=path):
                source = self.read(path)
                raw, guarded = s.first_arrival_forward(path, source, steps)
                self.assertIn(event, {e for e, _, _ in guarded})
                self.check_kept(source, raw)
        files, report = s.keep_first_arrivals_forward(self.read, self.read('RSDB/Challenge.Product.111.rstbl.byml.zs'))
        self.assertEqual(set(files), set(s.FIRST_ARRIVAL_REQUESTS))

    def test_arrival_expressions_exist(self):
        from oot_rando.patching.quest_guard import check_expressions, after_expression
        from oot_rando.patching.soul_adapter import GAMEDATA
        names = []
        for requests in s.FIRST_ARRIVAL_REQUESTS.values():
            for challenge, wanted in requests:
                names += [after_expression(challenge, step) for step in wanted]
                names.append(f'{challenge}_IsCompleted_Exp')
        check_expressions(self.read(GAMEDATA), names)

    def test_flags_exist_in_the_game_data(self):
        from oot_rando.patching.soul_adapter import GAMEDATA, murmur3
        data = Byml(self.read(GAMEDATA)).root['Data']
        bools = {e['Hash'] for e in data['Bool']}
        exps = {e['Hash'] for e in data['BoolExp']}
        stone_flags = tuple(s.STONE_FLAG_PREFIX + stone for stone in s.STONE_SETS['all'])
        for name in (s.DARUNIA_GIFT_PLAYED, s.TALON_AWAKE, s.SECOND_MALON, s.BRIDGE_CLOSED, s.CLOCK_FLAG,
                     s.LIGHT_ARROWS_PLAYED, s.PRELUDE_MEDAL) + stone_flags + s.LIGHT_ARROWS_MEDALS:
            self.assertIn(murmur3(name), bools, name)
        for name in (s.AFTER_SARIA_PLAY, s.SHEIK_PRESENCE, s.DOOR_STARTED, s.DOOR_BEFORE_ESCAPE,
                     s.FIRE_QUEST_STARTED, s.DOOR_PAST_SREP, s.PRELUDE_LATER_STEP):
            self.assertIn(murmur3(name), exps, name)
        for name in (s.DOOR_OPENED, s.CHILDHOOD, s.BRIDGE_PLAYED) + s.BRIDGE_MEDALS:
            self.assertIn(murmur3(name), bools, name)
        for name in (s.WATER_GATE_STEP, s.DOOR_SONG_STEP, s.DOOR_COMPLETE_ONLY_AFTER, s.BRIDGE_VANILLA,
                     s.GANON_PAST_REVELATION):
            self.assertIn(murmur3(name), exps, name)

    # --- Scenes no longer required (21/11) ------------------------------------------
    def module(self, path):
        return self.nup.read(self.nup.latest('romfs/' + path))

    def nodes(self, raw):
        import ainb
        return ainb.AINB.from_binary(raw).as_dict()['Nodes']

    def test_scene_steps_match_the_table(self):
        steps = self.steps()
        self.assertEqual(tuple(steps['SageOfWater']), s.SAGE_OF_WATER_STEPS)
        self.assertEqual(tuple(steps['Defeat_Ganon']), s.DEFEAT_GANON_STEPS)

    def test_scene_expressions_in_game_data(self):
        from oot_rando.patching.soul_adapter import GAMEDATA, murmur3
        source = self.read(GAMEDATA)
        self.assertFalse(s.scene_expressions_applied(source))
        raw, report = s.scene_expressions(source)
        self.assertTrue(s.scene_expressions_applied(raw))
        self.assertEqual(report['expressions'], [s.WATER_GATE_OPEN, s.BRIDGE_READY])
        programs = {e['Hash']: [list(v) for v in e['Values']] for e in Byml(raw).root['Data']['BoolExp']}
        # Water: Step05 passed OR NOT childhood. Bridge: vanilla OR (both medals AND NOT shown).
        self.assertEqual(programs[murmur3(s.WATER_GATE_OPEN)],
                         [[10, murmur3(s.WATER_GATE_STEP)], [0, murmur3(s.CHILDHOOD)], [5], [4]])
        self.assertEqual(programs[murmur3(s.BRIDGE_READY)],
                         [[10, murmur3(s.BRIDGE_VANILLA)], [0, murmur3(s.BRIDGE_MEDALS[0])],
                          [0, murmur3(s.BRIDGE_MEDALS[1])], [3], [0, murmur3(s.BRIDGE_PLAYED)], [5], [3], [4]])
        with self.assertRaises(ValueError):    # never applied twice
            s.scene_expressions(raw)

    def test_water_gate_opens_for_adult(self):
        from test_world_openings import unflagged_links
        raw, _ = s.water_gate_for_adult(self.module(s.WATER_GATE_MODULE))
        nodes = self.nodes(raw)
        self.assertEqual(nodes[3]['Name'], 'HoldGameDataGetBoolExpSimple')
        self.assertEqual(nodes[3]['Parameters']['Inputs']['String'][0]['Default Value'], s.WATER_GATE_OPEN)
        # The gate's OR and the "scene played" setter still read it.
        self.assertEqual(sorted(s._links_to(nodes, 3)), [(2, 'BoolMulti', 0), (16, 'IsDrive', 0)])
        self.assertEqual(unflagged_links(nodes), [])
        with self.assertRaises(ValueError):
            s.water_gate_for_adult(raw)

    def test_bombchu_shop_ignores_the_fire_stone_quest(self):
        from test_world_openings import unflagged_links
        raw, _ = s.bombchu_shop_open_from_start(self.module(s.BOMBCHU_SHOP_MODULE))
        nodes = self.nodes(raw)
        door = {(n['Node Index'], n['Output Index']) for n in nodes[3]['Parameters']['Inputs']['Bool']
                if 'Node Index' in n and n['Name'] in ('EnableDo', 'EnableOpen')}
        self.assertEqual(door, {(4, 1), (0, 1)})
        for node, time in ((0, (2, 1)), (4, (5, 1))):
            sources = [(x['Node Index'], x['Output Index']) for x in nodes[node]['Parameters']['Inputs']['Bool'][0]['Sources']]
            self.assertEqual(sources, [time, time])
        self.assertEqual(s._links_to(nodes, 1), [])
        self.assertEqual(unflagged_links(nodes), [])
        with self.assertRaises(ValueError):
            s.bombchu_shop_open_from_start(raw)

    def test_bombchu_shop_vendor_music_and_closed_sign_before_dodongo(self):
        import copy
        for path, targets in s.BOMBCHU_SHOP_ACTORS.items():
            source = self.read(path)
            original = Byml(source).root
            edits, report = s.bombchu_shop_actor_edits(original, path)
            patched = Byml(patch_strings(source, edits)).root
            expected = copy.deepcopy(original)
            self.assertEqual(len(report['actors']), len(targets))
            for index, (ident, gyaml, negated) in zip(report['actors'], targets):
                actor = patched['Actors'][index]
                self.assertEqual((actor['Hash'], actor['Gyaml']), (ident, gyaml))
                expected['Actors'][index]['Presence']['FlagName'] = s.CHILDHOOD
                # Child Link, before and after Dodongo, sees the vendor/music
                # but never the closed sign. Adult map and day/night door stay separate.
                for completed in (False, True):
                    values = {s.BOMBCHU_SHOP_QUEST: completed, s.CHILDHOOD: True}
                    presence = actor['Presence']
                    visible = values[presence['FlagName']] != presence['IsNegation']
                    self.assertEqual(visible, not negated, (path, gyaml, completed))
            self.assertEqual(patched, expected)  # stock, links, all other actors unchanged
            with self.assertRaises(ValueError):
                s.bombchu_shop_actor_edits(patched, path)
            missing = copy.deepcopy(original)
            missing['Actors'].pop(report['actors'][0])
            with self.assertRaises(ValueError):
                s.bombchu_shop_actor_edits(missing, path)

    def test_serenade_never_moves_the_water_quest_back(self):
        source = self.read(s.SAGE_OF_WATER_FLOW)
        raw, report = s.serenade_keeps_water_temple(source)
        self.assertEqual(sorted((e, step) for e, step, _ in report['guarded']),
                         [('Event280', 'Step05'), ('Event282', 'Step04'), ('Event39', 'Step05')])
        events = self.chart(raw)
        for name in ('Event280', 'Event282'):
            guard = next(e for e in events.values() if e.name.startswith('RandoWaterForward_')
                         and getattr(e.data.cases.get(1), 'v', None) is events[name])
            self.assertEqual(guard.data.params.data, {'GameDataName': s.WATER_GATE_STEP})
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.serenade_keeps_water_temple(raw)

    def test_door_reads_its_saved_flag(self):
        from test_world_openings import unflagged_links
        raw, _ = s.door_opens_on_saved_flag(self.module(s.DOOR_MODULE))
        nodes = self.nodes(raw)
        gate = nodes[5]
        self.assertEqual([(x['Node Index'], x['Output Index']) for x in gate['Parameters']['Inputs']['Bool'][0]['Sources']],
                         [(4, 1), (8, 0), (8, 2), (6, 0)])
        self.assertEqual(gate['Queries'], [4, 8, 8, 6])
        self.assertTrue(nodes[6]['Parameters']['Outputs']['Bool'][0]['Is Output'])
        self.assertEqual(unflagged_links(nodes), [])
        with self.assertRaises(ValueError):
            s.door_opens_on_saved_flag(raw)

    def test_song_opens_the_door_before_the_escape(self):
        # 21/11: the song was refused while DoorOfTime was not past Step04 (Event60).
        source = self.read(s.DOOR_FLOW)
        for current in (source, s.zelda_escape_door_flow(source)[0]):
            raw, report = s.door_song_before_escape(current)
            events = self.chart(raw)
            self.assertEqual(events['Event60'].data.cases[1].v.name, 'Event69')   # any step: door check
            # Step06 (Event57 and the new one) only past Step04; Complete only past Step05.
            guards = {e.name: e for e in events.values() if e.name.startswith(s.DOOR_SONG_PREFIX)}
            self.assertEqual(len(guards), 2)
            for guard in guards.values():
                self.assertEqual(guard.data.params.data, {'GameDataName': s.DOOR_SONG_STEP})
                self.assertIn(guard.data.cases[0].v.name, ('Event57', 'RandoDoorOpenedStep06'))
            complete = [e for e in events.values() if e.name.startswith(s.DOOR_COMPLETE_PREFIX)]
            self.assertEqual(len(complete), 1)
            self.assertEqual(complete[0].data.params.data, {'GameDataName': s.DOOR_COMPLETE_ONLY_AFTER})
            self.assertEqual(complete[0].data.cases[0].v.name, 'Event93')
            # Step05 (escape) with the door already opened: Step06 at once.
            check = events['Event14'].data.nxt.v
            self.assertEqual((check.name, check.data.params.data), ('RandoDoorOpenedBefore',
                                                                     {'GameDataName': s.DOOR_OPENED, 'Index': -1}))
            self.assertTrue(check.data.cases[0].v.name.startswith(s.DOOR_SONG_PREFIX))
            self.assertEqual(check.data.cases[1].v.name, 'Event171')
            self.assertEqual(events['RandoDoorOpenedStep06'].data.params.data, events['Event57'].data.params.data)
            self.check_kept(current, raw)
            with self.assertRaises(ValueError):
                s.door_song_before_escape(raw)

    def test_bridge_on_two_medallions(self):
        from test_world_openings import unflagged_links
        raw, _ = s.bridge_on_medallions(self.module(s.BRIDGE_MODULE))
        nodes = self.nodes(raw)
        self.assertEqual(nodes[4]['Parameters']['Inputs']['String'][0]['Default Value'], s.BRIDGE_READY)
        # Still ANDed with "not past Step01" (node 6 = NOT node 3).
        self.assertEqual(nodes[3]['Parameters']['Inputs']['String'][0]['Default Value'], s.GANON_PAST_REVELATION)
        self.assertEqual(unflagged_links(nodes), [])
        with self.assertRaises(ValueError):
            s.bridge_on_medallions(raw)

    def test_revelation_never_moves_ganon_quest_back(self):
        source = s.prelude_keeps_later_sage_progress(self.read(s.ALL_SAGE_FLOW))[0]
        raw, report = s.revelation_keeps_ganon_quest(source)
        self.assertEqual([(e, step) for e, step, _ in report['guarded']], [('Event11', 'Step01')])
        events = self.chart(raw)
        guard = events['RandoGanonForward_0'].data
        self.assertEqual(guard.params.data, {'GameDataName': s.GANON_PAST_REVELATION})
        self.assertEqual(guard.cases[1].v.name, 'Event11')
        self.check_kept(source, raw)

    def test_scene_modules_listed_once(self):
        paths = [path for path, _, _ in s.scene_module_fixes()]
        self.assertEqual(len(paths), len(set(paths)))
        for path, key, fix in s.scene_module_fixes():
            with self.subTest(key=key):
                fix(self.module(path))


if __name__ == '__main__':
    unittest.main()
