"""Per-chest opening flags: records, map edits, rows and (with OOT_NUP) flow entry points."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.patching import chest_flags

NUP = os.environ.get('OOT_NUP')
ROWS = {'Dm_SY_TreasureboxSmall': {'__RowId': 'Dm_SY_TreasureboxSmall', 'EntryPointName': 'Success',
                                   'FlowchartFileName': 'Work/Event/EventFlow/Dm_SY_TreasureboxSmall.evfc'},
        'Dm_SY_Treasurebox': {'__RowId': 'Dm_SY_Treasurebox', 'EntryPointName': 'Success',
                              'FlowchartFileName': 'Work/Event/EventFlow/Dm_SY_Treasurebox.evfc'},
        'KokiriForest_TreasureBox_NaviChatOff': {
            '__RowId': 'KokiriForest_TreasureBox_NaviChatOff', 'EntryPointName': 'Success_MidoHouse',
            'FlowchartFileName': 'Work/Event/EventFlow/Dm_SY_TreasureboxSmall.evfc'}}
MAPS = {'A': {'Actors': [{'Gyaml': 'Obj_TBox_A_01', 'Dynamic': {'Drop__DropActor': 'X',
                                                                'GetEventName': 'KokiriForest_TreasureBox_NaviChatOff'}},
                         {'Gyaml': 'Obj_TBox_A_02_NoBake', 'Dynamic': {'Drop__DropActor': 'Y'}},
                         {'Gyaml': 'Obj_Pot_A_01', 'Dynamic': {}},
                         {'Gyaml': 'Obj_TBox_A_01', 'Dynamic': {'GetEventName': 'Unknown_Event'}}]},
        'B': {'Actors': [{'Gyaml': 'Obj_TBox_A_01', 'Dynamic': {}}]}}


def placement(gid, *variants):
    return {'id': gid, 'source': 'chest', 'variants': list(variants)}


class Units(unittest.TestCase):
    def records(self):
        return chest_flags.plan_records(
            [placement('Kokiri#1', ('A', 0)), placement('Dungeon#2', ('A', 1)), placement('Mixed#3', ('A', 0), ('B', 0)),
             placement('Pot#4', ('A', 2)), placement('Odd#5', ('A', 3)), {'id': 'Shop#6', 'source': 'shop'}],
            MAPS.__getitem__, 'f' * 64, ROWS)

    def test_records(self):
        records, skipped = self.records()
        by_id = {r['id']: r for r in records}
        self.assertEqual(set(by_id), {'Kokiri#1', 'Dungeon#2'})
        self.assertEqual(by_id['Kokiri#1'], {
            'id': 'Kokiri#1', 'event': 'RandoChest_1', 'base': 'KokiriForest_TreasureBox_NaviChatOff',
            'entry': 'Success_MidoHouse', 'flow': 'Event/EventFlow/Dm_SY_TreasureboxSmall.bfevfl.zs',
            'flag': 'RandoCheck.ffffffffffffffff.Kokiri#1',
            'variants': [{'resource': 'A', 'index': 0, 'before': 'KokiriForest_TreasureBox_NaviChatOff'}]})
        self.assertEqual((by_id['Dungeon#2']['base'], by_id['Dungeon#2']['flow']),
                         ('Dm_SY_Treasurebox', 'Event/EventFlow/Dm_SY_Treasurebox.bfevfl.zs'))
        self.assertEqual(set(skipped), {'Mixed#3', 'Pot#4', 'Odd#5'})   # 2 events, not a chest, unknown row

    def test_map_edits_add_or_replace_the_event(self):
        records, _ = self.records()
        edits = chest_flags.map_edits(records)['A']
        self.assertIn({'path': ('Actors', 1, 'Dynamic', 'GetEventName'), 'before': None, 'after': 'RandoChest_2'}, edits)
        self.assertIn({'path': ('Actors', 0, 'Dynamic', 'GetEventName'),
                       'before': 'KokiriForest_TreasureBox_NaviChatOff', 'after': 'RandoChest_1'}, edits)

    def test_rows_are_sorted_copies(self):
        records, _ = self.records()
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': [dict(r) for r in sorted(
            ROWS.values(), key=lambda r: r['__RowId'])]})
        rows = byml_codec.load(chest_flags.add_rows(raw, records))['root']
        self.assertEqual([r['__RowId'] for r in rows], sorted(r['__RowId'] for r in rows))
        row = next(r for r in rows if r['__RowId'] == 'RandoChest_1')
        self.assertEqual((row['EntryPointName'], row['FlowchartFileName']),
                         ('RandoChest_1', ROWS['KokiriForest_TreasureBox_NaviChatOff']['FlowchartFileName']))
        with self.assertRaises(ValueError):
            chest_flags.add_rows(chest_flags.add_rows(raw, records), records)


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class GameFlow(unittest.TestCase):
    def test_entry_sets_the_flag_then_runs_the_original_entry(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        from oot_rando.patching.event_patch import _flow
        nup = Nup(NUP)
        d = dictionaries(nup)
        path = 'Event/EventFlow/Dm_SY_TreasureboxSmall.bfevfl.zs'
        raw = decompress(nup.read(effective_members(nup)[path]), d)
        records = [{'event': 'RandoChest_1', 'entry': 'Success_MidoHouse', 'flag': 'RandoCheck.x.A#1', 'flow': path},
                   {'event': 'RandoChest_2', 'entry': 'Success', 'flag': 'RandoCheck.x.A#2', 'flow': path}]
        chart = _flow(chest_flags.add_entries(raw, records)).flowchart
        entries = {e.name: e for e in chart.entry_points}
        for record in records:
            mark = entries[record['event']].main_event.v
            self.assertEqual(dict(mark.data.params.data), {'GameDataName': record['flag'], 'Index': -1, 'Value': True})
            run = mark.data.nxt.v
            self.assertEqual((run.data.entry_point_name, run.data.res_flowchart_name), (record['entry'], ''))
            self.assertEqual([chart.events[i] for i in entries[record['event']]._sub_flow_event_indices], [run])
        self.assertEqual(len(entries), len(_flow(raw).flowchart.entry_points) + 2)


if __name__ == '__main__':
    unittest.main()
