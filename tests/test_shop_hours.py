"""Native door/service graphs and attendants for shops at any time of day."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.patching import shop_hours as shops
from oot_rando.formats.evfl_tools import params_by_event, parse_flow


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class ShopHours(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.addClassCleanup(cls.nup.stream.close)
        cls.dicts = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    def read(self, path):
        raw = self.nup.read(self.nup.latest('romfs/' + path))
        return self.decompress(raw, self.dicts) if path.endswith('.zs') else raw

    def test_entrances_keep_indoor_locks_and_all_unrelated_nodes(self):
        import ainb
        for name in (*shops.DOORS, *shops.GATES):
            with self.subTest(name=name):
                raw = self.read(shops.module(name))
                if name == 'Market_Child_Prefab_0c76':
                    from oot_rando.patching.story_fixes import bombchu_shop_open_from_start
                    raw = bombchu_shop_open_from_start(raw)[0]
                before = ainb.AINB.from_binary(raw).as_dict()
                result, _ = shops.doors_all_hours(raw, name)
                after = ainb.AINB.from_binary(result).as_dict()
                changed = {i for i, (a, b) in enumerate(zip(before['Nodes'], after['Nodes'])) if a != b}
                expected = {d[0] for d in shops.DOORS.get(name, ())}
                if name in shops.GATES:
                    expected.add(shops.GATES[name][0])
                self.assertEqual(changed, expected)
                for i in changed:
                    a, b = before['Nodes'][i], after['Nodes'][i]
                    indoor_before = [v for v in a['Parameters']['Inputs']['Bool'] if v['Name'] == 'EnableOpenIndoor']
                    indoor_after = [v for v in b['Parameters']['Inputs']['Bool'] if v['Name'] == 'EnableOpenIndoor']
                    self.assertEqual(indoor_before, indoor_after)
                for index, _, param, _, _ in shops.DOORS.get(name, ()):
                    entry = next(v for v in after['Nodes'][index]['Parameters']['Inputs']['Bool'] if v['Name'] == param)
                    self.assertEqual(entry['Node Index'], -1)
                    self.assertTrue(entry['Default Value'])
                if name in shops.GATES:
                    index, sources, keep = shops.GATES[name]
                    node = after['Nodes'][index]
                    self.assertEqual([(s['Node Index'], s['Output Index']) for s in node['Parameters']['Inputs']['Bool'][0]['Sources']],
                                     [sources[keep], sources[keep]])
                    # Both time states now preserve the same age/quest truth value.
                    for day in (False, True):
                        for retained in (False, True):
                            values = {sources[keep]: retained, sources[1 - keep]: day}
                            actual = all(values[(s['Node Index'], s['Output Index'])]
                                         for s in node['Parameters']['Inputs']['Bool'][0]['Sources'])
                            self.assertEqual(actual, retained)
                with self.assertRaises(ValueError):
                    shops.doors_all_hours(result, name)

    def test_services_take_normal_branch_in_both_time_states_only(self):
        for spec in shops.SERVICES:
            with self.subTest(flow=spec[0]):
                path = 'Event/EventFlow/' + spec[0] + '.bfevfl.zs'
                source = parse_flow(self.read(path))
                result, _ = shops.service_all_hours(self.read(path), spec)
                patched = parse_flow(result)
                old = {e.name: e for e in source.flowchart.events}
                new = {e.name: e for e in patched.flowchart.events}
                self.assertEqual(params_by_event(source), params_by_event(patched))
                for name, event in old.items():
                    if hasattr(event.data, 'cases'):
                        expected = {k: v.v.name if v.v else None for k, v in event.data.cases.items()}
                        if name == spec[1]:
                            expected = {0: spec[5], 1: spec[5]}
                        self.assertEqual({k: v.v.name if v.v else None for k, v in new[name].data.cases.items()}, expected)
                    if hasattr(event.data, 'nxt'):
                        self.assertEqual(getattr(event.data.nxt.v, 'name', None), getattr(new[name].data.nxt.v, 'name', None))
                with self.assertRaises(ValueError):
                    shops.service_all_hours(result, spec)

    def test_native_minigame_attendants_have_all_day_talk_callbacks(self):
        from oot_rando.formats.inspect_resources import sarc, Byml
        pack = sarc(self.read('Pack/AIScheduleParam.pack.zs'))
        for game, actor in (('HitTarget', '019'), ('SequentialChoiceTreasure', '022'), ('BombchuBowling', '067')):
            path = f'Component/AIScheduleParam/MiniGame_{game}_Ready_Npc_Hylia_{actor}_Shop_Child.game__component__AIScheduleParam.bgyml'
            document = Byml(pack[path]).root
            schedule = document['DefaultSchedule']
            self.assertTrue(any(e['$type'] == 'game__aischedule__OnPlayerTalk' for e in schedule['EventEntry']))
            self.assertEqual(len(schedule['ActionSchedule']), 1)
            self.assertNotIn('StartTime', schedule['ActionSchedule'][0])
            self.assertEqual(schedule['ActionSchedule'][0]['ActionTimeDivision'], 3710534274)
        # Native attendants exist in both Kakariko scene variants and the Market.
        for scene in ('Market/Market_Child', 'KakarikoVillage/KakarikoVillage_Adult',
                      'KakarikoVillage/KakarikoVillage_Adult_Alternative'):
            root = Byml(self.read('Banc/' + scene + '_Static.bcett.byml.zs')).root
            names = {a['Gyaml'] for a in root['Actors'] if not a.get('Presence')}
            self.assertIn('Npc_Hylia_019_Shop_Child', names)
            self.assertIn('Npc_Hylia_020_Shop_' + ('Child' if scene.startswith('Market') else 'Adult'), names)

    def test_shopkeeper_schedules_keep_talk_available_all_day(self):
        from oot_rando.formats.inspect_resources import Byml
        for actor in ('018_Shop_Child', '018_Shop_Adult', '020_Shop_Child',
                      '020_Shop_Adult', '021_Shop_Child', '023_Shop_Child'):
            path = f'Component/AIScheduleParam/Npc_Hylia_{actor}.game__component__AIScheduleParam.bgyml'
            document = Byml(self.read(path)).root
            for schedule in [document['DefaultSchedule'], *document.get('ConditionalSchedule', [])]:
                actions = schedule['ActionSchedule']
                self.assertEqual(len(actions), 1, actor)
                self.assertIn(actions[0].get('StartTime'), (None, 0), actor)
                self.assertTrue(any(e['$type'] == 'game__aischedule__OnPlayerTalk'
                                    for e in schedule['EventEntry']), actor)


if __name__ == '__main__':
    unittest.main()
