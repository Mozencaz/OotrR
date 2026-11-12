"""Collection markers added to event flows. NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS, POUCH_ACTOR_PARAMS, _flow, add_collection_markers, add_pouch_items

NUP = os.environ.get('OOT_NUP')
OPENING = 'Event/EventFlow/OpeningEvent.bfevfl.zs'


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class CollectionMarkerTests(unittest.TestCase):
    def test_added_gamedata_actor_has_native_parameters(self):
        # Regression: a GameDataActor without its parameter container crashed the
        # game at the end of the new-game intro (null read in the event system).
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        nup = Nup(NUP)
        dic = dictionaries(nup)
        member = next(p + '/romfs/' + OPENING for p in '10' if p + '/romfs/' + OPENING in nup.entries)
        raw = decompress(nup.read(member), dic)
        self.assertFalse([a for a in _flow(raw).flowchart.actors if str(a.identifier) == 'GameDataActor'])
        patched, records = add_collection_markers(raw, {'Event3': 'RandoSeed.test'})
        actors = _flow(patched).flowchart.actors
        added = [a for a in actors if str(a.identifier) == 'GameDataActor']
        self.assertEqual(len(added), 1)
        self.assertEqual(dict(added[0].params.data), GAMEDATA_ACTOR_PARAMS)
        self.assertFalse([str(a.identifier) for a in actors if a.params is None])
        self.assertEqual(records, [{'event': 'Event3', 'marker': 'RandoCollected_Event3', 'flag': 'RandoSeed.test'}])


    def test_starting_items_follow_the_seed_marker(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        nup = Nup(NUP)
        member = next(p + '/romfs/' + OPENING for p in '10' if p + '/romfs/' + OPENING in nup.entries)
        raw = decompress(nup.read(member), dictionaries(nup))
        marked, _ = add_collection_markers(raw, {'Event3': 'RandoSeed.test'})
        original_next = {e.name: e for e in _flow(marked).flowchart.events}['RandoCollected_Event3'].data.nxt.v.name
        patched = add_pouch_items(marked, 'RandoCollected_Event3', ('Item_BulletBag_Small', 'Item_Quiver_Small'))
        chart = _flow(patched).flowchart
        events = {e.name: e for e in chart.events}
        chain, event = [], events['RandoCollected_Event3']
        for _ in range(3):
            event = event.data.nxt.v
            chain.append(event.name)
        self.assertEqual(chain, ['RandoStartItem_Item_BulletBag_Small', 'RandoStartItem_Item_Quiver_Small', original_next])
        self.assertEqual(events['RandoStartItem_Item_Quiver_Small'].data.params.data['Actor'], 'Item_Quiver_Small')
        pouch = [a for a in chart.actors if str(a.identifier) == 'PouchSystemActor']
        self.assertEqual(len(pouch), 1)
        self.assertEqual(dict(pouch[0].params.data), POUCH_ACTOR_PARAMS)

if __name__ == '__main__':
    unittest.main()
