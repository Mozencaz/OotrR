"""Physical actions, choices and one-time effects survive silent story lines."""
import _src_path  # noqa: F401
import os
import unittest

from evfl.event import ActionEvent
from oot_rando.patching import special_dialogues as special, npc_dialogue_skip as dialogue
from oot_rando.patching.cinematic_tools import path
from oot_rando.patching.event_patch import _flow, _snapshot
from oot_rando.patching.song_lessons import _action, _params, _reach


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class GameFlows(unittest.TestCase):
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

    def patch(self, name):
        raw = self.read(path(name))
        result, report = special.shorten(raw, name, self.read)
        return _flow(raw).flowchart, _flow(result).flowchart, report

    def test_every_entry_keeps_native_gameplay_actions_and_calls(self):
        presentation = {'EventTalk', 'EventTalkIgnoreSameTalkAS',
                        'EventCloseMessageDialog', 'EventTriggerBecomeSpeaker'}
        total = 0
        for name in special.FLOWS:
            if self.read(path(name)) is None:
                continue
            with self.subTest(flow=name):
                before, after, report = self.patch(name)
                total += len(report['silent_lines'])
                from oot_rando.patching.skip_auto import _roots
                reached = {e.name for e in _reach(after, _roots(after))}
                self.assertFalse(reached & set(report['silent_lines']))
                entries = {e.name: e for e in after.entry_points}
                original = {e.name for e in before.events}
                def gameplay(chart, root):
                    return {e.name for e in _reach(chart, [root]) if e.name in original and
                            (not isinstance(e.data, ActionEvent) or _action(e)[1] not in presentation)}
                for entry in before.entry_points:
                    self.assertEqual(gameplay(before, entry.main_event.v),
                                     gameplay(after, entries[entry.name].main_event.v), entry.name)
                # Existing parameters, including selected bottle and debit counts,
                # only change to close a retained question's message box.
                old = _snapshot(_flow(self.read(path(name))))
                for e in after.events:
                    if e.name in old:
                        params = _params(e) if old[e.name] is not None else None
                        if params is not None and params != old[e.name]:
                            expected = dict(old[e.name], IsCloseDialog=True)
                            self.assertEqual(params, expected)
        self.assertGreater(total, 400)

    def test_gameplay_routing_and_choice_cases_keep_their_order_and_branches(self):
        from oot_rando.patching.skip_auto import _successors
        for name in special.FLOWS:
            if self.read(path(name)) is None:
                continue
            with self.subTest(flow=name):
                before, after, _ = self.patch(name)
                stable = {e.name for e in before.events if not (
                    isinstance(e.data, ActionEvent) and (
                        (dialogue._is_talk(e) and not dialogue._offers_choice(e)) or
                        _action(e)[1] in ('EventCloseMessageDialog', 'EventTriggerBecomeSpeaker')))}
                def endpoint(event):
                    todo, seen, result = [event], set(), set()
                    while todo:
                        e = todo.pop()
                        if e is None:
                            result.add(None)
                        elif e.name in stable:
                            result.add(e.name)
                        elif e.name not in seen:
                            seen.add(e.name)
                            following = _successors(e)
                            todo.extend(following or [None])
                    return result
                def routes(chart):
                    result = {('entry', e.name): endpoint(e.main_event.v) for e in chart.entry_points}
                    for e in chart.events:
                        if e.name not in stable:
                            continue
                        for attr in ('nxt', 'join'):
                            if hasattr(e.data, attr):
                                result[(e.name, attr)] = endpoint(getattr(e.data, attr).v)
                        for key, target in (getattr(e.data, 'cases', None) or {}).items():
                            result[(e.name, 'case', key)] = endpoint(target.v)
                        for i, target in enumerate(getattr(e.data, 'forks', None) or []):
                            result[(e.name, 'fork', i)] = endpoint(target.v)
                    return result
                self.assertEqual(routes(before), routes(after))

    def test_disabled_story_option_does_not_write_special_flows(self):
        from oot_rando.patching.story_shortcuts import apply
        def reject_write(*args):
            self.fail('Disabled story option wrote a resource')
        self.assertEqual(apply({'skip_story_sequences': False}, self.read, self.read, reject_write), {})

    def test_nine_goron_entries_only_release_their_own_prisoner(self):
        _, chart, report = self.patch('Dm_FireTemple_0020')
        prisoners = ('005', '001', '003', '007', '004', '002', '008', '009', '010')
        self.assertEqual(len(report['silent_lines']), 37)
        for i, prisoner in enumerate(prisoners):
            entry = next(e for e in chart.entry_points if e.name == f'EntryPoint{i}')
            live = _reach(chart, [entry.main_event.v])
            debits = [e for e in live if _params(e).get('GameDataName') == 'NumberOfCoughtGoron'
                      and _action(e) == ('GameDataActor', 'EventTriggerAddOrSubGameDataInt')]
            self.assertEqual(len(debits), 1)
            self.assertEqual(_params(debits[0])['Value'], -1)
            flags = [_params(e)['GameDataName'] for e in live if
                     _params(e).get('GameDataName', '').endswith('_FireTemple_Delete')]
            self.assertEqual(flags, [f'Npc_Goron_{prisoner}_Adult_FireTemple_Delete'])
            self.assertFalse(any(dialogue._is_talk(e) for e in live))

    def test_talon_consumes_one_cucco_and_keeps_his_run_and_saved_state(self):
        for name in ('Dm_HrlCastle_0020', 'Dm_HrlCastle_0020.110'):
            with self.subTest(flow=name):
                _, chart, report = self.patch(name)
                entry = next(e for e in chart.entry_points if e.name == 'EntryPoint0')
                live = _reach(chart, [entry.main_event.v])
                self.assertEqual(len(report['silent_lines']), 9)
                self.assertFalse(any(dialogue._is_talk(e) for e in live))
                debit = [e for e in live if _params(e).get('Actor') == 'Item_AlarmCucco']
                self.assertEqual(len(debit), 1)
                self.assertEqual(_params(debit[0])['Num'], -1)
                self.assertTrue(any(_params(e).get('ASName') == 'C06_Dash' for e in live))
                self.assertTrue(any(_params(e).get('GameDataName') == 'Talon_AfterWakeUp'
                                    and _params(e).get('Value') is True for e in live))

    def test_zora_keeps_root_motion_collision_and_the_question(self):
        before, after, report = self.patch('Dm_Zora_0010')
        self.assertGreaterEqual(len(report['silent_lines']), 16)
        events = {e.name: e for e in after.events}
        for key in ('Event67', 'Event55', 'Event56'):
            old = next(e for e in before.events if e.name == key)
            self.assertEqual(_params(events[key]), _params(old))
        self.assertEqual(_params(events['Event67'])['ASName'], 'C10')
        self.assertIs(_params(events['Event67'])['IsAnimeDriven'], True)
        self.assertEqual(set(events['Event56'].data.cases), {0, 1})

    def test_eye_drops_keep_both_choices_and_debit_only_on_native_branch(self):
        before, after, report = self.patch('Dm_DeathMtTrail_0050')
        self.assertEqual(len(report['silent_lines']), 6)
        events = {e.name: e for e in after.events}
        # Neither the debit nor the following quest request gets cloned/replayed.
        for key in ('Event58', 'Event57'):
            self.assertEqual(_params(events[key]), _params(next(e for e in before.events if e.name == key)))
        # Debit ends a local scene section; Step11 belongs to its caller. Keep
        # that boundary instead of inventing a linear debit -> progress chain.
        old_debit = next(e for e in before.events if e.name == 'Event58')
        self.assertEqual(events['Event58'].data.nxt.v, old_debit.data.nxt.v)
        self.assertEqual(sum(dialogue._offers_choice(e) for e in after.events if dialogue._is_talk(e)
                             and e.name not in report['silent_lines']), 2)
