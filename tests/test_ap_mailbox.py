"""Archipelago reception: global sequence watcher, item-get entry, memory write helpers."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import struct
import unittest

from oot_rando.tracker.live_memory import bool_slot

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_bool_slot_probes_like_the_game(self):
        size = 4
        table = bytearray(size * 8)
        struct.pack_into('<II', table, (9 % size) * 8, 5, 0)      # another key in 9's home slot
        struct.pack_into('<II', table, ((9 % size) + 1) * 8, 9, 7)
        self.assertEqual(bool_slot(bytes(table), size, 9), 7)
        self.assertIsNone(bool_slot(bytes(table), size, 13))      # empty slot reached

    def test_received_dungeon_keys_use_the_seed_key_actors(self):
        # A ring received outside its dungeon once played an item get with no actor
        # built (the ring was only built for keys placed in this world): softlock.
        from oot_rando.patching.ap_mailbox import key_items, records
        items = records([{'item': 'Small Key Ring (Ganons Castle)', 'location': 'L1', 'player': 'Ami'},
                         {'item': 'Boss Key (Forest Temple)', 'location': 'L2', 'player': 'Ami'},
                         {'item': 'Kokiri Sword', 'location': 'L3', 'player': 'Ami'}])
        self.assertEqual([r['actor'] for r in items],
                         ['Item_KeyRing_Ganon', 'Item_BossKey_ForestTemple', 'Item_Sword_Kokiri'])
        self.assertEqual(key_items(items), ['Boss Key (Forest Temple)', 'Small Key Ring (Ganons Castle)'])
        for item in ('Small Key (Forest Temple)', 'Boss Key (Ganons Castle)', 'Map (Fire Temple)',
                     'Small Key Ring (Thieves Hideout)'):
            with self.assertRaises(ValueError):
                records([{'item': item, 'location': 'L', 'player': 'Ami'}])


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(NUP)
        cls.d, cls.m = dictionaries(cls.nup), effective_members(cls.nup)
        cls.read = lambda self, p, z=True: decompress(cls.nup.read(cls.m[p]), cls.d) if z else cls.nup.read(cls.m[p])

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def test_vanilla_sequence_rewritten_byte_for_byte(self):
        import ainb
        from oot_rando.patching.ap_mailbox import MAIN_UPDATE, ainb_to_binary
        raw = self.read(MAIN_UPDATE, False)
        self.assertEqual(ainb_to_binary(ainb.AINB.from_binary(raw).as_dict()), raw)

    REMOTE = [{'item': 'Rupees (20)', 'location': 'Chest A', 'player': 'Ami'},
              {'item': 'Kokiri Sword', 'location': 'Chest B', 'player': 'Ami'}]

    def test_records(self):
        from oot_rando.patching.ap_mailbox import records
        items = records(self.REMOTE)
        self.assertEqual([r['actor'] for r in items], ['TBox_Rupee_Red', 'Item_Sword_Kokiri'])
        self.assertEqual(len({r['key'] for r in items}), 2)
        self.assertEqual([r['style'] for r in items], ['pickup', 'get'])
        with self.assertRaises(ValueError):
            records(self.REMOTE + self.REMOTE[:1])
        hookshot = records([{'item': 'Progressive Hookshot', 'location': 'X', 'player': 'Ami'}])[0]
        self.assertEqual(hookshot['style'], 'progressive')
        self.assertEqual(len(hookshot['tiers']), 2)

    def test_watchers_copy_the_after_event_pattern(self):
        import ainb
        from oot_rando.patching.ap_mailbox import MAIN_UPDATE, patch_main_update, records
        items = records(self.REMOTE)
        nodes = ainb.AINB.from_binary(patch_main_update(self.read(MAIN_UPDATE, False), items)).as_dict()['Nodes']
        group = nodes[nodes[0]['Plugs']['Child'][-1]['Node Index']]   # one group: 2 watchers
        self.assertEqual(group['Node Type'], 'Element_Simultaneous')
        for index, record in enumerate(items):
            selector = nodes[group['Plugs']['Child'][index]['Node Index']]
            query = nodes[selector['Queries'][0]]
            self.assertEqual(query['Parameters']['Inputs']['String'][0]['Default Value'], record['recv'])
            both = nodes[selector['Plugs']['Child'][0]['Node Index']]
            names = {nodes[c['Node Index']]['Name']: nodes[c['Node Index']] for c in both['Plugs']['Child']}
            self.assertEqual(names['SeqOneShotRequestEvent']['Parameters']['Inputs']['String'][0]['Default Value'],
                             record['event'])
            self.assertEqual(names['SeqOneShotSetNonStructGameDataBool']['Parameters']['Inputs']['String'][0]
                             ['Default Value'], record['recv'])

    def test_ocarina_handed_over_without_the_pose(self):
        # 13/11 in game: the ocarinas cannot be held up (accessory actors): the get crashed.
        from oot_rando.patching import ap_mailbox
        from oot_rando.patching.event_patch import _flow
        items = ap_mailbox.records([{'item': 'Ocarina', 'location': 'O', 'player': 'Ami'}])
        flow = ap_mailbox.add_entries(self.read(ap_mailbox.FLOW_PATH), items)
        entry = {e.name: e for e in _flow(flow).flowchart.entry_points}[items[0]['event']]
        check = entry.main_event.v                                   # holds the Ocarina of Time?
        give = check.data.cases[1].v.data.cases[0].v                  # holds the Fairy Ocarina: give Time
        self.assertEqual(ap_mailbox.given_actor(give)[0], 'Item_Ocarina_Time')
        self.assertEqual(give.data.actor_action.v.v, 'EventTriggerAddOrRemovePouchContent')
        self.assertEqual(give.data.nxt.v.data.res_flowchart_name, ap_mailbox.DISPLAY_FLOW)

    def test_handed_over_actors_can_be_held(self):
        # Every native actor given with Link's item-get pose derives from a holdable base.
        import json
        from oot_rando.formats import byml_codec
        from oot_rando.formats.inspect_resources import sarc
        from oot_rando.game.remake_world import PROGRESSIVE
        from oot_rando.patching import ap_mailbox
        held = set()
        for item, tiers in PROGRESSIVE.items():
            held |= set(tiers)
        held -= set(ap_mailbox.DISPLAY_ONLY)
        bases = ('Item_EventObject_Base', 'Obj_Item_Base')
        for actor in sorted(held):
            pack = sarc(self.read('Pack/Actor/' + actor + '.pack.zs'))   # holds its parents' params
            chain, current = [], actor
            while current and f'Actor/{current}.engine__actor__ActorParam.bgyml' in pack:
                param = byml_codec.load(pack[f'Actor/{current}.engine__actor__ActorParam.bgyml'])['root']
                current = param.get('$parent', '').split('/')[-1].split('.')[0] or None
                chain.append(current)
            with self.subTest(actor=actor):
                self.assertTrue(set(chain) & set(bases), chain)
        for actor in ap_mailbox.DISPLAY_ONLY:
            param = byml_codec.load(sarc(self.read('Pack/Actor/' + actor + '.pack.zs'))[
                f'Actor/{actor}.engine__actor__ActorParam.bgyml'])['root']
            self.assertNotIn('$parent', param)

    def test_hundreds_of_watchers(self):
        # A node lists at most 255 children: the watchers hang under groups.
        import ainb
        from oot_rando.patching.ap_mailbox import MAIN_UPDATE, WATCHER_GROUP, patch_main_update, records
        items = records([{'item': 'Rupees (5)', 'location': f'L{i}', 'player': 'Ami'} for i in range(300)])
        raw = self.read(MAIN_UPDATE, False)
        root_before = len(ainb.AINB.from_binary(raw).as_dict()['Nodes'][0]['Plugs']['Child'])
        nodes = ainb.AINB.from_binary(patch_main_update(raw, items)).as_dict()['Nodes']
        groups = -(-300 // WATCHER_GROUP)
        self.assertEqual(len(nodes[0]['Plugs']['Child']), root_before + groups)
        self.assertTrue(all(len(n['Plugs'].get('Child', [])) <= 255 for n in nodes))

    def test_entries_and_rows(self):
        from oot_rando.formats.inspect_resources import Byml
        from oot_rando.patching import ap_mailbox
        from oot_rando.patching.event_info import entry_names, flow_path
        items = ap_mailbox.records(self.REMOTE)
        flow = ap_mailbox.add_entries(self.read(ap_mailbox.FLOW_PATH), items)
        self.assertTrue({r['event'] for r in items} <= set(entry_names(flow)))
        rows = Byml(ap_mailbox.add_event_rows(self.read(ap_mailbox.EVENT_SETTINGS), items)).root
        row = next(r for r in rows if r['__RowId'] == items[1]['event'])
        self.assertEqual(row['EntryPointName'], items[1]['event'])
        current = lambda name: flow if name == ap_mailbox.FLOW else (
            self.read(flow_path(name)) if flow_path(name) in self.m else None)
        raw, info = ap_mailbox.add_analyzed_rows(self.read(ap_mailbox.ANALYZED), items, current)
        self.assertIn('Dm_SY_Get', info['subflows'])
        analyzed = {r['__RowId']: r for r in Byml(raw).root}
        self.assertEqual(analyzed[items[1]['event']].get('SubFlowList'), info['subflows'])   # item get
        self.assertIsNone(analyzed[items[0]['event']].get('SubFlowList'))                   # pick-up

    def test_progressive_tier_chain(self):
        # Tier chosen in game: highest held + 1 (the last one again when all are held).
        from oot_rando.patching import ap_mailbox
        from oot_rando.patching.event_patch import _flow
        from oot_rando.game.remake_world import PROGRESSIVE
        items = ap_mailbox.records(self.REMOTE + [
            {'item': 'Progressive Wallet', 'location': 'W', 'player': 'Moi'},
            {'item': 'Bomb Bag', 'location': 'B', 'player': 'Ami'}])
        flow = ap_mailbox.add_entries(self.read(ap_mailbox.FLOW_PATH), items)
        entries = {e.name: e for e in _flow(flow).flowchart.entry_points}
        bag = items[3]
        self.assertEqual(bag['tiers'], PROGRESSIVE['Bomb Bag'])
        event, seen = entries[bag['event']].main_event.v, []
        while event.name != bag['event'] + '_Give0':
            seen.append((event.data.params.data['Actor'], event.data.cases[0].v.data.params.data['ActorName']))
            event = event.data.cases[1].v
        tiers = bag['tiers']
        self.assertEqual(seen, [(tiers[2], tiers[2]), (tiers[1], tiers[2]), (tiers[0], tiers[1])])
        self.assertEqual(event.data.params.data['ActorName'], tiers[0])
        from oot_rando.patching.event_info import flow_path
        current = lambda name: flow if name == ap_mailbox.FLOW else (
            self.read(flow_path(name)) if flow_path(name) in self.m else None)
        raw, info = ap_mailbox.add_analyzed_rows(self.read(ap_mailbox.ANALYZED), items[2:], current)
        self.assertIn('Dm_SY_Get', info['subflows'])


if __name__ == '__main__':
    unittest.main()
