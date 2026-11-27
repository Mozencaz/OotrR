"""Fire Arrows (LH Sun): the sun-shot cutscene follows the shuffled pickup (needs OOT_NUP)."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import fire_arrows
from oot_rando.formats.evfl_tools import parse_flow

NUP = os.environ.get('OOT_NUP')


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        try:
            members, d = effective_members(nup), dictionaries(nup)
            cls.raw = decompress(nup.read(members[fire_arrows.CUTSCENE_FLOW]), d)
        finally:
            nup.stream.close()

    def test_cutscene_binds_the_new_pickup(self):
        result = fire_arrows.retarget_cutscene(self.raw, 'Obj_Rando_Item_Hookshot')
        actors = {(a.identifier.name, a.identifier.sub_name) for a in parse_flow(result).flowchart.actors}
        self.assertIn(('Obj_Rando_Item_Hookshot', 'Item'), actors)
        self.assertNotIn(('Obj_Arrow_Fire', 'Item'), actors)
        with self.assertRaises(ValueError):
            fire_arrows.retarget_cutscene(result, 'Obj_Rando_Item_Hookshot')

    def test_vanilla_item_keeps_the_flow(self):
        self.assertIs(fire_arrows.retarget_cutscene(self.raw, 'Obj_Arrow_Fire'), self.raw)


if __name__ == '__main__':
    unittest.main()
