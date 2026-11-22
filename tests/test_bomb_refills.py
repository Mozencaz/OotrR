"""No refill source may implicitly grant the bomb bag (real packs with OOT_NUP)."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching import bomb_refills as b


def document(root):
    return byml_codec.dump({'endian': '<', 'version': 7, 'root': root})


class PatchTests(unittest.TestCase):
    def test_only_automatic_bag_reference_changes(self):
        files = {path: document({'SmallBagActor': b.BAG_ACTOR, 'EnableStock': True,
                                'MaxNumGameData': 'Bomb', 'BundleActorNum': 5})
                 for path in b.POUCH_PATHS}
        files['unrelated'] = b'keep me'
        raw = byml_codec.build_sarc(files)
        patched, changed = b.patch_pack(raw)
        self.assertEqual(changed, list(b.POUCH_PATHS))
        actual = sarc(patched)
        self.assertEqual(actual['unrelated'], files['unrelated'])
        for path in b.POUCH_PATHS:
            expected = byml_codec.load(files[path])
            expected['root']['SmallBagActor'] = ''
            self.assertEqual(byml_codec.load(actual[path]), expected)
        self.assertEqual(b.patch_pack(patched), (patched, []))

    def test_unrelated_items_and_actual_bag_are_untouched(self):
        path = 'Component/PouchContentParam/Item_BombBag_Small.game__component__PouchContentParam.bgyml'
        raw = byml_codec.build_sarc({path: document({'GetType': 1})})
        self.assertEqual(b.patch_pack(raw), (raw, []))


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class GamePacks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.d = dictionaries(cls.nup)
        cls.members = effective_members(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        return self.decompress(self.nup.read(self.members[path]), self.d)

    def pack(self, actor):
        return sarc(self.read(f'Pack/Actor/{actor}.pack.zs'))

    def test_all_native_copies_are_covered_and_preserve_other_parameters(self):
        found = set()
        for path in self.members:
            if not path.startswith('Pack/Actor/'):
                continue
            raw = self.read(path)
            if b'SmallBagActor' not in raw:
                continue
            before = sarc(raw)
            # Search every pouch, not just the two known component paths.
            bag_refs = [p for p, v in before.items() if 'PouchContentParam/' in p
                        and b'SmallBagActor' in v
                        and byml_codec.load(v)['root'].get('SmallBagActor') == b.BAG_ACTOR]
            if not bag_refs:
                continue
            found.add(path)
            patched, changed = b.patch_pack(raw)
            self.assertEqual(set(changed), set(bag_refs), path)
            after = sarc(patched)
            self.assertEqual(set(before), set(after))
            for member in before:
                if member in bag_refs:
                    expected = byml_codec.load(before[member])
                    expected['root']['SmallBagActor'] = ''
                    self.assertEqual(byml_codec.load(after[member]), expected, (path, member))
                else:
                    self.assertEqual(before[member], after[member], (path, member))
        self.assertEqual(found, set(b.NATIVE_PACKS))

    def test_native_and_generated_sources_are_composed(self):
        from oot_rando.game.item_forms import build_pack
        from oot_rando.patching.qol_patches import free_bomb_lift, BOMB_LIFT_PACKS
        # Chest/NPC/AP bundles resolve Item_Bomb; world/drop/shop copies can
        # embed its pouch data, just as bombchu refills embed Item_Bombchu.
        generated = {}
        for actor in ('Item_BombBundle_Small', 'Item_BombchuBundle_Small', 'Item_Bomb', 'Item_Bombchu'):
            for prefix in ('Obj_Rando_', 'Obj_RandoDrop_', 'Obj_RandoWater_',
                           'Obj_RandoWaterDrop_', 'Shop_Rando_'):
                derived = prefix + actor
                generated[f'Pack/Actor/{derived}.pack.zs'] = build_pack(derived, self.pack, byml_codec)
        existing = {path: free_bomb_lift(self.read(path))[0] for path in BOMB_LIFT_PACKS}
        lifted = {path: sarc(raw) for path, raw in existing.items()}
        originals = dict(generated)
        records = b.apply(existing, generated, self.read)
        self.assertTrue(set(b.NATIVE_PACKS) <= set(records))
        for path, (raw, template) in generated.items():
            expected, _ = b.patch_pack(originals[path][0])
            self.assertEqual(raw, expected)
            self.assertEqual(template, originals[path][1])
        for path, before in lifted.items():
            for member, value in before.items():
                if member not in b.POUCH_PATHS:
                    self.assertEqual(sarc(existing[path])[member], value)
        for raw in list(existing.values()) + [r[0] for r in generated.values()]:
            self.assertEqual(b.patch_pack(raw), (raw, []))
        for actor in ('Item_BombBag_Small', 'Item_BombBag_Medium', 'Item_BombBag_Large'):
            raw = self.read(f'Pack/Actor/{actor}.pack.zs')
            self.assertEqual(b.patch_pack(raw), (raw, []))


if __name__ == '__main__':
    unittest.main()
