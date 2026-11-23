"""NPC lines without a choice taken out (patching/npc_dialogue_skip.py)."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import npc_dialogue_skip as skip

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_option_off_changes_nothing(self):
        self.assertEqual(skip.zone_flows(False), ())
        self.assertEqual(skip.zone_flows(None), ())
        self.assertIn('Npc_Kokiri_Mido_Child', skip.zone_flows(True))

    def test_white_list_has_no_shop_nor_cutscene(self):
        for name in skip.zone_flows(True):
            self.assertTrue(name.startswith('Npc_'), name)
            self.assertNotIn('Shop', name)

    def test_option_is_declared(self):
        from oot_rando.logic import rando_options
        option = next(o for o in rando_options.OPTIONS if o.name == 'skip_npc_dialogues')
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

    def test_every_listed_flow_is_muted(self):
        ok, kept = skip.scan(self.read, skip.zone_flows(True))
        self.assertEqual(kept, {})
        self.assertEqual(set(ok), set(skip.zone_flows(True)))
        self.assertEqual(sum(len(r['talks']) for r in ok.values()), 949)

    def test_lines_after_a_choice_stay(self):
        from oot_rando.patching.event_patch import _flow
        from oot_rando.patching.skip_auto import _roots
        name = 'Npc_Kokiri_008_Child'
        vanilla = self.read(skip.flow_path(name))
        out, report = skip.mute(vanilla, name)
        self.assertTrue(skip.muted(out))
        self.assertFalse(skip.muted(vanilla))
        chart = _flow(out).flowchart
        reached = {e.name for e in skip._reach(chart, _roots(chart))}
        # the question about the shield (choice) and its answer stay; the greeting goes
        self.assertTrue({'Event122', 'Event93'} <= reached)
        self.assertNotIn('Event5', reached)
        self.assertIn('Event5', report['talks'])
        with self.assertRaises(ValueError):
            skip.mute(out, name)

    def test_item_get_still_runs(self):
        from evfl.event import SubFlowEvent
        from oot_rando.patching.event_patch import _flow
        from oot_rando.patching.skip_auto import _roots
        name = 'Npc_Kokiri_005_Child'
        vanilla = self.read(skip.flow_path(name))
        out, _ = skip.mute(vanilla, name)
        for raw in (vanilla, out):
            chart = _flow(raw).flowchart
            gets = [e for e in skip._reach(chart, _roots(chart))
                    if isinstance(e.data, SubFlowEvent) and e.data.res_flowchart_name == 'Dm_SY_GetInEvent']
            self.assertTrue(gets)

    def test_choice_count_from_an_argument_is_a_choice(self):
        from oot_rando.patching.event_patch import _flow
        chart = _flow(self.read(skip.flow_path('Npc_Kokiri_008_Child'))).flowchart
        event = next(e for e in chart.events if e.name == 'Event40')
        self.assertEqual(skip._params(event)['ChoiceNumber'], 'ChoiceNumber')
        self.assertTrue(skip._offers_choice(event))


if __name__ == '__main__':
    unittest.main()
