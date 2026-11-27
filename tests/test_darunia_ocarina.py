"""Replay Darunia's ocarina dispatch before/after opening Dodongo's Cavern."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.patching import story_fixes as s
from oot_rando.formats.evfl_tools import params_by_event, parse_flow


def ocarina_route(raw, after_saria, given):
    chart = parse_flow(raw).flowchart
    event = next(e for e in chart.entry_points if e.name == 'Get_StoneOfFire_PlayOcarina').main_event.v
    for _ in range(20):
        if event.name in ('Event193', 'Event278'):
            return event.name
        data = event.data
        if type(data).__name__ == 'SwitchEvent':
            flag = data.params.data['GameDataName']
            value = {s.AFTER_SARIA_PLAY: after_saria, s.DARUNIA_GIFT_PLAYED: given}[flag]
            event = data.cases[0 if value else 1].v
        else:
            event = data.nxt.v
    raise AssertionError('Ocarina dispatch did not reach a prompt')


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class DaruniaOcarina(unittest.TestCase):
    def test_pending_gift_uses_full_ocarina_prompt_after_cavern_opens(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        nup = Nup(os.environ['OOT_NUP'])
        self.addCleanup(nup.stream.close)
        source = decompress(nup.read(nup.latest('romfs/' + s.FIRE_STONE_FLOW)), dictionaries(nup))
        raw, _ = s.darunia_gift_after_dungeon(source)
        for after_saria in (False, True):
            for given in (False, True):
                with self.subTest(after_saria=after_saria, given=given):
                    expected = 'Event278' if after_saria and given else 'Event193'
                    self.assertEqual(ocarina_route(raw, after_saria, given), expected)
        before, after = params_by_event(parse_flow(source)), params_by_event(parse_flow(raw))
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)
        events = {e.name: e for e in parse_flow(source).flowchart.events}
        self.assertEqual(set(events['Event115'].data.cases) - set(events['Event159'].data.cases),
                         {6, 7, 8, 9, 10, 11})
