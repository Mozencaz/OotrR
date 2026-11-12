import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.formats import byml_codec
from oot_rando.patching.qol_patches import KOKIRI_SHOP_FLAG, open_kokiri_shop, release_kokiri_shop_goods
from oot_rando.formats.inspect_resources import sarc


def presence(negation):
    return {'FlagName': KOKIRI_SHOP_FLAG, 'IsCheckLazy': True, 'IsNegation': negation}


class KokiriShopTests(unittest.TestCase):
    def test_full_stock_always_present_and_short_stock_hidden(self):
        actors = [
            {'Gyaml': 'Npc_Kokiri_001_Shop_Child', 'Presence': presence(False)},
            {'Gyaml': 'Shop_DekuStick', 'Presence': presence(False)},
            {'Gyaml': 'Npc_Kokiri_001_Shop_Child_ShortStock', 'Presence': presence(True)},
            {'Gyaml': 'Shop_Board_SoldOut', 'Presence': presence(True)},
            {'Gyaml': 'Npc_Mido', 'Presence': presence(True)},  # not part of the shop
        ]
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': actors}})
        patched, count = open_kokiri_shop(raw, 'RandoSeed.test')
        self.assertEqual(count, 4)
        result = byml_codec.load(patched)['root']['Actors']
        self.assertNotIn('Presence', result[0])
        self.assertNotIn('Presence', result[1])
        for actor in result[2:4]:
            self.assertEqual(actor['Presence'], {'FlagName': 'RandoSeed.test', 'IsCheckLazy': True,
                                                 'IsNegation': True})
        self.assertEqual(result[4]['Presence'], presence(True))

    def test_map_without_shop_is_untouched(self):
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': [{'Gyaml': 'Obj_Tree'}]}})
        self.assertEqual(open_kokiri_shop(raw, 'RandoSeed.test'), (raw, 0))


    def test_shop_goods_are_released_from_the_deku_tree_condition(self):
        gated = {'Actor': 'Work/Actor/Shop_Heart.engine__actor__ActorParam.gyml', 'StockNum': -1,
                 'Release': {'IsCheckReleaseGameData': True, 'ReleaseGameData': KOKIRI_SHOP_FLAG}}
        other = {'Actor': 'Work/Actor/Shop_Mask_Bunny.engine__actor__ActorParam.gyml',
                 'Release': {'IsCheckReleaseGameData': True, 'ReleaseGameData': 'HappyMaskShop_HasMask_Bunny'}}
        free = {'Actor': 'Work/Actor/Shop_DekuStick.engine__actor__ActorParam.gyml', 'StockNum': -1}
        param = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'GoodsList': [gated, other, free]}})
        untouched = b'model bytes'
        pack = byml_codec.build_sarc({'Component/ShopParam/Kokiri.game__component__ShopParam.bgyml': param,
                                      'Component/ModelInfo/X.bgyml': untouched})
        patched, count = release_kokiri_shop_goods(pack)
        self.assertEqual(count, 1)
        files = sarc(patched)
        self.assertEqual(files['Component/ModelInfo/X.bgyml'], untouched)
        goods = byml_codec.load(files['Component/ShopParam/Kokiri.game__component__ShopParam.bgyml'])['root']['GoodsList']
        self.assertEqual(goods[0]['Release'], {'IsCheckReleaseGameData': False, 'ReleaseGameData': ''})
        self.assertEqual(goods[1]['Release'], other['Release'])
        self.assertNotIn('Release', goods[2])

if __name__ == '__main__':
    unittest.main()
