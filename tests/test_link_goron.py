"""Replay the native Darunia Jr. spawn and pre/post-intro schedules (OOT_NUP)."""
import _src_path  # noqa: F401
import copy
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.formats.evfl_tools import parse_flow

NUP = os.environ.get('OOT_NUP')
MODULE = 'Logic/GoronCity_Adult_Prefab_118a.logic.module.ainb'
SCHEDULES = 'Pack/AIScheduleParam.pack.zs'
READY = 'Component/AIScheduleParam/SageOfFire_Ready_Npc_Goron_DaruniaJr_Adult.game__component__AIScheduleParam.bgyml'
STOP = READY.replace('_Ready_', '_StopDaruniaJr_')
FLOW = 'Event/EventFlow/SageOfFire.bfevfl.zs'


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class DaruniaJr(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        raw = self.nup.read(self.nup.latest('romfs/' + path))
        return self.decompress(raw, self.d) if path.endswith('.zs') else raw

    def patch(self, path, raw):
        from oot_rando.patching import link_goron
        return dict(link_goron.resource_fixes())[path](raw)[0]

    def test_playable_actor_created_on_first_load_without_intro_flag(self):
        import ainb
        source = self.read(MODULE)
        before = ainb.AINB.from_binary(source).as_dict()
        after = ainb.AINB.from_binary(self.patch(MODULE, source)).as_dict()
        create = next(p for p in after['Nodes'][0]['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Create')
        # First arrival: GenerateDaruniaJr is false, so following node 13 hides him.
        self.assertEqual(create['Node Index'], -1)
        self.assertIs(create['Default Value'], True)
        expected = copy.deepcopy(before)
        expected['Nodes'][0]['Parameters']['Inputs']['Bool'][4] = create
        expected['Nodes'][0]['Queries'] = after['Nodes'][0]['Queries']
        expected['Nodes'][0]['Plugs']['Generic'] = [p for p in expected['Nodes'][0]['Plugs']['Generic']
                                                  if p['Name'] != 'Logic_Create']
        for index in (10, 11):
            node = expected['Nodes'][index]
            self.assertIs(after['Nodes'][index]['Parameters']['Inputs']['Bool'][5]['Default Value'], True)
            self.assertEqual(after['Nodes'][index]['Parameters']['Inputs']['Bool'][5]['Node Index'], -1)
            node['Parameters']['Inputs']['Bool'][5] = after['Nodes'][index]['Parameters']['Inputs']['Bool'][5]
            node['Queries'].remove(12)
            del node['Plugs']['Generic']
        self.assertEqual(after, expected)  # bomb state and doors preserved; cinematic doubles hidden

    def test_ready_uses_stunnable_rolling_schedule_and_bomb_talk(self):
        source = self.read(SCHEDULES)
        files = sarc(self.patch(SCHEDULES, source))
        ready = byml_codec.load(files[READY])['root']
        stop = byml_codec.load(files[STOP])['root']
        self.assertEqual(ready['DefaultSchedule'], stop['DefaultSchedule'])
        self.assertTrue(ready['DefaultSchedule']['ActionSchedule'][0]['Setting']['IsTurnToTerror'])
        original = sarc(source)
        self.assertEqual({p: b for p, b in files.items() if p != READY},
                         {p: b for p, b in original.items() if p != READY})

    def test_late_intro_does_not_reset_stun_talk_or_later_quest_progress(self):
        chart = parse_flow(self.patch(FLOW, self.read(FLOW))).flowchart
        requests = {e.name: e for e in chart.events}
        entries = {e.name: e for e in chart.entry_points}
        for name in ('SageOfFire_CityIn', 'SageOfFire_CityIn_CrackWall'):
            event = entries[name].main_event.v
            for flag in ('SageOfFire_GenerateDaruniaJr', 'HavePlayedEvent.SageOfFire_CityIn'):
                self.assertEqual(event.data.params.data, {'GameDataName': flag, 'Index': -1, 'Value': True})
                event = event.data.nxt.v
            self.assertTrue(event.name.startswith('RandoGoronForward_'))
        for event, step in [('Event4', 'StopDaruniaJr'), ('Event9', 'TalkDaruniaJr'), ('Event13', 'MoveStatue')]:
            with self.subTest(step=step):
                guards = [e for e in chart.events if e.name.startswith('RandoGoronForward_')
                          and any(v.v.name == event for v in (getattr(e.data, 'cases', None) or {}).values())]
                self.assertEqual(len(guards), 1)
                guard = guards[0]
                self.assertEqual(guard.data.params.data['GameDataName'], 'SageOfFire_IsAfter_' + step + '_Exp')
                self.assertEqual(guard.data.cases[1].v.name, event)  # not past: native transition
                self.assertNotEqual(getattr(guard.data.cases.get(0), 'v', None), requests[event])

    def test_native_steps_expressions_and_schedule_composition(self):
        from oot_rando.patching import gerudo_fortress, link_goron, quest_guard
        from oot_rando.patching.soul_adapter import GAMEDATA
        self.assertEqual(tuple(quest_guard.challenge_steps(self.read(quest_guard.CHALLENGES))['SageOfFire']),
                         link_goron.STEPS)
        quest_guard.check_expressions(self.read(GAMEDATA),
                                     ['SageOfFire_IsAfter_' + step + '_Exp' for step in link_goron.STEPS[1:4]])
        source = self.read(SCHEDULES)
        gerudo = gerudo_fortress.archery_schedule_pack(source)[0]
        first = link_goron.stunnable_before_intro(gerudo)[0]
        second = gerudo_fortress.archery_schedule_pack(link_goron.stunnable_before_intro(source)[0])[0]
        self.assertEqual(first, second)
        for path, fix in link_goron.resource_fixes():
            with self.subTest(path=path), self.assertRaises(ValueError):
                fix(fix(self.read(path))[0])


if __name__ == '__main__':
    unittest.main()
