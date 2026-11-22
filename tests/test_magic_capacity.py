"""Magic-using items cannot grant a meter; actual upgrades retain their effects."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.formats import byml_codec as byml
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching import magic_capacity as m


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class GameTests(unittest.TestCase):
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

    def test_exhaustive_native_pack_coverage_and_preservation(self):
        found = set()
        for path in self.members:
            if not path.startswith('Pack/Actor/'):
                continue
            raw = self.read(path)
            if b'ExpansionAbilityActor' not in raw:
                continue
            before = sarc(raw)
            targets = []
            for member, value in before.items():
                if member.startswith('GameParameter/GameParameterTable/'):
                    root = byml.load(value)['root']
                    if (root.get('Components', {}).get('ExpansionAbilityActor') == m.MAGIC_REF
                            and '/Item_FairyBless_MP.engine' not in member):
                        targets.append(member)
            patched, changed = m.patch_pack(raw)
            self.assertEqual(set(changed), set(targets), path)
            if not targets:
                self.assertEqual(patched, raw)
                continue
            found.add(path)
            after = sarc(patched)
            self.assertEqual(set(after), set(before))
            for member, value in before.items():
                if member in targets:
                    expected = byml.load(value)
                    del expected['root']['Components']['ExpansionAbilityActor']
                    self.assertEqual(byml.load(after[member]), expected)
                else:
                    self.assertEqual(after[member], value)
            self.assertEqual(m.patch_pack(patched), (patched, []))
        self.assertEqual(found, set(m.NATIVE_PACKS))

    def test_pouch_effects_before_and_after_meter_upgrades(self):
        raw = self.read(m.TABLE)
        before = byml.load(raw)['root']
        patched = m.patch_table(raw)
        after = byml.load(patched)['root']
        self.assertEqual(m.patch_table(patched), patched)
        affected = set()
        for old, new in zip(before, after):
            expected = dict(old)
            if (old.get('ExpansionAvility') == 'MPMaxUP'
                    and old.get('PouchSpecialDeal') not in ('FairyBlessMP', 'FairyBlessMPDouble')):
                affected.add(old['__RowId'])
                self.assertEqual(old['MPMax'], 24)  # native regression evidence
                expected['ExpansionAvility'] = 'None'
                del expected['MPMax']
                # Receiving the item must preserve zero, single and double magic.
                for capacity in (0, 24, 48):
                    result = new.get('MPMax', capacity) if new['ExpansionAvility'] == 'MPMaxUP' else capacity
                    self.assertEqual(result, capacity)
            self.assertEqual(new, expected)
        self.assertTrue(set(m.ITEMS) <= affected)
        for actor, capacity in (('Item_FairyBless_MP', 24), ('Item_FairyBless_MPDouble', 48)):
            row = next(r for r in after if r['__RowId'] == actor)
            self.assertEqual((row['ExpansionAvility'], row['MPMax']), ('MPMaxUP', capacity))
            raw = self.read(f'Pack/Actor/{actor}.pack.zs')
            self.assertEqual(m.patch_pack(raw), (raw, []))

    def test_generated_sources_and_normal_bow_changes_are_composed(self):
        from oot_rando.game.item_forms import build_pack
        from oot_rando.patching import elemental_arrows
        generated = {}
        for actor in m.ITEMS:
            for prefix in ('Obj_Rando_', 'Obj_RandoDrop_', 'Obj_RandoWater_',
                           'Obj_RandoWaterDrop_', 'Shop_Rando_'):
                derived = prefix + actor
                generated[f'Pack/Actor/{derived}.pack.zs'] = build_pack(derived, self.pack, byml)
        originals = dict(generated)
        existing = {elemental_arrows.PACK: elemental_arrows.patch_pack(self.read(elemental_arrows.PACK)),
                    m.TABLE: elemental_arrows.patch_table(self.read(m.TABLE))}
        records = m.apply(existing, generated, self.read)
        self.assertTrue(set(m.NATIVE_PACKS) <= set(records))
        for path, (raw, template) in generated.items():
            self.assertEqual((raw, template), (m.patch_pack(originals[path][0])[0], originals[path][1]))
            self.assertEqual(m.patch_pack(raw), (raw, []))
        self.assertEqual(elemental_arrows.patch_pack(existing[elemental_arrows.PACK]),
                         existing[elemental_arrows.PACK])
        self.assertEqual(elemental_arrows.patch_table(existing[m.TABLE]), existing[m.TABLE])
        self.assertEqual(m.apply(existing, generated, self.read), {})


if __name__ == '__main__':
    unittest.main()
