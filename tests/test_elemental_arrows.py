"""Normal bows and elemental arrows have separate equipment identities."""
import _src_path  # noqa: F401
import os
import unittest
from collections import Counter

from oot_rando.formats import byml_codec as b
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching import elemental_arrows as a
from oot_rando.patching.soul_adapter import murmur3


class LogicTests(unittest.TestCase):
    def test_menu_restores_selection_after_the_previous_patch(self):
        # A standalone arrow is the native selectable entry; marking it unusable
        # prevents selection even with the bow and magic already acquired.
        for usable in (False, True):
            before = {'root': {'ItemArray': [{'Actor': [
                {'ActorShort': 'Item_Arrow_' + element, 'IsUsableAdult': usable,
                 'IsUsableChild': False}
                for element in a.ELEMENTS
            ]}]}, 'version': 7, 'endian': '<'}
            raw = b.dump(before)
            patched = a.patch_ui(raw)
            after = b.load(patched)
            for row in before['root']['ItemArray'][0]['Actor']:
                row['IsUsableAdult'] = True
            self.assertEqual(after, before)
            self.assertEqual(a.patch_ui(patched), patched)

    def test_elemental_arrows_need_bow_and_magic(self):
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        logic = Logic(World(), {'blue_fire_arrows': True})
        for element in a.ELEMENTS:
            rule = logic.compile(f'can_use({element}_Arrows)')
            for bow in (0, 1, 2, 3):
                for magic in (0, 1):
                    for age in ('child', 'adult'):
                        counts = Counter({element + ' Arrows': 1, 'Bow': bow, 'Magic Meter': magic})
                        state = logic.new_state(counts)
                        self.assertEqual(bool(rule(state, state.counts, age)),
                                         bool(bow and magic and age == 'adult'))

    def test_ice_arrows_are_separate_from_progressive_bow(self):
        from oot_rando.game.remake_world import ACTOR_ITEMS, PROGRESSIVE, item_actor
        self.assertEqual(ACTOR_ITEMS['Item_Arrow_Ice'], 'Ice Arrows')
        self.assertEqual(item_actor('Ice Arrows', 'GerudoTrainingGround'), 'Item_Arrow_Ice')
        self.assertNotIn('Item_Arrow_Ice', PROGRESSIVE['Bow'])


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        raw = self.nup.read(self.nup.latest('romfs/' + path))
        return self.decompress(raw, self.d) if path.endswith('.zs') else raw

    def test_normal_bow_overrides_ice_identity_without_changing_ice(self):
        original = self.read(a.PACK)
        before, after = sarc(original), sarc(a.patch_pack(original))
        table = b.load(after[a.GAME_TABLE])['root']
        param = b.load(after[table['Components']['AssignableItemParam'][1:]])['root']
        self.assertEqual(param['AssignableItem'], murmur3('Bow'))
        for path, raw in before.items():
            if path != a.GAME_TABLE:
                self.assertEqual(after[path], raw, path)
        # Only native resources: the private file of the old patch crashed the inventory.
        self.assertEqual(set(after), set(before) | {a.PARAM})
        native = sarc(self.read('Pack/Actor/Weapon_Range_Bow.pack.zs'))[a.PARAM]
        self.assertEqual(b.load(after[a.PARAM]), b.load(native))
        old = dict(before)
        old[a.OLD_PARAM] = b'stale'
        self.assertEqual(a.patch_pack(b.build_sarc(old)), a.patch_pack(original))
        raw = self.read(a.TABLE)
        before, after = b.load(raw)['root'], b.load(a.patch_table(raw))['root']
        for old, new in zip(before, after):
            expected = dict(old)
            if old['__RowId'] == a.ACTOR:
                self.assertEqual(old['AssignableItem'], 'IceArrow')  # native regression
                expected['AssignableItem'] = 'Bow'
            self.assertEqual(new, expected)

    def test_native_arrow_selection_is_preserved(self):
        before = b.load(self.read(a.UI))
        after = b.load(a.patch_ui(self.read(a.UI)))
        for slot in before['root']['ItemArray']:
            for row in slot['Actor']:
                if row['ActorShort'] in ['Item_Arrow_' + e for e in a.ELEMENTS]:
                    self.assertTrue(row['IsUsableAdult'])
                if row['ActorShort'].startswith('Pouch_Range_BowAndArrow_'):
                    self.assertTrue(row['IsUsableAdult'])
        self.assertEqual(after, before)
        for path, fix in a.resource_fixes():
            patched = fix(self.read(path))
            self.assertEqual(fix(patched), patched, path)


if __name__ == '__main__':
    unittest.main()
