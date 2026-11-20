import _src_path  # noqa: F401
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats.byml_writer import lift_actors, patch_strings
from oot_rando.formats.inspect_resources import Byml
import os

from oot_rando.game.item_forms import (GROUND_LIFT, LIFT_MARGIN, MAX_WORLD_SCALE, MODEL_BOTTOM, SMALL_MODELS, WORLD_SIZE,
                                       ground_lift, lifted, world_scale)


def _map():
    actors = [{'Gyaml': 'Obj_Heart_Piece', 'Hash': 1, 'Translate': [1.0, 2.5, 3.0]},
              {'Gyaml': 'Obj_Rupee_Red', 'Hash': 2, 'Translate': [4.0, 5.0, 6.0]}]
    return byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': actors}})


class GroundLiftTests(unittest.TestCase):
    def test_token_on_a_ground_spot_is_lifted(self):
        self.assertGreater(ground_lift('Obj_Heart_Piece', 'Obj_Token_Gold'), 0)
        self.assertEqual(ground_lift('Obj_Token_Gold', 'Obj_Token_Gold'), 0)
        self.assertEqual(ground_lift('Obj_Rupee_Red', 'Obj_Heart_Piece'), 0)

    def test_lift_after_string_edit_moves_only_that_actor(self):
        height = GROUND_LIFT['Obj_Token_Gold']
        raw = patch_strings(_map(), [{'path': ('Actors', 0, 'Gyaml'), 'before': 'Obj_Heart_Piece',
                                      'after': 'Obj_Token_Gold'}])
        actors = Byml(lift_actors(raw, {0: height})).root['Actors']
        self.assertEqual(actors[0]['Gyaml'], 'Obj_Token_Gold')
        self.assertEqual(actors[0]['Translate'], [1.0, lifted(2.5, height), 3.0])
        self.assertEqual(actors[1]['Translate'], [4.0, 5.0, 6.0])

    def test_no_height_keeps_bytes(self):
        raw = _map()
        self.assertIs(lift_actors(raw, {}), raw)
        self.assertIs(lift_actors(raw, {0: 0.0}), raw)


class WorldScaleTests(unittest.TestCase):
    def test_small_key_items_are_scaled_up_to_the_token_size(self):
        self.assertEqual(world_scale('Obj_Rando_Item_Gauntlet_Goron'), MAX_WORLD_SCALE)
        self.assertAlmostEqual(world_scale('Obj_Rando_Item_Range_SlingShot'), 1.16)
        # Progressive tokens are drawn with their family's first level.
        self.assertEqual(world_scale('Obj_Rando_Item_Prog_Strength_1'), MAX_WORLD_SCALE)
        self.assertAlmostEqual(world_scale('Obj_Rando_Item_Prog_Slingshot_2'), 1.16)
        self.assertEqual(world_scale('Obj_Rando_Item_Prog_Hookshot_1'), 1.0)
        for actor in ('Obj_Rando_Item_Hookshot', 'Obj_Token_Gold', 'Obj_Heart_Piece',
                      'Item_Gauntlet_Goron', 'Obj_RandoDrop_Item_Gauntlet_Goron'):
            self.assertEqual(world_scale(actor), 1.0, actor)

    def test_derived_pickup_lifted_by_its_model_bottom(self):
        self.assertAlmostEqual(ground_lift('Obj_Heart_Piece', 'Obj_Rando_Item_Hookshot'), 0.152 + LIFT_MARGIN)
        self.assertAlmostEqual(ground_lift('Obj_Rupee_Red', 'Obj_Rando_Item_Arrow_Light'), 0.377 + LIFT_MARGIN)
        self.assertAlmostEqual(ground_lift('Obj_Heart_Piece', 'Obj_Rando_Item_Prog_Hookshot_1'), 0.152 + LIFT_MARGIN)
        self.assertAlmostEqual(ground_lift('Obj_Heart_Piece', 'Obj_Rando_Item_AP_Medal'), 0.183 + LIFT_MARGIN)
        self.assertEqual(ground_lift('Obj_Heart_Piece', 'Obj_Rando_Item_Stone_Forest'), 0.0)
        self.assertEqual(ground_lift('Obj_Rando_Item_Hookshot', 'Obj_Rando_Item_Hookshot'), 0.0)
        self.assertEqual(ground_lift('Obj_Heart_Piece', 'Obj_RandoDrop_Item_Hookshot'), 0.0)

    def test_scaled_model_lifted_by_its_scaled_bottom(self):
        scale = world_scale('Obj_Rando_Item_Range_SlingShot')
        self.assertAlmostEqual(ground_lift('Obj_Heart_Piece', 'Obj_Rando_Item_Range_SlingShot'),
                               0.09 * scale + LIFT_MARGIN, places=3)

    def test_scale_added_as_a_new_float_array(self):
        raw = patch_strings(_map(), [
            {'path': ('Actors', 0, 'Gyaml'), 'before': 'Obj_Heart_Piece', 'after': 'Obj_Rando_Item_AgonyStone'},
            {'path': ('Actors', 0, 'Scale'), 'before': None, 'after': (3.0, 3.0, 3.0)}])
        actors = Byml(lift_actors(raw, {0: 0.1})).root['Actors']
        self.assertEqual(actors[0]['Scale'], [3.0, 3.0, 3.0])
        self.assertEqual(actors[0]['Translate'], [1.0, lifted(2.5, 0.1), 3.0])
        self.assertNotIn('Scale', actors[1])
        self.assertEqual(actors[1]['Gyaml'], 'Obj_Rupee_Red')

    def test_float_array_only_as_a_new_leaf(self):
        for change in ({'path': ('Actors', 0, 'Scale'), 'before': 'x', 'after': (1.0,)},
                       {'path': ('Actors', 0, 'Scale'), 'before': None, 'after': ()},
                       {'path': ('Actors', 0, 'Scale'), 'before': None, 'after': ('a',)}):
            with self.assertRaises(ValueError):
                patch_strings(_map(), [change])

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_small_models_match_the_game(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        nup = Nup(os.environ['OOT_NUP'])
        raw = decompress(nup.read(nup.latest('romfs/RSDB/ActorInfo.Product.111.rstbl.byml.zs')), dictionaries(nup))
        rows = {row['__RowId']: row for row in byml_codec.load(raw)['root']}
        for actor, extent in SMALL_MODELS.items():
            low, high = rows[actor]['ModelAabbMin'], rows[actor]['ModelAabbMax']
            self.assertAlmostEqual(max(high[k] - low[k] for k in 'XYZ'), extent, delta=0.002, msg=actor)
            self.assertLess(extent, WORLD_SIZE)
        # Rando-built actors take their ActorInfo model box from a native weapon.
        from oot_rando.patching.master_sword_item import MASTER_SWORD_ACTOR, WEAPON
        derived = {MASTER_SWORD_ACTOR: WEAPON}
        for actor, bottom in MODEL_BOTTOM.items():
            row = rows[derived.get(actor, actor)]
            self.assertAlmostEqual(row['ModelAabbMin']['Y'], bottom, delta=0.002, msg=actor)
        for actor, row in rows.items():
            low = (row.get('ModelAabbMin') or {}).get('Y', 0.0)
            if actor.startswith(('Item_', 'TBox_')) and -1 < low < -0.02 and not actor.endswith(
                    ('_ImportantMenu', '_Holder')) and actor not in ('Item_Token_Gold', 'Item_OrnamentalBottle_Milk',
                                                                    'Item_Hat_FishingPondOwner'):
                self.assertIn(actor, MODEL_BOTTOM)


if __name__ == '__main__':
    unittest.main()
