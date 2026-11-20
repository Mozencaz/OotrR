"""Big Poes to bring back: the collector's thresholds."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import big_poes

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(big_poes.thresholds(10), {'Event70': (900, 900), 'Event265': (400, 400)})
        self.assertEqual(big_poes.thresholds(3), {'Event70': (900, 200), 'Event265': (400, 100)})
        # One Big Poe: 0 points held already pass both comparisons.
        self.assertEqual(big_poes.thresholds(1), {'Event70': (900, 0), 'Event265': (400, -100)})
        for bad in (0, 11, '3', True):
            with self.assertRaises(ValueError):
                big_poes.thresholds(bad)


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    def test_patch(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.extra_sources import event_paths
        from oot_rando.game.world_maps import effective_members
        from oot_rando.patching.event_patch import _flow
        nup = Nup(NUP)
        try:
            d, m = dictionaries(nup), effective_members(nup)
            paths = event_paths(m, big_poes.FLOW)
            self.assertTrue(paths)
            for path in paths:
                raw = decompress(nup.read(m[path]), d)
                self.assertIs(big_poes.patch_flow(raw, 10), raw)
                events = {e.name: e for e in _flow(big_poes.patch_flow(raw, 4)).flowchart.events}
                self.assertEqual(events['Event70'].data.params.data['Value'], 300)
                self.assertEqual(events['Event265'].data.params.data['Value'], 200)
        finally:
            nup.stream.close()


if __name__ == '__main__':
    unittest.main()
