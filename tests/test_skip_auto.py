"""+ skip windows taken on their own (patching/skip_auto.py)."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import skip_auto

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_option_off_changes_nothing(self):
        self.assertEqual(skip_auto.flows(False, {'Dm_Kokiri_0045': []}), ())
        self.assertEqual(skip_auto.flows(None), ())
        self.assertEqual(skip_auto.flows(True), skip_auto.NATIVE_FLOWS)
        self.assertIn('Dm_Kokiri_0045', skip_auto.flows(True, {'Dm_Kokiri_0045': []}))

    def test_option_is_declared(self):
        from oot_rando.logic import rando_options
        option = next(o for o in rando_options.OPTIONS if o.name == 'auto_skip_cutscenes')
        self.assertIs(option.default, False)


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class GameFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        d, members = dictionaries(nup), effective_members(nup)
        cls.read = staticmethod(lambda path: decompress(nup.read(members[path]), d) if path in members else None)
        cls.names = sorted(p[len(skip_auto.FLOWS):-len('.bfevfl.zs')] for p in members
                           if p.startswith(skip_auto.FLOWS) and p.endswith('.bfevfl.zs'))

    def test_native_table_matches_the_scan(self):
        ok, kept = skip_auto.scan(self.read, self.names)
        self.assertEqual(ok, skip_auto.NATIVE_FLOWS)
        self.assertEqual(sorted(kept), ['Dm_FairyFountain_Din', 'Dm_WaterTemple_0020', 'Dm_WaterTemple_0021',
                                        'Dm_WaterTemple_0022'])

    def test_fountain_goes_to_the_skipped_path(self):
        from oot_rando.patching.event_patch import _flow
        name = 'Dm_FairyFountain_Courage'
        vanilla = self.read(skip_auto.flow_path(name))
        out, report = skip_auto.take_windows(vanilla, name)
        self.assertEqual(report, [{'start': 'Event0', 'end': 'Event22', 'to': 'Event46', 'fade': False,
                                   'loading_wait': False}])
        self.assertTrue(skip_auto.taken(out))
        self.assertFalse(skip_auto.taken(vanilla))
        chart = _flow(out).flowchart
        reached = {e.name for e in skip_auto._reach(chart, skip_auto._roots(chart))}
        # the gift (item get) and the end of the scene still run; the appearance does not
        self.assertTrue({'Event144', 'Event126', 'Event135', 'Event29'} <= reached)
        self.assertNotIn('Event28', reached)
        with self.assertRaises(ValueError):
            skip_auto.take_windows(out, name)

    def test_every_randomizer_window_is_taken(self):
        from oot_rando.patching.event_info import new_subflows
        from oot_rando.patching.qol_patches import EVENT_SETTINGS, cutscene_window_files, skip_window_candidates
        files, windows = cutscene_window_files(self.read, set(self.names),
                                               skip_window_candidates(self.read(EVENT_SETTINGS)))
        total = 0
        for path, raw in sorted(files.items()):
            name = path[len(skip_auto.FLOWS):-len('.bfevfl.zs')]
            with self.subTest(name):
                out, report = skip_auto.take_windows(raw, name)
                self.assertTrue(skip_auto.taken(out))
                self.assertEqual(len([r for r in report if 'start' in r]), len(windows[name]))
                self.assertFalse(new_subflows({name: out}, lambda n: self.read(skip_auto.flow_path(n))))
                total += len(windows[name])
        self.assertEqual((len(files), total), (65, 99))


if __name__ == '__main__':
    unittest.main()
