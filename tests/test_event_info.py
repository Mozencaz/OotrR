"""Sub-flow dependencies of events (GameAnalyzedEventInfo). NUP tests need OOT_NUP."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
NUP = os.environ.get('OOT_NUP')


class ClosureTests(unittest.TestCase):
    def test_transitive_per_entry_and_loop_safe(self):
        from oot_rando.patching import event_info
        calls = {('A', 'a'): {('B', 'b')}, ('B', 'b'): {('C', 'c'), ('A', 'a')}, ('C', 'c'): set(),
                 ('C', 'other'): {('D', 'd')}}
        original = event_info.entry_calls
        event_info.entry_calls = lambda raw, entry: calls.get((raw, entry), set())
        try:
            self.assertEqual(event_info.closure({('A', 'a')}, lambda name: name), {'A', 'B', 'C'})  # not D
        finally:
            event_info.entry_calls = original


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class NupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(NUP)
        cls.members = effective_members(cls.nup)
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def raw(self, path):
        return self.decompress(self.nup.read(self.members[path]), self.d)

    def flow(self, name):
        from oot_rando.patching.event_info import flow_path
        path = flow_path(name)
        return self.raw(path) if path in self.members else None

    def test_deku_tree_gift_lists_the_item_get_for_warp_kokiri(self):
        from oot_rando.formats.byml_codec import load
        from oot_rando.formats.inspect_resources import Byml
        from oot_rando.patching import event_info, qol_patches
        from oot_rando.patching.event_patch import add_collection_markers
        spec = qol_patches.GIFT_AFTER_CUTSCENE['Event/EventFlow/Dm_Kokiri_0130.bfevfl.zs']
        escape = self.raw(spec['flow'])
        given, _ = qol_patches.give_gift_after(escape, spec['after'], 'Item_HoverBoot', 'RandoCheck.test.boss')
        changed = {'Dm_SY_BancChange_EscapeDungeon': given}
        added = event_info.new_subflows(changed, self.flow)
        self.assertEqual(added, {('Dm_SY_BancChange_EscapeDungeon', 'Warp_Kokiri'):
                                 {('Dm_SY_GetInEvent', 'GetInEvent_NotTurn_NotNpc')}})
        settings = Byml(self.raw(qol_patches.EVENT_SETTINGS)).root
        info = self.raw(event_info.GAME_ANALYZED_EVENT_INFO)
        patched, report = event_info.add_subflow_dependencies(
            info, settings, added, lambda name: changed.get(name) or self.flow(name))
        rows = {r['__RowId']: r for r in load(patched)['root']}
        before = {r['__RowId']: r for r in load(info)['root']}
        warp = rows['KokiriForest_WarpFromInsideTheDekuTree']['SubFlowList']
        self.assertEqual(before['KokiriForest_WarpFromInsideTheDekuTree']['SubFlowList'], ['NaviChat'])
        # As listed by the vanilla callers of the same entry (Skull Kid's heart piece).
        self.assertEqual(warp, ['ActionGuide', 'Dm_SY_Get', 'Dm_SY_GetInEvent', 'GetPouchContent', 'NaviChat',
                                'NaviEventCommon'])
        self.assertEqual(warp, sorted(warp, key=str.lower))
        self.assertEqual(sorted(report), ['KokiriForest_WarpFromInsideTheDekuTree'])   # only that event
        for row_id, row in rows.items():
            old = before[row_id]
            if row_id in report:
                self.assertEqual({k: v for k, v in old.items() if k != 'SubFlowList'},
                                 {k: v for k, v in row.items() if k != 'SubFlowList'})
            else:
                self.assertEqual(old, row)

    def test_no_new_call_no_change(self):
        from oot_rando.patching import event_info
        info = self.raw(event_info.GAME_ANALYZED_EVENT_INFO)
        changed = {'Dm_Kokiri_0130': self.flow('Dm_Kokiri_0130')}
        self.assertEqual(event_info.new_subflows(changed, self.flow), {})
        self.assertEqual(event_info.add_subflow_dependencies(info, [], {}, self.flow), (info, {}))

    def test_vanilla_lists_are_found_again(self):
        # The analysis gives back what the game lists for vanilla events (never more).
        from oot_rando.formats.inspect_resources import Byml
        from oot_rando.patching import event_info, qol_patches
        settings = Byml(self.raw(qol_patches.EVENT_SETTINGS)).root
        info = {r['__RowId']: r for r in Byml(self.raw(event_info.GAME_ANALYZED_EVENT_INFO)).root}
        owners = event_info.event_entries(settings, lambda flow: event_info.entry_names(self.flow(flow)))
        memo = {}
        self.assertIn(event_info.SWITCH_CALL, event_info.entry_calls(self.flow('Dm_SY_BancChange_EscapeDungeon'),
                                                                     'BossArea_WarpIn'))
        for row_id in ('Npc_SkullKid_Child_PlayOcarinaSequence',
                       'KokiriForest_WarpFromInsideTheDekuTree', 'Dm_Kokiri_0130', 'Dm_FairyFountain_Din'):
            flow, entry = owners[row_id]
            got = event_info.closure(event_info.entry_calls(self.flow(flow), entry), self.flow, memo) - {flow}
            got.discard(event_info.SWITCH_CALL[0])   # (message sub-flows: not followed, refused for new calls)
            self.assertLessEqual(got, set(info[row_id].get('SubFlowList') or []), row_id)   # (the game lists a few more)


if __name__ == '__main__':
    unittest.main()
