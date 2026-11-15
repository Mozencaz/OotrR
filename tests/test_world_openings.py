"""World openings (patching/world_openings.py). Needs OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import game_defaults, quest_guard, world_openings as w

NUP = os.environ.get('OOT_NUP')


class Option(unittest.TestCase):
    def test_open_fountain_is_offered(self):
        from oot_rando.logic import rando_options
        self.assertEqual(rando_options.validate({'zora_fountain': 'open'}, supported_only=True)['zora_fountain'],
                         'open')

    def test_open_fountain_logic(self):
        from collections import Counter
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        data = World()
        logic = Logic(data, {'open_forest': 'closed_deku', 'zora_fountain': 'open'})
        _, collected, _ = logic.sweep({'Deliver Rutos Letter': None, 'ZF Great Fairy Reward': None},
                                      logic.new_state(Counter({'Rutos Letter': 1, 'Ocarina': 1,
                                                               'Zeldas Lullaby': 1, 'Bomb Bag': 1,
                                                               'Progressive Scale': 1})))
        self.assertNotIn('Deliver Rutos Letter', collected)   # the letter is never a bottle


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class ZoraFountain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        nup = Nup(NUP)
        d = dictionaries(nup)
        cls.read = staticmethod(lambda path: decompress(nup.read(nup.latest('romfs/' + path)), d))

    def opened(self):
        return w.zora_fountain_open(self.read, self.read(game_defaults.GAMEDATA),
                                    self.read(quest_guard.CHALLENGES))

    def test_quest_starts_after_the_letter(self):
        gamedata, flows, report = self.opened()
        self.assertEqual(game_defaults.read_defaults(gamedata, [w.ZORA_STEP]), {w.ZORA_STEP: w.ZORA_FLOOR})
        self.assertEqual(report['expression'], 'Get_StoneOfWater_IsAfter_Step06_Exp')
        self.assertEqual(set(flows), set(w.ZORA_FLOWS))
        guarded = {step for path in w.ZORA_FLOWS for _, step, _ in report['guarded'][path]}
        self.assertIn('Step03', guarded)            # first arrival in Zora's Domain
        self.assertTrue({'Step05', 'Step06'} <= guarded)
        self.assertFalse(guarded & {'Step07', 'Step08', 'Step09', 'Step10', 'Step14'})

    def test_no_other_flow_requests_the_quest(self):
        # The two guarded flows are the only ones that move the Zora quest back.
        from oot_rando.formats.inspect_nup import Nup
        nup = Nup(NUP)
        steps = quest_guard.challenge_steps(self.read(quest_guard.CHALLENGES))
        order = steps[w.ZORA_QUEST]
        early = set(order[:order.index(w.ZORA_FLOOR)])
        paths = sorted({p.split('/', 2)[2] for p in nup.entries
                        if '/romfs/Event/EventFlow/' in p and p.endswith('.bfevfl.zs')})
        found = set()
        for path in paths:
            try:
                requests = quest_guard.step_requests(self.read(path), w.ZORA_QUEST)
            except (ValueError, AttributeError):
                continue    # empty or unreadable flow charts
            if any(step in early for _, step in requests):
                found.add(path)
        self.assertEqual(found, set(w.ZORA_FLOWS))


if __name__ == '__main__':
    unittest.main()
