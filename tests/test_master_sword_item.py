"""Native get-demo contract and adult-only equipment for shuffled Master Sword."""
import _src_path  # noqa: F401
import copy
import os
import unittest

from oot_rando.formats import byml_codec as codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.game.item_forms import pack_path, _table_components, resolve_components
from oot_rando.patching import master_sword_item as master


class MasterSwordRows(unittest.TestCase):
    def test_child_equipment_is_removed_without_changing_native_rows(self):
        rows = [{'__RowId': master.TEMPLATE, 'ChildEquipment': 'Kokiri',
                 'PouchCategory': 'Weapon', 'PouchGetType': 'Large'},
                {'__RowId': master.WEAPON, 'WeaponSubType': 'MasterSword'}]
        original = copy.deepcopy(rows)
        master.add_rows('PouchActorInfo', rows)
        result = next(row for row in rows if row['__RowId'] == master.MASTER_SWORD_ACTOR)
        self.assertNotIn('ChildEquipment', result)
        self.assertEqual(result['AdultEquipment'],
                         f'Work/Actor/{master.WEAPON}.engine__actor__ActorParam.gyml')
        self.assertEqual([row for row in rows if row['__RowId'] != master.MASTER_SWORD_ACTOR], original)
        with self.assertRaises(ValueError):
            master.add_rows('PouchActorInfo', rows)


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class NativeMasterSword(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.dictionaries = dictionaries(cls.nup)
        cls.members = effective_members(cls.nup)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        from oot_rando.formats.inspect_resources import decompress
        return decompress(self.nup.read(self.members[path]), self.dictionaries)

    def pack(self, actor):
        return sarc(self.read(f'Pack/Actor/{actor}.pack.zs'))

    def test_get_contract_preserves_template_and_grants_native_adult_weapon(self):
        files = sarc(master.build_pack(self.pack))
        components = resolve_components(files, master.MASTER_SWORD_ACTOR, codec)
        original = resolve_components(self.pack(master.TEMPLATE), master.TEMPLATE, codec)
        for key in ('ASInfoRef', 'ASRef', 'EventPerformerRef', 'PhysicsRef', 'ActorLogicNodeRef'):
            self.assertEqual(components[key], original[key])
        actor = codec.load(files[f'Actor/{master.MASTER_SWORD_ACTOR}.engine__actor__ActorParam.bgyml'])['root']
        self.assertEqual(actor['$parent'], 'Work/Actor/Item_EventObject_Base.engine__actor__ActorParam.gyml')
        self.assertIn('Actor/Item_EventObject_Base.engine__actor__ActorParam.bgyml', files)
        self.assertIn('Item_GetDemo', components['ASInfoRef'])
        self.assertEqual(components['ActorNameRef'],
                         resolve_components(self.pack(master.WEAPON), master.WEAPON, codec)['ActorNameRef'])
        model = codec.load(files[pack_path(components['ModelInfoRef'])])['root']
        self.assertEqual(model['ModelProjectName'], master.WEAPON)
        self.assertEqual(model['FmdbName'], master.WEAPON)
        animation = codec.load(files[pack_path(components['AnimationRef'])])['root']
        self.assertEqual(animation['AnimationResources'], master.ANIMATIONS)
        self.assertIn('Model/Item_Common_Animation.anim.bfres.zs', self.members)
        self.assertIn(f'Model/{master.WEAPON}.{master.WEAPON}.bfres.zs', self.members)
        table = _table_components(files, components['GameParameterTableRef'], codec)
        equipment = codec.load(files[pack_path(table['PlayerEquipmentActor'])])['root']
        self.assertEqual(equipment, {'Adult': f'Work/Actor/{master.WEAPON}.engine__actor__ActorParam.gyml'})
        pouch = codec.load(files[pack_path(components['PouchContentRef'])])['root']
        self.assertEqual(pouch['PouchActor'], equipment['Adult'])
        self.assertIn(pack_path(pouch['$parent']), files)

    def test_new_references_resolve_and_all_three_rows_preserve_native_data(self):
        modified, new = master.build_files(self.read)
        self.assertEqual(set(modified), set(master.RSDB_FILES.values()) | {master.PEDESTAL_PACK})
        self.assertEqual(set(new), {master.PACK})
        raw, template = new[master.PACK]
        self.assertEqual(template, master.TEMPLATE_PACK)
        files = sarc(raw)
        # Every reference introduced or replaced by this adapter resolves locally
        # or is an existing shared native parameter. Native external refs in the
        # unchanged template are outside this adapter's responsibility.
        components = resolve_components(files, master.MASTER_SWORD_ACTOR, codec)
        # Native ActorName refs are symbolic identities: neither the original
        # weapon nor native sword-get packs contain a corresponding BYML file.
        # Preserve that exact native ref and verify its RSDB identity below.
        self.assertEqual(components['ActorNameRef'],
                         resolve_components(self.pack(master.WEAPON), master.WEAPON, codec)['ActorNameRef'])
        for key in ('ModelInfoRef', 'AnimationRef', 'PouchContentRef', 'GameParameterTableRef'):
            path = pack_path(components[key])
            self.assertTrue(path in files or path in self.members, path)
        for name, path in master.RSDB_FILES.items():
            before = codec.load(self.read(path))['root']
            after = codec.load(modified[path])['root']
            row = next(row for row in after if row['__RowId'] == master.MASTER_SWORD_ACTOR)
            self.assertEqual([r for r in after if r['__RowId'] != master.MASTER_SWORD_ACTOR], before)
            if name == 'ActorInfo':
                self.assertEqual(row['ActorName'], master.WEAPON)
                self.assertEqual(row['ModelProjectName'], master.WEAPON)
                self.assertEqual(row['AnimationResources'], master.ANIMATIONS)
            if name == 'PouchActorInfo':
                self.assertNotIn('ChildEquipment', row)
                self.assertIn(master.WEAPON, row['AdultEquipment'])
                self.assertEqual(row['PouchGetType'], 'Large')

    def test_adult_put_in_prompt_uses_the_swordless_pull_verb(self):
        # 20/11: no put-in prompt without the Master Sword owned.
        before = sarc(self.read(master.PEDESTAL_PACK))
        after = sarc(master.pedestal_put_in_without_sword(self.read(master.PEDESTAL_PACK)))
        self.assertEqual(set(after), set(before))
        for path in before:
            if path != master.PUT_IN_CLIENT:
                self.assertEqual(after[path], before[path], path)
        old, new = (codec.load(files[master.PUT_IN_CLIENT])['root'] for files in (before, after))
        self.assertEqual(new['ActionType'], master.PULL_OUT)
        new['ActionType'] = master.PUT_IN
        self.assertEqual(new, old)
        pull = codec.load(before['Attention/ClientParam/TimeTemple_MasterSwordAttention_PullOut'
                                 '.game__attention__ClientParam.bgyml'])['root']
        self.assertEqual(pull['ActionType'], master.PULL_OUT)
        with self.assertRaises(ValueError):
            master.pedestal_put_in_without_sword(codec.build_sarc(after))


if __name__ == '__main__':
    unittest.main()
