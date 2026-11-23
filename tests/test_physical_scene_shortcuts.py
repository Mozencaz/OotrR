"""Physical story shortcuts: accounting, branching and interactive services."""
import _src_path  # noqa: F401
import os
import unittest

from evfl.event import SubFlowEvent, SubFlowSwitchEvent
from oot_rando.patching import physical_scene_shortcuts as physical
from oot_rando.patching.cinematic_tools import path
from oot_rando.patching.event_patch import _flow, _snapshot
from oot_rando.patching.song_lessons import _action, _params, _reach


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class PhysicalScenes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(os.environ['OOT_NUP'])
        members, d = effective_members(cls.nup), dictionaries(cls.nup)
        cls.read = staticmethod(lambda p: decompress(cls.nup.read(members[p]), d) if p in members else None)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def patch(self, name, current=None):
        current = current or self.read
        result, report = physical.shorten(current(path(name)), name, self.read, current)
        return _flow(result).flowchart, report

    def live(self, chart, entry):
        ep = next(e for e in chart.entry_points if e.name == entry)
        return _reach(chart, [ep.main_event.v])

    def assert_short(self, live):
        self.assertFalse(any('EventTalk' in (_action(e) or ('', ''))[1] for e in live))
        self.assertFalse(any((_action(e) or ('', ''))[0].startswith('EventCamera') and
                             (_action(e) or ('', ''))[1] != 'EventTriggerSendReserveCameraResetMessageToPlayerCamera'
                             for e in live))
        self.assertFalse(any((_action(e) or ('', ''))[1] == 'EventTransition' for e in live))
        self.assertFalse(any((_action(e) or ('', ''))[1] == 'EventPlayAS' and _params(e).get('IsWaitEnd') for e in live))

    def test_nine_independent_releases_and_repeat_guard(self):
        chart, _ = self.patch('Dm_FireTemple_0020')
        for i, npc in enumerate(('005', '001', '003', '007', '004', '002', '008', '009', '010')):
            with self.subTest(prisoner=npc):
                live = self.live(chart, f'EntryPoint{i}')
                self.assert_short(live)
                writes = [e for e in live if _action(e) == ('GameDataActor', 'EventTriggerSetGameDataBool')]
                self.assertEqual([_params(e)['GameDataName'] for e in writes],
                                 [f'Npc_Goron_{npc}_Adult_FireTemple_Delete'])
                debits = [e for e in live if (_action(e) or ('', ''))[1] == 'EventTriggerAddOrSubGameDataInt']
                self.assertEqual([_params(e) for e in debits],
                                 [{'GameDataName': 'NumberOfCoughtGoron', 'Value': -1, 'Index': -1}])
                root = next(e for e in chart.entry_points if e.name == f'EntryPoint{i}').main_event.v
                self.assertEqual(_action(root.data.cases[0].v), ('UISystemActor', 'EventEventFadeIn'))
                calls = [e.data.entry_point_name for e in live if isinstance(e.data, SubFlowEvent)]
                self.assertEqual(calls, ['SageOfFire_MeetBoss'] if i == 8 else [])
                hide = next(e for e in live if (_action(e) or ('', ''))[1] == 'EventGoOffstageForUser')
                self.assertEqual(hide.data.nxt.v.name, writes[0].name)

    def test_carpenter_completion_keeps_per_cell_accounting_and_argument(self):
        chart, _ = self.patch('Dm_Gerudo_0020')
        for i, npc in enumerate(('013', '014', '015', '016')):
            live = self.live(chart, f'EntryPoint{i}')
            self.assert_short(live)
            self.assertTrue(any((_action(e) or ('', ''))[0] == f'Npc_Hylia_{npc}_Adult[GerudoFortress]'
                                for e in live))
            completions = [e for e in live if isinstance(e.data, SubFlowEvent)
                           and e.data.res_flowchart_name == 'Common_Dungeon_OpenDoorChainLockMove']
            self.assertEqual(len(completions), 1)
            flags = next(e for e in live if isinstance(e.data, SubFlowEvent)
                         and e.name.startswith('RandoCinema_CarpenterFlags'))
            self.assertEqual(_params(flags), {'GameDataName': f'GerudoFortress_WarpPoint0{i+1}_ClearEvent'})
            self.assertEqual(flags.data.entry_point_name, 'Npc_Gerudo_001_CreateCheck')
            self.assertEqual(_action(flags.data.nxt.v)[1], 'EventGoOffstageForUser')
            self.assertEqual(flags.data.nxt.v.data.nxt.v.name, completions[0].name)
            self.assertEqual(_action(completions[0].data.nxt.v), ('UISystemActor', 'EventEventFadeIn'))
        before = _flow(self.read(path('SageOfSpirit_RescueCarpenter'))).flowchart
        after, _ = self.patch('SageOfSpirit_RescueCarpenter')
        for key in ('Event184', 'Event191', 'Event280', 'Event145'):
            self.assertEqual(_params(next(e for e in before.events if e.name == key)),
                             _params(next(e for e in after.events if e.name == key)))
        advice = self.live(after, 'NaviEvent_CarpenterNumber')
        self.assertFalse(any(isinstance(e.data, SubFlowEvent) and e.data.res_flowchart_name == 'NaviEventCommon'
                             for e in advice))

    def test_shuffled_membership_card_is_given_and_marked_once(self):
        from oot_rando.patching.event_patch import patch_event_params, add_collection_markers
        scene = patch_event_params(self.read(path('Dm_Gerudo_0025')),
                                   [('Event294', 'ActorName', 'Item_Token_Gerudo', 'Item_Hookshot')])
        scene = add_collection_markers(scene, {'Event294': 'RandoCheck.card'})[0]
        current = lambda p: scene if p == path('Dm_Gerudo_0025') else self.read(p)
        chart, _ = self.patch('SageOfSpirit', current)
        live = self.live(chart, 'Meet_FourCarpenter_ClearEvent')
        gets = [e for e in live if isinstance(e.data, SubFlowEvent) and e.data.res_flowchart_name == 'Dm_SY_GetInEvent']
        self.assertEqual([_params(e)['ActorName'] for e in gets], ['Item_Hookshot'])
        self.assertEqual(sum(_params(e).get('GameDataName') == 'RandoCheck.card' for e in live), 1)
        self.assertTrue(any(_params(e).get('StepName') == 'Step02' for e in live))
        self.assertFalse(any(_params(e).get('EventName') == 'Dm_Gerudo_0025' for e in live))

    def test_nabooru_retains_final_anchor_and_guarded_completion(self):
        chart, _ = self.patch('SageOfSpirit')
        live = self.live(chart, 'SageOfSpirit_MeetNabooru')
        self.assert_short(live)
        warp = next(e for e in live if (_action(e) or ('', ''))[1] == 'EventAIScheduleWarpToAnchor')
        self.assertEqual(_params(warp)['AnchorType'], 4)
        call = next(e for e in live if isinstance(e.data, SubFlowEvent))
        self.assertEqual(_action(call.data.nxt.v), ('UISystemActor', 'EventEventFadeIn'))
        self.assertTrue(any(_params(e).get('StepName') == 'Step06' for e in live))

    def test_gate_keeps_handover_branch_and_single_letter_debit(self):
        chart, report = self.patch('Npc_Hylia_Soldier_003')
        self.assertEqual(report['letter_gate'], ['Event7'])
        original = _flow(self.read(path('Npc_Hylia_Soldier_003'))).flowchart
        for key in ('Event57', 'Event12'):
            self.assertEqual(_params(next(e for e in original.events if e.name == key)),
                             _params(next(e for e in chart.events if e.name == key)))
        self.assertFalse(any(_params(e).get('EventName') == 'Dm_Kakariko_0010'
                             for e in self.live(chart, 'ShowItem_ZeldaLetter')))
        self.assertEqual(sum(_action(e) == ('PouchSystemActor', 'EventTriggerAddOrRemovePouchContent')
                             for e in chart.events), 1)

    def test_ruto_starts_big_octo_without_collecting_the_boss_reward(self):
        chart, _ = self.patch('Get_StoneOfWater')
        # Inspect the shortcut itself, excluding the caller's later quest routes.
        start = next(e for e in chart.events if e.name.startswith('RandoCinema_FadeOut'))
        # This isolated adapter has one new fade-out (the platform).
        live = _reach(chart, [start])
        self.assert_short(live)
        self.assertTrue(any(_action(e) == ('Enemy_MiddleBoss_BigOcto[MiddleBoss]',
                                         'EventDungeonBossSetConsiderBattlePresentation') for e in live))
        self.assertFalse(any(isinstance(e.data, SubFlowEvent) and e.data.res_flowchart_name in
                             ('GetPouchContent', 'Dm_SY_GetInEvent') for e in live))
        self.assertFalse(any((_action(e) or ('', ''))[1] in ('EventTriggerModelBind', 'EventTriggerModelUnbind') for e in live))
        from oot_rando.formats.inspect_resources import Byml
        actors = Byml(self.read('Banc/InsideJabuJabuBelly/InsideJabuJabuBelly_Static.bcett.byml.zs')).root['Actors']
        lift = next(a for a in actors if a['Gyaml'] == 'Obj_InsideJabu_Jabu_ElevatorLift_A_01')
        final = next(e for e in live if (_action(e) or ('', ''))[0].startswith('Obj_InsideJabu_Jabu_ElevatorLift'))
        self.assertEqual(_params(final)['Position'], lift['Translate'])

    def test_epona_preserves_races_menus_mounts_fees_and_native_counters(self):
        chart, report = self.patch('Get_Epona')
        self.assertEqual([len(report[k]) for k in ('race_staging', 'first_win', 'final_win')], [2, 1, 1])
        before = _flow(self.read(path('Get_Epona')))
        original = _snapshot(before)
        after = {e.name: e for e in chart.events}
        # The caller's fees, race choice/result queries and win accounting are untouched.
        self.assertTrue(all((_params(after[k]) if v is not None else None) == v for k, v in original.items()))
        for i in ('0020', '0030', '0040'):
            self.assertFalse(any(_params(e).get('EventName') == 'Dm_LonLon_' + i
                                 and e.name not in ('Event186', 'Event166', 'Event177', 'Event94') for e in chart.events))
        mounts = [e for e in chart.events if (_action(e) or ('', ''))[1] == 'EventTriggerRequestRideMe'
                  and e.name.startswith('RandoCinema_')]
        self.assertEqual(len(mounts), 3)
        return20 = [e for e in chart.events if _action(e) == ('PouchSystemActor', 'EventTriggerIncreaseRupee')
                    and e.name.startswith('RandoCinema_')]
        self.assertEqual([_params(e)['Value'] for e in return20], [20])

    def test_scarecrows_preserve_interactive_recording_learning_and_choice_cases(self):
        from oot_rando.patching import npc_dialogue_skip as dialogue
        for name in ('Npc_Bonooru', 'Npc_Pierre'):
            chart, _ = self.patch(name)
            before = _flow(self.read(path(name))).flowchart
            def interactive(c):
                return {e.name: (e.data.res_flowchart_name, e.data.entry_point_name, _params(e))
                        for e in c.events if isinstance(e.data, SubFlowEvent) and
                        ('Recording' in e.data.entry_point_name or 'Learning' in e.data.entry_point_name)}
            self.assertEqual(interactive(before), interactive(chart))
            self.assertTrue(interactive(chart))
            for old in before.events:
                if dialogue._is_choice_query(old):
                    new = next(e for e in chart.events if e.name == old.name)
                    self.assertEqual({k: v.v.name for k, v in old.data.cases.items()},
                                     {k: v.v.name for k, v in new.data.cases.items()})
            if name == 'Npc_Bonooru':
                live = self.live(chart, 'PierreApperedFlow')
                self.assert_short(live)
                self.assertFalse(any(_params(e).get('Value') is True and
                                     _params(e).get('GameDataName') == 'SubEvent_GetScarecrow_Pierre_Appear'
                                     for e in live))
                self.assertTrue(any(_params(e).get('StepName') == 'Complete' for e in live))

    def test_all_rewritten_entries_have_exact_direct_preloads(self):
        for name in physical.FLOWS:
            chart, _ = self.patch(name)
            for ep in chart.entry_points:
                self.assertIsNotNone(ep.main_event.v)
                direct = {e.name for e in _reach(chart, [ep.main_event.v], descend=False)}
                calls = {i for i, e in enumerate(chart.events) if e.name in direct
                         and isinstance(e.data, (SubFlowEvent, SubFlowSwitchEvent))}
                self.assertEqual(set(ep._sub_flow_event_indices), calls, (name, ep.name))

    def test_gate_collision_uses_native_instant_ground_controller_and_letter_selector(self):
        import copy
        import ainb
        from oot_rando.patching import world_openings
        modules = (world_openings.KAKARIKO_CLOSED_MODULE, world_openings.KAKARIKO_OPEN_MODULE)
        staged = {}
        for resource, opened in zip(modules, (False, True)):
            # Compose with the always-on letter-selection fix, not vanilla quest gates.
            staged[resource] = world_openings.kakariko_gate_on_letter(
                self.nup.read(self.nup.latest('romfs/' + resource)), opened)[0]
        original = copy.deepcopy(staged)
        physical.apply_world(staged, lambda p: self.fail('Existing module was not reused'))
        for resource in modules:
            before = ainb.AINB.from_binary(original[resource]).as_dict()
            after = ainb.AINB.from_binary(staged[resource]).as_dict()
            for doc in (before, after):
                doc.pop('File Hashes', None)
            ground = world_openings._node(before['Nodes'], 0, 'ActorLogicGroundControlResidentMoveTo')
            world_openings._bool_input(ground, 'ForceWarp')['Default Value'] = True
            self.assertEqual(before['Nodes'], after['Nodes'])
