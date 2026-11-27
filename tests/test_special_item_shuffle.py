"""Native Master Sword flows: resource proof, not a playable game test."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.patching import special_item_shuffle as s
from oot_rando.patching.event_patch import patch_event_params
from oot_rando.formats.evfl_tools import links_to, params_by_event, parse_flow

NUP = os.environ.get('OOT_NUP')


class Planning(unittest.TestCase):
    def test_disabled_requires_no_resources(self):
        self.assertEqual(s.flow_paths({}), ())
        self.assertEqual(s.flow_paths({'shuffle_gerudo_card': True}, {}), ())

    def test_required_native_flows_and_updates(self):
        options = {'shuffle_master_sword': True}
        self.assertEqual(s.flow_paths(options), s.FLOWS)
        with self.assertRaises(ValueError):
            s.flow_paths(options, [])
        members = set(s.FLOWS)
        update = s.FLOWS[0].replace('.bfevfl.zs', '.110.bfevfl.zs')
        members.add(update)
        self.assertEqual(s.flow_paths(options, members), (s.FLOWS[0], update) + s.FLOWS[1:])

    def test_kokiri_shuffle_alone_requires_era_replacement(self):
        options = {'shuffle_kokiri_sword': True}
        path = s.FLOWS[2]
        update = path.replace('.bfevfl.zs', '.110.bfevfl.zs')
        self.assertEqual(s.flow_paths(options), (path,))
        self.assertEqual(s.flow_paths(options, {path, update}), (path, update))
        with self.assertRaises(ValueError):
            s.flow_paths(options, set())


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class NativeFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        cls.nup = Nup(NUP)
        dictionaries_ = dictionaries(cls.nup)
        cls.read = staticmethod(lambda path: decompress(
            cls.nup.read(cls.nup.latest('romfs/' + path)), dictionaries_))

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def patched(self, index):
        path = s.FLOWS[index]
        source = self.read(path)
        raw, report = s.patch_flow(path, source)
        chart = parse_flow(raw).flowchart
        return source, raw, chart, {e.name: e for e in chart.events}, report

    def test_all_native_flows_replay_and_reject_second_application(self):
        members = {p.split('romfs/', 1)[1] for p in self.nup.entries if '/romfs/' in p}
        for path in s.flow_paths({'shuffle_master_sword': True}, members):
            with self.subTest(path=path):
                source = self.read(path)
                raw, report = s.patch_flow(path, source)
                self.assertEqual((raw, report), s.patch_flow(path, source))
                before, after = params_by_event(parse_flow(source)), params_by_event(parse_flow(raw))
                if path == s.FLOWS[0]:
                    before['Event115']['IsEquipDIrect'] = False
                self.assertEqual({k: after[k] for k in before}, before)
                with self.assertRaises(ValueError):
                    s.patch_flow(path, raw)

    def test_pedestal_keeps_random_reward_and_collection_marker(self):
        from oot_rando.patching.event_patch import add_collection_markers
        source = patch_event_params(self.read(s.FLOWS[0]),
                                    [('Event115', 'Actor', s.SWORD, 'Item_Token_Gerudo')])
        source, _ = add_collection_markers(source, {'Event115': 'RandoCollectedMasterSword'})
        raw, _ = s.patch_flow(s.FLOWS[0], source)
        events = {e.name: e for e in parse_flow(raw).flowchart.events}
        gift = events['Event115']
        self.assertEqual(gift.data.params.data['Actor'], 'Item_Token_Gerudo')
        self.assertFalse(gift.data.params.data['IsEquipDIrect'])
        self.assertEqual(gift.data.nxt.v.name, 'RandoCollected_Event115')
        self.assertEqual(events['RandoCollected_Event115'].data.nxt.v.name, 'Event98')

    def test_vanilla_display_is_unreachable(self):
        _, _, chart, events, report = self.patched(1)
        self.assertFalse(links_to(chart, events['Event117']))
        self.assertIn('Event117', report['bypassed'])
        _, _, _, events, _ = self.patched(1)
        self.assertIsNone(events['Event136'].data.nxt.v)

    def test_final_disarm_recovery_remains_native(self):
        path = s.PREFIX + 'Dm_FinalBattle_0010.bfevfl.zs'
        self.assertNotIn(path, s.flow_paths({'shuffle_master_sword': True}))
        source = self.read(path)
        with self.assertRaises(ValueError):
            s.patch_flow(path, source)
        events = {e.name: e for e in parse_flow(source).flowchart.events}
        self.assertEqual(events['Event137'].data.nxt.v.name, 'Event173')
        self.assertEqual(events['Event173'].data.params.data['Actor'], s.SWORD)
        self.assertEqual(events['Event173'].data.params.data['Num'], 1)
        self.assertEqual(events['Event173'].data.nxt.v.name, 'Event260')

    def test_ownership_guards_preserve_owned_and_missing_branches(self):
        cases = {
            2: [('EraFallback', 'Event5', 'Event13')],
            3: [('AllSage', 'Event165', 'Event12')],
            4: [('Arrival', 'Event37', 'Event484')],
            5: [('GanonIntro', 'Event33', 'Event159'), ('GanonExit', 'Event217', 'Event30')],
        }
        for index, checks in cases.items():
            _, _, chart, events, _ = self.patched(index)
            for label, owned, missing in checks:
                with self.subTest(label=label):
                    guard = events['RandoMasterSwordOwned_' + label]
                    self.assertEqual(str(guard.data.actor.v.identifier), 'PouchSystemActor')
                    self.assertEqual(guard.data.actor_query.v.v, 'EventQueryIsExistInPouch')
                    self.assertEqual(guard.data.params.data, {'Actor': s.SWORD, 'Num': 1})
                    self.assertEqual(guard.data.cases[0].v.name, owned)
                    self.assertEqual(guard.data.cases[1].v.name, missing)
                    self.assertTrue(links_to(chart, guard))
                    # Every incoming native link to the action now goes through
                    # inventory ownership; missing inventory never enters it.
                    self.assertEqual([(e.name, kind, key) for e, kind, key in
                                      links_to(chart, events[owned])], [(guard.name, 'case', 0)])
                    self.assertIsNotNone(guard.data.actor.v.params)

    def test_era_change_drops_a_stored_unowned_master_sword(self):
        _, _, chart, events, report = self.patched(2)
        entry = chart.entry_points[0]
        stored = events['RandoMasterSwordStored_EraStored']
        owned = events['RandoMasterSwordOwned_EraStored']
        clear = events['RandoMasterSwordClear_EraStored']
        self.assertIs(entry.main_event.v, events['RandoMasterSwordStored_KokiriEraStored'])
        self.assertIs(entry.main_event.v.data.cases[1].v, stored)
        self.assertEqual(stored.data.actor_query.v.v, 'EventQueryIsGameDataString64')
        self.assertEqual(stored.data.params.data, {
            'GameDataName': 'PlayerStatus.AnotherEraEquipWeapon', 'Value': s.SWORD, 'Index': -1})
        self.assertEqual((stored.data.cases[0].v.name, stored.data.cases[1].v.name),
                         (owned.name, 'Event4'))
        self.assertEqual(owned.data.params.data, {'Actor': s.SWORD, 'Num': 1})
        self.assertEqual((owned.data.cases[0].v.name, owned.data.cases[1].v.name),
                         ('Event4', clear.name))
        self.assertEqual(clear.data.actor_action.v.v, 'EventTriggerSetGameDataString64')
        self.assertEqual(clear.data.params.data, {
            'GameDataName': 'PlayerStatus.AnotherEraEquipWeapon', 'Value': '', 'Index': -1})
        self.assertEqual(clear.data.nxt.v.name, 'Event4')
        self.assertIn(owned.name, report['guards'])

    def test_child_return_equips_kokiri_only_when_owned(self):
        source, _, chart, events, report = self.patched(2)

        def restored_weapon(flowchart, stored, owns):
            # Follow the actual native/patched weapon branch until shield
            # replacement begins; Event0 later copies this slot into EquipWeapon.
            event = flowchart.entry_points[0].main_event.v
            for _ in range(20):
                if event.name == 'Event13':
                    return stored
                params = event.data.params.data if event.data.params else {}
                if hasattr(event.data, 'actor_query'):
                    query = event.data.actor_query.v.v
                    if query == 'EventQueryIsEmptyGameDataString64':
                        result = not stored
                    elif query == 'EventQueryIsGameDataString64':
                        result = stored == params['Value']
                    elif query == 'EventQueryIsExistInPouch':
                        result = owns and params['Actor'] == s.KOKIRI_SWORD
                    elif query == 'EventQueryPlayerIsChild':
                        result = False  # Still adult before equipment is swapped.
                    else:
                        self.fail(query)
                    event = event.data.cases[0 if result else 1].v
                else:
                    self.assertEqual(event.data.actor_action.v.v, 'EventTriggerSetGameDataString64')
                    stored = params['Value']
                    event = event.data.nxt.v
            self.fail('Weapon replacement did not terminate')

        for stored in ('', s.KOKIRI_SWORD):
            with self.subTest(stored=stored):
                # Native flow reproduces both the fallback and stale-storage bug.
                self.assertEqual(restored_weapon(parse_flow(source).flowchart, stored, False), s.KOKIRI_SWORD)
                self.assertEqual(restored_weapon(chart, stored, False), '')
                self.assertEqual(restored_weapon(chart, stored, True), s.KOKIRI_SWORD)
        self.assertIn('RandoMasterSwordOwned_KokiriEraFallback', report['guards'])
        self.assertIn('RandoMasterSwordOwned_KokiriEraStored', report['guards'])
        for label in ('KokiriEraFallback', 'KokiriEraStored'):
            guard = events['RandoMasterSwordOwned_' + label]
            self.assertEqual(str(guard.data.actor.v.identifier), 'PouchSystemActor')
            self.assertEqual(guard.data.params.data, {'Actor': s.KOKIRI_SWORD, 'Num': 1})

    def test_later_arrival_creates_the_hand_sword_only_when_owned(self):
        _, _, chart, events, report = self.patched(6)
        guard = events['RandoMasterSwordOwned_LaterArrival']
        self.assertEqual(guard.data.params.data, {'Actor': s.SWORD, 'Num': 1})
        self.assertEqual(guard.data.cases[0].v.name, 'Event9')
        self.assertNotIn(1, guard.data.cases)
        self.assertEqual([(e.name, kind, key) for e, kind, key in links_to(chart, events['Event9'])],
                         [(guard.name, 'case', 0)])
        self.assertEqual([(e.name, kind, key) for e, kind, key in links_to(chart, guard)],
                         [('Event37', 'case', 1)])
        self.assertIn(guard.name, report['guards'])

    def test_unexpected_native_parameters_fail_closed(self):
        path = s.FLOWS[4]
        source = patch_event_params(self.read(path),
                                    [('Event37', 'EquipmentActorName', s.SWORD, 'Weapon_Sword_Biggoron')])
        with self.assertRaises(ValueError):
            s.patch_flow(path, source)


if __name__ == '__main__':
    unittest.main()
