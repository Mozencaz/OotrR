"""Native fortress resources: reduced rescues release every cell; card controls guards."""
import os
import unittest

import _src_path  # noqa: F401
from oot_rando.patching import game_defaults, quest_guard, world_openings
from oot_rando.patching import gerudo_fortress as g
from oot_rando.patching.story_fixes import _Chart
from oot_rando.formats.evfl_tools import event_params_of
from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class Fortress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        cls.nup = Nup(os.environ['OOT_NUP'])
        d = dictionaries(cls.nup)
        cls.raw = staticmethod(lambda p: cls.nup.read(cls.nup.latest('romfs/' + p)))
        cls.read = staticmethod(lambda p: decompress(cls.raw(p), d) if p.endswith('.zs') else cls.raw(p))

    def test_fast_rescue_opens_remaining_cells(self):
        data, files, report = world_openings.gerudo_fortress_fast(
            self.read, self.read(game_defaults.GAMEDATA), self.read(quest_guard.CHALLENGES))
        self.assertEqual(game_defaults.read_defaults(data, [world_openings.CARPENTERS_HELPED,
                         world_openings.CARPENTERS_LEFT]), {world_openings.CARPENTERS_HELPED: 3,
                                                          world_openings.CARPENTERS_LEFT: 1})
        # Every last-rescue scene returns through this chain, whichever cell was rescued.
        for first in range(1, 5):
            flags = {f'GerudoFortress_WarpPoint{first:02}_ClearEvent': True}
            events = _Chart(files[g.SPIRIT_FLOW]).events
            event = events['Event192'].data.nxt.v
            while event.name.startswith('RandoFreeCarpenters'):
                params = event_params_of(event)
                self.assertEqual(event.data.actor_action.v.v, 'EventTriggerSetGameDataBool')
                flags[params['GameDataName']] = params['Value']
                event = event.data.nxt.v
            self.assertEqual(event.name, 'Event146')
            self.assertTrue(all(flags.get(flag) for flag in report['freed']['freed']))
        self.assertNotIn(g.CARD, report['freed']['freed'])
        freed = report['freed']['freed']
        # The cell's carpenter is deleted by the native rescue flag, not by the release flags.
        for carpenter in g.CARPENTERS:
            self.assertIn(f'GerudoFortress_Saved_{carpenter}', freed)
            # His thief's key stays obtainable: defeated, it lies in the cell.
            self.assertIn(f'GerudoFortress_DestroyGerudoThief_{carpenter}', freed)
        self.assertIn(g.CELLS_RELEASED, freed)
        # WarpPointXX creates the leader at that cell: only the native one (the last rescue).
        self.assertFalse(any('WarpPoint' in flag for flag in freed))
        known = {int(e['Hash']) for e in byml_codec.load(data)['root']['Data']['Bool']}
        from oot_rando.patching.soul_adapter import murmur3
        self.assertEqual([f for f in freed if murmur3(f) not in known], [])
        with self.assertRaises(ValueError):
            g.free_remaining_carpenters(files[g.SPIRIT_FLOW])

    def test_released_cells_do_not_replay_their_unlock(self):
        # The released lock holds its key at every load: the unlock entries must end at once.
        source = self.read(g.UNLOCK_FLOW)
        raw, report = g.skip_completed_unlocks(source)
        chart = _Chart(raw)
        for entry in chart.chart.entry_points:
            if entry.name not in g.UNLOCK_ENTRIES:
                continue
            guard = entry.main_event.v
            self.assertEqual(guard.data.actor_query.v.v, 'EventQueryIsGameDataBool')
            self.assertEqual(event_params_of(guard), {'GameDataName': g.CELLS_RELEASED, 'Index': -1})
            # Bool switches: case 0 = true. Released: no case, the flow ends; else the native unlock.
            self.assertEqual(set(guard.data.cases), {1})
            self.assertEqual(guard.data.cases[1].v.name, g.UNLOCK_ENTRIES[entry.name])
        self.assertEqual(len(report['entries']), 4)
        with self.assertRaises(ValueError):
            g.skip_completed_unlocks(raw)

    def test_cell_lock_graph_preserves_key_path_until_completion(self):
        import ainb
        from test_world_openings import unflagged_links
        source = self.raw(g.CELL_MODULE)
        raw = g.open_completed_cells(source)
        nodes = ainb.AINB.from_binary(raw).as_dict()['Nodes']
        original = ainb.AINB.from_binary(source).as_dict()['Nodes']
        self.assertEqual(unflagged_links(nodes), [])
        self.assertEqual(raw, g.open_completed_cells(source))
        self.assertEqual(len(nodes), len(original) + 1)
        released = nodes[g.RELEASED]
        self.assertEqual(released['Name'], 'HoldGameDataGetBoolSimple')
        self.assertEqual(released['Parameters']['Inputs']['String'][0]['Default Value'], g.CELLS_RELEASED)
        self.assertNotEqual(g.CELLS_RELEASED, g.RESCUED)  # Requiem must not open unrescued cells.
        # The released flag deletes the chain lock and the shutter, linked like the
        # navmesh cut's own Logic_Delete (node 4); the key path is untouched.
        navmesh = next(p for p in original[4]['Parameters']['Inputs']['Bool'] if p['Name'] == 'Logic_Delete')
        self.assertEqual(navmesh['Flags'], [])
        for target in g.DELETED_ON_RELEASE:
            before, after = original[target], nodes[target]
            self.assertIn(after['Name'], ('ActorLogicDoorChainLock', 'ActorLogicSwitchShutter'))
            inputs = {p['Name']: p for p in after['Parameters']['Inputs']['Bool']}
            self.assertEqual(inputs['Logic_Delete'], dict(navmesh, **{'Node Index': g.RELEASED}))
            self.assertEqual(after['Queries'], before['Queries'] + [g.RELEASED])
            self.assertEqual(after['Plugs']['Generic'],
                             before['Plugs']['Generic'] + [{'Node Index': g.RELEASED, 'Name': 'Logic_Delete'}])
            self.assertEqual({k: v for k, v in inputs.items() if k != 'Logic_Delete'},
                             {p['Name']: p for p in before['Parameters']['Inputs']['Bool'] if p['Name'] != 'Logic_Delete'})
        for index in (1, 2, 4, 5, 6, 7, 8, 9):
            self.assertEqual(nodes[index], original[index])
        with self.assertRaises(ValueError):
            g.open_completed_cells(raw)

    def test_guard_schedules_follow_card_in_both_rescue_states(self):
        for identifier in g.SCHEDULE_IDS:
            raw = self.read(g.schedule_path(identifier))
            before = byml_codec.load(raw)['root']
            after = byml_codec.load(g.membership_schedule(raw)[0])['root']
            for old, new in zip(before['ConditionalSchedule'], after['ConditionalSchedule']):
                if old['ConditionFlag'] != g.RESCUED:
                    self.assertEqual(old, new)
                    continue
                self.assertEqual(new, dict(old, ConditionFlag=g.CARD))
                for rescued in (False, True):
                    for card in (False, True):
                        values = {g.CARD: card, g.RESCUED: rescued}
                        selected = values[new['ConditionFlag']] != bool(new.get('IsReverseCondition'))
                        self.assertEqual(selected, card != bool(old.get('IsReverseCondition')))
            with self.assertRaises(ValueError):
                g.membership_schedule(g.membership_schedule(raw)[0])

    def test_guard_packs_preserve_ai_and_unrelated_resources(self):
        for identifier in g.GUARD_IDS:
            raw = self.read(f'Pack/Actor/Npc_Gerudo_{identifier}.pack.zs')
            before, after = sarc(raw), sarc(g.guard_pack(raw)[0])
            self.assertEqual(set(before), set(after))
            changed = {p for p in before if before[p] != after[p]}
            self.assertTrue(changed)
            self.assertTrue(all('/SecurityGuardParam/' in p or '/InterestReceiveParam/' in p for p in changed))
            for p in changed:
                self.assertIn(g.CARD.encode(), after[p])
            with self.assertRaises(ValueError):
                g.guard_pack(g.guard_pack(raw)[0])

    def test_every_guard_interest_reacts_until_the_card(self):
        for identifier in g.GUARD_IDS:
            raw = self.read(f'Pack/Actor/Npc_Gerudo_{identifier}.pack.zs')
            for path, data in sarc(g.guard_pack(raw)[0]).items():
                if '/InterestReceiveParam/' in path:
                    self.assertNotIn(g.NOT_STARTED.encode(), data, (identifier, path))

    def test_fortress_modules_follow_card_not_quest_step(self):
        import ainb
        for name in g.MEMBERSHIP_MODULES:
            path = f'Logic/{name}.logic.module.ainb'
            source = self.read(path)
            raw, report = g.membership_module(source)
            nodes = ainb.AINB.from_binary(raw).as_dict()['Nodes']
            original = ainb.AINB.from_binary(source).as_dict()['Nodes']
            self.assertFalse(any(n['Name'] == 'HoldChallengeCurrentStepCheckOrder'
                                 and n['Parameters']['Inputs']['String'][1]['Default Value'] == 'Step01'
                                 for n in nodes), name)
            for index in report['checks']:
                self.assertEqual(nodes[index]['Name'], 'HoldGameDataGetBoolSimple')
                self.assertEqual(nodes[index]['Parameters']['Inputs']['String'][0]['Default Value'], g.CARD)
            # Nodes added for the card's negation are wired to the card.
            for node in nodes[len(original):]:
                self.assertEqual(node['Name'], 'OperateOR')
                self.assertIn(node['Parameters']['Inputs']['Bool'][0]['Sources'][0]['Node Index'], report['checks'])
            with self.assertRaises(ValueError):
                g.membership_module(raw)

    def test_prison_dialogue_and_compounds_read_card(self):
        for path, names in ((g.SPIRIT_FLOW, ('Event123', 'Event99', 'Event389')),
                            (g.GUARD_FLOW, ('Event20',))):
            source = _Chart(self.read(path))
            result = _Chart(g.membership_flow(self.read(path), names)[0])
            for name, event in result.events.items():
                if name in names:
                    self.assertEqual(event_params_of(event), {'GameDataName': g.CARD, 'Index': -1})
                    self.assertEqual(event.data.actor_query.v.v, 'EventQueryIsGameDataBool')
                    self.assertEqual({k: v.v.name for k, v in event.data.cases.items()},
                                     {k: v.v.name for k, v in source.events[name].data.cases.items()})
                elif hasattr(event.data, 'params'):
                    self.assertEqual(event_params_of(event), event_params_of(source.events[name]))
        raw = self.read(game_defaults.GAMEDATA)
        self.assertFalse(g.expressions_applied(raw))
        patched, _ = g.membership_expressions(raw)
        self.assertTrue(g.expressions_applied(patched))
        with self.assertRaises(ValueError):
            g.membership_expressions(patched)
