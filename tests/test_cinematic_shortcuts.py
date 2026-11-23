"""Behavioral contracts of the optional scene adapters, using the player's assets.

These graph assertions cannot establish engine animation or fade behavior.
"""
import _src_path  # noqa: F401
import os
import unittest

from evfl.event import SubFlowEvent, SubFlowSwitchEvent
from oot_rando.logic import rando_options
from oot_rando.patching import cinematic_comfort as comfort, story_shortcuts as shortcuts
from oot_rando.patching.cinematic_tools import path
from oot_rando.patching.event_patch import _flow, _snapshot, add_collection_markers, add_start_values
from oot_rando.patching.song_lessons import _reach, _params, _action


def reached(raw, entry):
    chart = _flow(raw).flowchart
    start = next(e.main_event.v for e in chart.entry_points if e.name == entry)
    return _reach(chart, [start])


def gets(events):
    return [e for e in events if isinstance(e.data, SubFlowEvent) and
            e.data.res_flowchart_name == 'Dm_SY_GetInEvent']


class SettingsTests(unittest.TestCase):
    def test_new_options_are_opt_in_and_do_not_change_old_settings(self):
        from oot_rando.randomizer.randomizer_core import Settings
        from oot_rando.gui.randomizer_gui import SETTING_GROUPS
        options = rando_options.defaults()
        recorded = Settings('same', full=options, randomize_chests=False).to_dict()['full']
        gui = {name for _, _, names in SETTING_GROUPS for name in names}
        for name in shortcuts.OPTIONS:
            self.assertIs(options[name], False)
            self.assertNotIn(name, recorded)
            self.assertIn(name, gui)
            self.assertTrue(rando_options.BY_NAME[name].supported(True))
        self.assertFalse(shortcuts.enabled(options))

    def test_start_flags_only_suppress_presentations(self):
        self.assertEqual(comfort.start_values({}), {})
        pickups = comfort.start_values({'skip_first_pickup_text': True})
        self.assertEqual(len(pickups), 16)
        self.assertTrue(all(n.startswith('HavePlayedGetEvent.') for n in pickups))
        self.assertNotIn('HavePlayedGetEvent.Obj_Heart_Piece', pickups)
        self.assertNotIn('HavePlayedGetEvent.Obj_Rupee_Gold', pickups)
        guides = comfort.start_values({'skip_tutorials': True})
        self.assertEqual(sum(k.startswith('ActionGuide_IsEnd.') for k in guides), 53)
        self.assertFalse(any(k.startswith('DungeonInfo.') for k in guides))


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class GameFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.d = dictionaries(cls.nup)
        cls.members = effective_members(cls.nup)
        cls.read = staticmethod(lambda p: decompress(cls.nup.read(cls.members[p]), cls.d) if p in cls.members else None)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def test_every_start_value_exists_with_the_expected_game_type(self):
        from oot_rando.game.tracking_metadata import GAMEDATA
        from oot_rando.patching.key_adapter import check_start_values
        check_start_values(self.read(GAMEDATA), comfort.start_values(
            {'skip_tutorials': True, 'skip_first_pickup_text': True}))

    def test_tutorial_body_disappears_but_all_three_gameplay_hooks_survive(self):
        from oot_rando.patching.progressive import add_converter, token_actor
        from oot_rando.patching.key_adapter import add_key_hook, key_records
        from oot_rando.patching.story_fixes import zelda_escape_on_item_get
        from oot_rando.patching.qol_patches import ocarina_guide_on_get
        raw = ocarina_guide_on_get(self.read(path('ActionGuide')))[0]
        raw = add_key_hook(raw, key_records(['Small Key Ring (Forest Temple)']))[0]
        raw = add_converter(raw, [token_actor('Progressive Hookshot', 1)])[0]
        raw = zelda_escape_on_item_get(raw, ('Item_Stone_Forest', 'Item_Stone_Fire', 'Item_Stone_Water'))[0]
        result, _ = comfort.tutorials(raw)
        live = reached(result, 'ActionGuide')
        names = {e.name for e in live}
        self.assertTrue(any(n.startswith('RandoDoorStones') for n in names))
        self.assertTrue(any(n.startswith('RandoKey') for n in names))
        self.assertTrue(any(n.startswith('RandoProg') for n in names))
        self.assertFalse(any('OpenActionGuide' in (_action(e) or ('', ''))[1] for e in live))
        self.assertFalse(any(isinstance(e.data, SubFlowEvent) and e.data.res_flowchart_name == 'Dm_SY_Ocarina' for e in live))

    def test_opening_skips_both_movies_without_losing_seed_or_inventory_initialization(self):
        raw = add_collection_markers(self.read(path('OpeningEvent')), {'Event3': 'RandoSeed.test'})[0]
        raw = add_start_values(raw, 'RandoCollected_Event3', {'IsGet.Item_Dungeon_Map': True})
        result, _ = comfort.opening(raw, {'skip_opening': True, 'skip_first_pickup_text': True})
        live = reached(result, 'Opening_LoadingKokiriForest')
        self.assertIn('RandoCollected_Event3', {e.name for e in live})
        self.assertIn('RandoStartValue_IsGet.Item_Dungeon_Map', {e.name for e in live})
        for entry in ('Opening_LoadingKokiriForest', 'Opening_Introduction'):
            self.assertFalse(any(_params(e).get('EventName') in ('Dm_Kokiri_0000', 'Dm_Kokiri_0030')
                                 and _action(e) == ('EventSystemActor', 'EventTransition') for e in reached(result, entry)))

    def test_new_ocarina_grants_display_pickups_then_add_and_equip_the_actual_item(self):
        result, report = shortcuts.extra_song(self.read(path('DoorOfTime')), 'DoorOfTime', self.read, self.read)
        live = reached(result, 'DoorOfTime_GetOcarinaOfTime')
        self.assertEqual(len(gets(live)), 2)
        shown = {_params(e)['ActorName'] for e in gets(live)}
        self.assertIn('Obj_Rando_Item_Ocarina_Time', shown)
        self.assertIn('Obj_Rando_Item_Melody_TimeSong', shown)
        self.assertTrue(any(_action(e) == ('PouchSystemActor', 'EventTriggerAddOrRemovePouchContent')
                            and _params(e).get('Actor') == 'Item_Ocarina_Time' for e in live))
        self.assertTrue(any(_params(e).get('GameDataName') == 'PlayerStatus.EquipOcarina' for e in live))
        self.assertTrue(any(_params(e).get('StepName') == 'Step05' for e in live))
        self.assertIn('time_ocarina', report)

    def test_time_scene_retains_two_independent_collection_markers(self):
        scene = add_collection_markers(self.read(path('Dm_MelodyGet_Time')),
                                       {'Event70': 'RandoCheck.ocarina', 'Event4': 'RandoCheck.song'})[0]
        current = lambda p: scene if p == path('Dm_MelodyGet_Time') else self.read(p)
        result, _ = shortcuts.extra_song(self.read(path('DoorOfTime')), 'DoorOfTime', self.read, current)
        live = reached(result, 'DoorOfTime_GetOcarinaOfTime')
        self.assertEqual({n for e in live if (n := _params(e).get('GameDataName', '')).startswith('RandoCheck.')},
                         {'RandoCheck.ocarina', 'RandoCheck.song'})

    def test_requiem_retains_the_reward_and_sheik_meeting_without_any_lesson(self):
        raw = self.read(path('Dm_MelodyGet_Spilit'))
        result, _ = shortcuts.extra_song(raw, 'Dm_MelodyGet_Spilit', self.read, self.read)
        live = reached(result, 'EntryPoint0')
        self.assertEqual(len(gets(live)), 1)
        calls = [(e.data.res_flowchart_name, e.data.entry_point_name) for e in live if isinstance(e.data, SubFlowEvent)]
        self.assertIn(('AllSage', 'MeetSheik_And_Gone'), calls)
        self.assertFalse(any(flow == 'Dm_SY_Ocarina' for flow, _ in calls))
        self.assertFalse(any((_action(e) or ('', ''))[1].startswith('EventTalk') for e in live))

    def test_first_draw_keeps_the_master_sword_and_rauru_checks_and_native_era_change(self):
        raw = self.read(path('DoorOfTime'))
        # A non-vanilla placed reward and its independent marker.
        scene = self.read(path('Dm_SageRoom_0005'))
        from oot_rando.patching.event_patch import patch_event_params
        scene = patch_event_params(scene, [('Event48', 'ActorName', 'Item_Medal_Light', 'Item_Hookshot')])
        scene = add_collection_markers(scene, {'Event48': 'RandoCheck.rauru'})[0]
        current = lambda p: scene if p == path('Dm_SageRoom_0005') else self.read(p)
        result, _ = shortcuts.story(raw, 'DoorOfTime', self.read, current)
        chart = _flow(result).flowchart
        root = next(e.main_event.v for e in chart.entry_points if e.name == 'DoorOfTime_Draw')
        live = _reach(chart, [root.data.cases[1].v])
        self.assertTrue(any(_params(e).get('ActorName') == 'Item_Hookshot' for e in gets(live)))
        self.assertTrue(any(_params(e).get('Actor') == 'Weapon_Sword_Master' for e in live))
        self.assertTrue(any(_params(e).get('GameDataName') == 'RandoCheck.rauru' for e in live))
        self.assertTrue(any(_params(e).get('EventName') == 'Market_Child_Field_ChildToAdult' for e in live))
        self.assertFalse(any(_params(e).get('NextBanc') == 'SageRoom' for e in live))
        self.assertTrue(any(_action(e) == ('Player_Event', 'EventTriggerHealLifeMax') for e in live))
        self.assertTrue(any(_action(e) == ('Player_Event', 'EventTriggerPlayerHealMPMax') for e in live))

    def test_escape_keeps_the_exact_step_required_by_the_moat_pickup_trigger(self):
        import ainb
        resource = 'Logic/HyruleField_Child_Prefab_91f9.logic.module.ainb'
        module = ainb.AINB.from_binary(self.nup.read(self.members[resource])).as_dict()
        gate = next(n for n in module['Nodes'] if n['Name'] == 'HoldChallengeCurrentStepCheckOrder')
        strings = {p['Name']: p['Default Value'] for p in gate['Parameters']['Inputs']['String']}
        self.assertEqual(strings['ChallengeStepName'], 'Step04')
        outputs = {p['Name']: p['Is Output'] for p in gate['Parameters']['Outputs']['Bool']}
        self.assertTrue(outputs['IsEqual'])
        result, _ = shortcuts.story(self.read(path('DoorOfTime')), 'DoorOfTime', self.read, self.read)
        steps = [_params(e)['StepName'] for e in reached(result, 'DoorOfTime_Escape')
                 if _action(e) == ('ChallengeSystemActor', 'EventExecuteProgressChallengeStep')]
        self.assertEqual(steps, ['Step04'])

    def test_all_dungeon_rewards_are_after_first_clear_warp_acceptance_and_not_on_repeat(self):
        raw = self.read(path('Dm_SY_BancChange_EscapeDungeon'))
        result, report = shortcuts.endings(raw, self.read, self.read)
        self.assertEqual(set(report), {location for location, *_ in shortcuts.REWARDS})
        chart = _flow(result).flowchart
        live_all = _reach(chart, [e.main_event.v for e in chart.entry_points])
        for scene in ('Dm_LakeHrl_0020', 'Dm_DeathMtTrail_0027', 'Dm_DeathMtCrater_0010',
                      'Dm_Graveyard_0030', 'Dm_DesertColossus_0040'):
            self.assertFalse(any(_action(e) == ('EventSystemActor', 'EventTransition')
                                 and _params(e).get('EventName') == scene for e in live_all), scene)
        for location, _, _, entry in shortcuts.REWARDS:
            with self.subTest(location=location):
                node = next(e.main_event.v for e in chart.entry_points if e.name == entry)
                while not hasattr(node.data, 'cases'):
                    node = node.data.nxt.v
                first = _reach(chart, [node.data.cases[1].v])
                repeat = _reach(chart, [node.data.cases[0].v])
                self.assertTrue(gets(first))
                self.assertFalse(gets(repeat))
                # Up to the accepted choice there is no standard get.
                pending = [node.data.cases[1].v]; seen = set(); menu = None
                while pending:
                    e = pending.pop()
                    if e.name in seen: continue
                    seen.add(e.name)
                    if isinstance(e.data, SubFlowSwitchEvent): menu = e; continue
                    self.assertNotIn(e, gets(first))
                    if getattr(e.data, 'nxt', None) is not None and e.data.nxt.v:
                        pending.append(e.data.nxt.v)
                self.assertIsNotNone(menu)
                self.assertEqual(len(menu.data.cases), 1)

    def test_fairy_shortcuts_keep_native_grants_payment_prerequisites_and_healing(self):
        for name in shortcuts.FAIRIES:
            with self.subTest(fairy=name):
                raw = self.read(path(name))
                result, _ = shortcuts.fairy(raw, name, self.read)
                before, after = _snapshot(_flow(raw)), _snapshot(_flow(result))
                for event, params in before.items():
                    self.assertEqual(after[event], params)
                live = reached(result, 'EntryPoint0')
                calls = [(e.data.res_flowchart_name, e.data.entry_point_name) for e in live if isinstance(e.data, SubFlowEvent)]
                self.assertTrue(any(entry == 'Pay' for _, entry in calls))
                self.assertIn(('', 'C15-01'), calls)
                self.assertIn(('TriForcePoint', 'Recover'), calls)
                self.assertNotIn(('', name), calls)
                self.assertNotIn(('', 'GreatFairy_Appear'), calls)

    def test_shortcuts_have_complete_call_indices(self):
        raw, _ = shortcuts.extra_song(self.read(path('Dm_MelodyGet_Spilit')), 'Dm_MelodyGet_Spilit', self.read, self.read)
        chart = _flow(raw).flowchart
        for entry in chart.entry_points:
            live = {e.name for e in _reach(chart, [entry.main_event.v], descend=False)}
            required = {i for i, e in enumerate(chart.events) if e.name in live and isinstance(e.data, (SubFlowEvent, SubFlowSwitchEvent))}
            self.assertEqual(set(entry._sub_flow_event_indices), required)

    def test_requiem_event_uses_normal_player_event_style(self):
        from oot_rando.formats import byml_codec
        table = self.read('RSDB/EventSetting.Product.111.rstbl.byml.zs')
        raw, targets = shortcuts.event_styles(table, {'skip_song_lessons': True})
        rows = {r['__RowId']: r for r in byml_codec.load(raw)['root']}
        self.assertEqual(targets, ['Dm_MelodyGet_Spilit'])
        self.assertEqual(rows['Dm_MelodyGet_Spilit']['EventSettingComponentList'],
                         rows['KokiriForest_ArriveLostWood']['EventSettingComponentList'])

    def test_burning_village_moves_nocturne_before_the_load_and_preserves_both_destinations(self):
        from oot_rando.patching import song_lessons
        scene = self.read(path('Dm_MelodyGet_Shadow'))
        raw, _ = song_lessons.give_in_trigger(self.read(path('Dm_SY_BancChangeArrive')), scene,
                    song_lessons.BY_AP['Sheik in Kakariko'], 'Item_Melody_ShadowNocturne', 'RandoCheck.nocturne')
        # The placed scene carries the same check marker that the trigger carries.
        scene = add_collection_markers(scene, {'Event21': 'RandoCheck.nocturne'})[0]
        current = lambda p: scene if p == path('Dm_MelodyGet_Shadow') else self.read(p)
        result, _ = shortcuts.story(raw, 'Dm_SY_BancChangeArrive', self.read, current)
        before_load = reached(result, 'KakarikoVillage_Arrive')
        after_load = reached(result, 'KakarikoVillage_MelodyGet_Shadow')
        self.assertEqual(len(gets(before_load)), 1)
        self.assertEqual(len(gets(after_load)), 0)
        self.assertTrue(any(_params(e).get('GameDataName') == 'RandoCheck.nocturne' for e in before_load))
        events = {e.name: e for e in _flow(result).flowchart.events}
        self.assertEqual(_params(events['Event329'])['NextBanc'], 'KakarikoVillage_Adult')
        self.assertEqual(_params(events['Event379'])['NextBanc'], 'KakarikoVillage_Adult_Alternative')
        self.assertTrue(any(_action(e) == ('EventWorldManagerController', 'EventTrigger_SetTime') for e in before_load))

    def test_held_song_and_ocarina_forms_have_common_animation_and_correct_pouch_identity(self):
        from oot_rando.formats.inspect_resources import sarc
        from oot_rando.formats import byml_codec as codec
        from oot_rando.game.item_forms import build_pack, resolve_components, _pack_path
        from oot_rando.patching.cinematic_tools import held_actor
        self.assertEqual(held_actor('Item_Prog_Ocarina_1'), 'Obj_Rando_Item_Prog_Ocarina_1')
        for actor in ('Item_Ocarina_Fairy', 'Item_Ocarina_Time', 'Item_Melody_EponaSong'):
            form = held_actor(actor)
            pack, _ = build_pack(form, lambda a: sarc(self.read('Pack/Actor/' + a + '.pack.zs')), codec)
            files = sarc(pack)
            components = resolve_components(files, form, codec)
            animation = codec.load(files[_pack_path(components['AnimationRef'])])['root']
            self.assertIn({'ModelProjectName': 'Item_Common_Animation'}, animation['AnimationResources'])
            self.assertIn(b'Rotate_GetDemo', self.read(_pack_path(components['ASRef']) + '.zs'))
            pouch = codec.load(files[_pack_path(components['PouchContentRef'])])['root']
            self.assertEqual(pouch['PouchActor'], f'Work/Actor/{actor}.engine__actor__ActorParam.gyml')

    def test_darunia_keeps_song_success_check_but_not_the_dance_or_bracelet_ceremony(self):
        raw = self.read(path('Get_StoneOfFire'))
        result, _ = shortcuts.story(raw, 'Get_StoneOfFire', self.read, self.read)
        events = {e.name: e for e in _flow(result).flowchart.events}
        live = _reach(_flow(result).flowchart, [events['Event35'].data.cases[0].v])
        self.assertEqual(len(gets(live)), 1)
        self.assertFalse(any(_params(e).get('EventName') in ('Dm_Goron_0025', 'Dm_Goron_0030')
                             and _action(e) == ('EventSystemActor', 'EventTransition') for e in live))
        self.assertEqual(events['Event35'].data.actor_query.v.v, 'EventQueryIsRecommendedMelody')
        self.assertTrue(any(_params(e).get('StepName') == 'DodongoCavernOpne' for e in live))

    def test_rutos_earlier_display_cannot_collect_the_relocated_boss_check(self):
        raw = add_collection_markers(self.read(path('Dm_InsideJabu_Jabu_0030')),
                                     {'Event181': 'RandoCheck.barinade'})[0]
        before = reached(raw, 'EntryPoint0')
        self.assertIn('RandoCollected_Event181', {e.name for e in before})
        result, _ = shortcuts.retire_ruto_display_marker(raw, 'RandoCheck.barinade')
        live = reached(result, 'EntryPoint0')
        self.assertNotIn('RandoCollected_Event181', {e.name for e in live})
        self.assertIn('Event181', {e.name for e in live})
