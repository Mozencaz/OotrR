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
        with self.assertRaises(ValueError):
            records([{'item': 'Progressive Hookshot', 'location': 'X', 'player': 'Ami'}])

    def test_watchers_copy_the_after_event_pattern(self):
        import ainb
        from oot_rando.patching.ap_mailbox import MAIN_UPDATE, patch_main_update, records
        items = records(self.REMOTE)
        nodes = ainb.AINB.from_binary(patch_main_update(self.read(MAIN_UPDATE, False), items)).as_dict()['Nodes']
        for index, record in enumerate(items):
            selector = nodes[nodes[0]['Plugs']['Child'][-2 + index]['Node Index']]
            query = nodes[selector['Queries'][0]]
            self.assertEqual(query['Parameters']['Inputs']['String'][0]['Default Value'], record['recv'])
            both = nodes[selector['Plugs']['Child'][0]['Node Index']]
            names = {nodes[c['Node Index']]['Name']: nodes[c['Node Index']] for c in both['Plugs']['Child']}
            self.assertEqual(names['SeqOneShotRequestEvent']['Parameters']['Inputs']['String'][0]['Default Value'],
                             record['event'])
            self.assertEqual(names['SeqOneShotSetNonStructGameDataBool']['Parameters']['Inputs']['String'][0]
                             ['Default Value'], record['recv'])

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


if __name__ == '__main__':
    unittest.main()
