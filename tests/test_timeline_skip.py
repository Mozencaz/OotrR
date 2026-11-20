"""Animated story scenes that never play (patching/timeline_skip.py)."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import timeline_skip as timelines

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_option_off_changes_nothing(self):
        self.assertEqual(timelines.site_flows(False), ())
        self.assertEqual(timelines.site_flows(None), ())
        self.assertEqual(timelines.site_flows(True), tuple(sorted(timelines.SITES)))

    def test_never_the_title_nor_the_ending(self):
        scenes = {scene for sites in timelines.SITES.values() for _, scene in sites}
        self.assertFalse([s for s in scenes if s.startswith(timelines.EXCLUDED_FAMILIES)])
        self.assertEqual(len(scenes), 75)

    def test_sword_in_hand_is_scene_only(self):
        from types import SimpleNamespace as NS

        def clip(params, start, duration, actor='Player_Event', action=timelines.SWORD_IN_HAND[0]):
            return NS(actor=NS(v=NS(identifier=NS(name=actor))), actor_action=NS(v=NS(v=action)),
                      params=NS(data=dict(params)), start_time=start, duration=duration)
        timeline = NS(duration=200.0)
        held = timelines.SWORD_IN_HAND[1]
        self.assertTrue(timelines.scene_only(clip(held, 100.0, 100.0), timeline))
        self.assertFalse(timelines.scene_only(clip(held, 100.0, 150.0), timeline))   # outlasts the scene
        self.assertFalse(timelines.scene_only(clip({'DynamicEquipmentSlot': 2, 'EquipmentState': 0}, 0.0, 10.0),
                                              timeline))
        warp = 'EventWarpToTargetPosAndRot'
        self.assertTrue(timelines.scene_only(clip({}, 0.0, 1.0, 'Dm_Locator', warp), timeline))
        self.assertFalse(timelines.scene_only(clip({}, 0.0, 1.0, 'Npc_Pierre', warp), timeline))


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class GameFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import Byml, decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        d, members = dictionaries(nup), effective_members(nup)
        cls.read = staticmethod(lambda name: decompress(nup.read(members[timelines.flow_path(name)]), d)
                                if timelines.flow_path(name) in members else None)
        cls.names = sorted(p[len(timelines.FLOWS):-len('.bfevfl.zs')] for p in members
                           if p.startswith(timelines.FLOWS) and p.endswith('.bfevfl.zs'))
        cls.rows = Byml(decompress(nup.read(members['RSDB/EventSetting.Product.111.rstbl.byml.zs']), d)).root
        cls.gamedata = decompress(nup.read(members['GameData/GameDataList.Product.110.byml.zs']), d)

    def test_table_matches_the_scan(self):
        sites, kept = timelines.scan(self.read, self.names, self.rows, self.gamedata)
        self.assertEqual(sites, timelines.SITES)
        self.assertEqual(kept['OpeningEvent/Event3'], 'starts its event')
        self.assertNotIn('Dm_Deku_BossIn', kept)   # its fight start and music are replayed
        self.assertTrue(kept['Dm_FinalBattle_BossIn'].startswith('acts on the world'))
        self.assertEqual(kept['Defeat_Ganon/Event46'], 'leads to the ending')
        self.assertEqual(timelines.scene_replays(self.read, self.rows), timelines.REPLAYS)
        # Link's sword held during the scene is not a world change; Lake Hylia's scarecrows are.
        self.assertNotIn('Dm_Kakariko_0030', kept)
        self.assertTrue(kept['Dm_LakeHrl_0010'].startswith('acts on the world'))
        self.assertEqual(kept['AllSage/Event9'], 'starts its event')   # (Dm_TimeTemple_0050)

    def test_every_flow_drops_its_sites(self):
        from oot_rando.patching.event_info import new_subflows
        fades = []
        for flow in timelines.SITES:
            with self.subTest(flow):
                vanilla = self.read(flow)
                out, report = timelines.drop_timelines(vanilla, flow)
                self.assertTrue(timelines.dropped(out, flow))
                self.assertFalse(timelines.dropped(vanilla, flow))
                self.assertEqual([(r['event'], r['scene']) for r in report], list(timelines.SITES[flow]))
                self.assertFalse(new_subflows({flow: out}, self.read))
                fades += [r['event'] for r in report if r['chain'][-1].endswith('_FadeIn')]
                with self.assertRaises(ValueError):
                    timelines.drop_timelines(out, flow)
        self.assertEqual(len(fades), 3)

    def test_world_actions_are_replayed_in_place(self):
        from oot_rando.patching.event_patch import _flow
        self.assertEqual(timelines.REPLAYS['Dm_Kakariko_0030'],
                         (('EventWorldManagerController', 'EventTrigger_SetTime', {'TimeHour': 0, 'TimeMin': 0}),))
        for flow, sites in timelines.SITES.items():
            for event, scene in sites:
                if scene not in timelines.REPLAYS:
                    continue
                with self.subTest(scene):
                    out, report = timelines.drop_timelines(self.read(flow), flow)
                    chain = next(r['chain'] for r in report if r['event'] == event)
                    events = {e.name: e for e in _flow(out).flowchart.events}
                    replayed = []
                    for name in chain[1:1 + len(timelines.REPLAYS[scene])]:
                        data = events[name].data
                        params = dict(data.params.data) if data.params is not None else None
                        replayed.append((str(data.actor.v.identifier), data.actor_action.v.v, params))
                    self.assertEqual(tuple(replayed), timelines.REPLAYS[scene])

    def test_boss_intro_takes_the_skipped_path(self):
        from oot_rando.patching.event_patch import _flow
        vanilla = self.read('SageOfFire')
        out, report = timelines.drop_timelines(vanilla, 'SageOfFire')
        site = next(r for r in report if r['scene'] == 'Dm_FireTemple_BossIn')
        self.assertEqual(site['queries'], ['Event73'])
        chart = _flow(out).flowchart
        events = {e.name: e for e in chart.events}
        # Played -> fight start -> boss music -> the boss's pre-state -> the skipped case
        self.assertEqual(site['chain'][-1], 'RandoTimeline_Event315_Replay1')
        self.assertEqual(events[site['chain'][-1]].data.nxt.v.name, 'Event216')
        self.assertEqual(events['Event216'].data.nxt.v.name, 'Event145')   # vanilla skip path (BGM, camera)

    def test_fade_in_replaces_a_scene_after_a_fade_out(self):
        _, report = timelines.drop_timelines(self.read('Npc_Kaepora_DeathMountainTrail'),
                                             'Npc_Kaepora_DeathMountainTrail')
        self.assertEqual(report, [{'event': 'Event5', 'scene': 'Dm_DeathMtTrail_0030',
                                   'chain': ['RandoTimeline_Event5_Played', 'RandoTimeline_Event5_FadeIn']}])


if __name__ == '__main__':
    unittest.main()
