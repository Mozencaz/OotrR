"""Full bottles (Ruto's Letter...) on a shelf are bought without an empty bottle."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import shop_bottles
from oot_rando.formats.evfl_tools import parse_flow

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_full_bottles_are_the_ones_the_randomizer_places(self):
        from oot_rando.game.remake_world import ACTOR_ITEMS
        bottles = {actor for actor in ACTOR_ITEMS if actor.startswith('Item_Bottle')}
        self.assertEqual(bottles, set(shop_bottles.FULL_BOTTLES))


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    def setUp(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        self.addCleanup(nup.stream.close)
        members = effective_members(nup)
        self.raw = decompress(nup.read(members[shop_bottles.DISPLAY_SHOP_FLOW]), dictionaries(nup))

    def test_full_bottles_take_the_plain_item_branches(self):
        raw, report = shop_bottles.patch_display_shop(self.raw)
        events = {e.name: e for e in parse_flow(raw).flowchart.events}
        for name, (plain, contents) in shop_bottles.BRANCHES.items():
            with self.subTest(switch=name):
                guard = events[name].data.cases[shop_bottles.BOTTLE_CATEGORY].v
                seen = []
                while guard.name.startswith(shop_bottles.PREFIX):
                    seen.append(guard.data.params.data['Value'])
                    self.assertEqual(guard.data.params.data['GameDataName'], 'Shop_SelectItemName')
                    self.assertEqual(guard.data.cases[0].v.name, plain)
                    guard = guard.data.cases[1].v
                self.assertEqual(seen, list(shop_bottles.FULL_BOTTLES))
                # Native bottle contents (fish, potions...) still need an empty bottle.
                self.assertEqual(guard.name, contents)
                # Other categories untouched.
                original = {e.name: e for e in parse_flow(self.raw).flowchart.events}[name]
                for key, case in original.data.cases.items():
                    if key != shop_bottles.BOTTLE_CATEGORY:
                        self.assertEqual(events[name].data.cases[key].v.name, case.v.name)
        self.assertEqual(set(report), set(shop_bottles.BRANCHES))

    def test_applied_once(self):
        raw, _ = shop_bottles.patch_display_shop(self.raw)
        with self.assertRaises(ValueError):
            shop_bottles.patch_display_shop(raw)


if __name__ == '__main__':
    unittest.main()
