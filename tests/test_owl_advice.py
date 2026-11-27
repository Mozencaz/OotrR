"""Owl tutorials disappear without skipping quest work or losing the two rides."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.patching import owl_advice as owl
from oot_rando.formats.evfl_tools import event_params_of, links_to, parse_flow


class OwlFlags(unittest.TestCase):
    def test_only_safe_tutorials_are_premarked(self):
        flags = owl.start_values()
        advice = {'HavePlayedEvent.' + event for event in owl.ADVICE_EVENTS}
        self.assertTrue(all(flags[name] is True for name in advice))
        for scene in ('Dm_TimeTemple_0086', 'Dm_HrlField_0080', 'Npc_Dream_FirstTalk',
                      'Dm_DeathMtTrail_0030', 'Dm_LakeHrl_0010'):
            self.assertNotIn('HavePlayedEvent.' + scene, flags)

    def test_first_field_arrival_is_premarked(self):
        # Discord 19/11: the clock waits for Kaepora's first field arrival.
        flags = owl.start_values()
        for scene in ('Dm_HrlField_0000', 'Dm_HrlField_0005', 'Dm_HrlField_0010'):
            self.assertIs(flags['HavePlayedEvent.' + scene], True)
        self.assertIs(flags['HyruleField_ArriveEntrance'], True)
        self.assertEqual(len(flags), len(owl.ADVICE_EVENTS) + 3 + len(owl.FIELD_ARRIVAL_VALUES))

    def test_amiibo_menu_is_a_starting_item(self):
        from oot_rando.randomizer.randomizer_core import STARTING_ITEMS
        self.assertTrue(set(owl.FIELD_ARRIVAL_POUCH) <= set(STARTING_ITEMS))


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class NativeOwls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.d = dictionaries(cls.nup)
        cls.members = effective_members(cls.nup)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        from oot_rando.formats.inspect_resources import decompress
        return decompress(self.nup.read(self.members[path]), self.d)

    @staticmethod
    def chart(raw):
        return parse_flow(raw).flowchart

    def test_all_premarked_flags_are_native_saved_bools(self):
        from oot_rando.formats.inspect_resources import Byml
        from oot_rando.patching.soul_adapter import GAMEDATA, murmur3
        entries = {e['Hash']: e for e in Byml(self.read(GAMEDATA)).root['Data']['Bool']}
        for name in owl.start_values():
            self.assertIn(murmur3(name), entries)
            self.assertGreaterEqual(entries[murmur3(name)]['SaveFileIndex'], 0)

    def test_field_arrival_sequence_is_what_the_start_replaces(self):
        # Goto_HyruleCastle_Kaepora_00: its saved effects are the start values, its
        # pouch gift a starting item, its quest step the escape flow's new request.
        chart = self.chart(self.read(owl.CASTLE_FLOW))
        entry = next(e for e in chart.entry_points if e.name == 'Goto_HyruleCastle_Kaepora_00')
        seen, stack, flags, played, pouch, steps = set(), [entry.main_event.v], {}, set(), [], []
        while stack:
            event = stack.pop()
            if event is None or event.name in seen:
                continue
            seen.add(event.name)
            data = event.data
            action = getattr(getattr(data, 'actor_action', None), 'v', None)
            action = getattr(action, 'v', action)
            params = event_params_of(event) if hasattr(data, 'params') else {}
            if action == 'EventTriggerSetGameDataBool':
                flags[params['GameDataName']] = params['Value']
            elif action == 'EventTransition':
                played.add(params['EventName'])
            elif action == 'EventTriggerAddOrRemovePouchContent':
                pouch.append(params['Actor'])
            elif action == 'EventExecuteProgressChallengeStep':
                steps.append((params['ChallengeName'], params['StepName']))
            if getattr(data, 'nxt', None) is not None:
                stack.append(data.nxt.v)
            stack.extend(case.v for case in (getattr(data, 'cases', None) or {}).values())
            stack.extend(fork.v for fork in (getattr(data, 'forks', None) or []))
            if getattr(data, 'join', None) is not None:
                stack.append(data.join.v)
        self.assertEqual(played, set(owl.FIELD_ARRIVAL_EVENTS))
        flags.pop('HyruleField_ChangeENV')    # the sky palette: False is its default
        self.assertEqual(flags, owl.FIELD_ARRIVAL_VALUES)
        self.assertEqual(tuple(pouch), owl.FIELD_ARRIVAL_POUCH)
        self.assertEqual(steps, [('Goto_HyruleCastle', 'Step02')])

    def test_field_step_follows_the_deku_tree_escape(self):
        from oot_rando.patching.quest_guard import CHALLENGES, challenge_steps
        steps = challenge_steps(self.read(CHALLENGES))
        raw = self.read(owl.ESCAPE_FLOW)
        patched, report = owl.field_step_after_escape(raw, steps)
        events = {e.name: e for e in self.chart(patched).events}
        original = next(e for e in self.chart(raw).events if e.name == owl.ESCAPE_STEP01)
        guard = events[owl.ESCAPE_STEP01].data.nxt.v
        self.assertEqual(event_params_of(guard), {'GameDataName': owl.FIELD_STEP_SKIP})
        request = events[owl.FIELD_STEP]
        self.assertEqual(event_params_of(request), dict(event_params_of(original), StepName='Step02',
                                                IsIgnoreCompletedChallenge=True, IsIgnoreChallengeProgressUI=True))
        resume = original.data.nxt.v.name
        self.assertEqual(request.data.nxt.v.name, resume)
        self.assertEqual({k: v.v.name for k, v in guard.data.cases.items()}, {0: resume, 1: owl.FIELD_STEP})
        self.assertEqual(report['event'], owl.FIELD_STEP)
        with self.assertRaises(ValueError):
            owl.field_step_after_escape(patched, steps)

    def test_first_field_scenes_mark_played_then_run_original_continuations(self):
        raw = self.read(owl.CASTLE_FLOW)
        patched, report = owl.skip_first_field_advice(raw)
        before, after = self.chart(raw), self.chart(patched)
        events = {e.name: e for e in after.events}
        for name, details in report.items():
            self.assertFalse(links_to(after, events[name]))
            seen = events['RandoOwlSeen' + name]
            self.assertEqual(seen.data.actor_action.v.v, 'EventTriggerSetGameDataBool')
            self.assertEqual(seen.data.params.data,
                             {'GameDataName': 'HavePlayedEvent.' + details['scene'], 'Value': True, 'Index': -1})
            self.assertEqual(seen.data.nxt.v.name, details['resume'])
        # The native quest advance and environment reset are still present, unchanged.
        for name in ('Event14', 'Event217'):
            original = next(e for e in before.events if e.name == name)
            self.assertEqual(events[name].data.params.data, original.data.params.data)
            self.assertEqual(events[name].data.nxt.v.name, original.data.nxt.v.name)
        with self.assertRaises(ValueError):
            owl.skip_first_field_advice(patched)

    def test_dream_world_unlocks_without_forced_advice(self):
        patched, _ = owl.skip_dream_advice(self.read(owl.DREAM_INTRO_FLOW))
        chart = self.chart(patched)
        entry = next(e for e in chart.entry_points if e.name == 'EntryPoint0')
        self.assertEqual(entry.main_event.v.data.actor_action.v.v, 'EventTriggerSetGameDataBool')
        self.assertEqual(entry.main_event.v.data.params.data,
                         {'GameDataName': 'DreamWorld_Open', 'Value': True, 'Index': -1})
        wait = entry.main_event.v.data.nxt.v
        self.assertEqual(wait.data.actor_action.v.v, 'EventWaitCloseLoadingFade')
        reset = wait.data.nxt.v
        self.assertEqual(reset.data.actor_action.v.v, 'EventTriggerSendReserveCameraResetMessageToPlayerCamera')
        music = reset.data.nxt.v
        self.assertEqual(music.data.actor_action.v.v, 'EventTriggerSoundStartSceneBgm')
        self.assertIsNone(music.data.nxt.v)
        with self.assertRaises(ValueError):
            owl.skip_dream_advice(patched)

    def test_both_rides_keep_choice_loading_and_flight_without_advice(self):
        for path, fix, yes, resume, no in (
                (owl.DMT_FLOW, owl.short_mountain_ride, 'Event0', 'Event24', 'Event54'),
                (owl.LAKE_FLOW, owl.short_lake_ride, 'Event39', 'Event2', 'Event40')):
            with self.subTest(path=path):
                raw = self.read(path)
                before = self.chart(raw)
                patched, _ = fix(raw)
                chart = self.chart(patched)
                entries = {e.name: e for e in chart.entry_points}
                events = {e.name: e for e in chart.events}
                init = entries['Talk'].main_event.v
                self.assertEqual((init.data.res_flowchart_name, init.data.entry_point_name), ('InitTalk', 'InitTalk'))
                first = init.data.nxt.v
                if path == owl.LAKE_FLOW:
                    self.assertEqual(first.data.actor_action.v.v, 'EventTriggerParticipateEvent')
                    first = first.data.nxt.v
                self.assertEqual(first.name, 'Event13')
                self.assertEqual(first.data.params.data['ChoiceNumber'], 2)
                self.assertIsNone(entries['Near'].main_event.v)
                self.assertEqual(events[yes].data.nxt.v.name, resume)
                self.assertIsNone(events[no].data.nxt.v)
                # Yes/no switch and all original transition/reserve actions survive.
                for event in before.events:
                    action = getattr(event.data, 'actor_action', None)
                    if action and action.v.v in ('EventTransition', 'EventReserveBancChange',
                                                 'EventTriggerBancRequestBeforehandLoad'):
                        self.assertEqual(events[event.name].data.params.data, event.data.params.data)
                switch = events['Event14']
                self.assertEqual(set(switch.data.cases), {0, 1})
                self.assertEqual(switch.data.cases[1].v.name, no)
                with self.assertRaises(ValueError):
                    fix(patched)


if __name__ == '__main__':
    unittest.main()
