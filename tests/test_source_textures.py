import _src_path  # noqa: F401
import copy
import os
import struct
import unittest

from oot_rando.formats import byml_codec as codec
from oot_rando.formats.inspect_resources import decompress, sarc
from oot_rando.patching import source_textures as textures


class TextureAssetTests(unittest.TestCase):
    def test_bundled_assets_keep_their_internal_names(self):
        for name in set(textures.REMAPS.values()):
            with self.subTest(name=name):
                raw = decompress((textures.ASSETS / (name + '.bntx.zstd')).read_bytes(), {})
                self.assertEqual(raw[:4], b'BNTX')
                self.assertIn(name.encode() + b'\0', raw)

    def test_shorter_pot_name_does_not_move_model_offsets(self):
        old = 'Rock_Pot_A_02_Alb'
        raw = b'FRES' + struct.pack('<H', len(old)) + old.encode() + b'\0unchanged'
        after, used = textures.gold_model(raw)
        self.assertEqual(len(after), len(raw))
        self.assertEqual(after[-9:], b'unchanged')
        self.assertEqual(used, {old: 'random_pot_Alb'})
        self.assertEqual(struct.unpack_from('<H', after, 4)[0], len('random_pot_Alb'))

    def test_unknown_models_remain_unchanged(self):
        raw = b'FRESunknown'
        self.assertEqual(textures.gold_model(raw), (raw, {}))


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class NativeSourceTextureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        from oot_rando.patching.soul_adapter import RSDB_FILES
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.dictionaries = dictionaries(cls.nup)
        cls.members = effective_members(cls.nup)
        cls.tables = {k: codec.load(cls.read(v))['root'] for k, v in RSDB_FILES.items()}

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    @classmethod
    def read(cls, path):
        return decompress(cls.nup.read(cls.members[path]), cls.dictionaries)

    @classmethod
    def pack(cls, actor):
        return sarc(cls.read(f'Pack/Actor/{actor}.pack.zs'))

    def test_all_shuffled_source_models_preserve_physical_state_and_switch_on_check(self):
        import ainb
        from oot_rando.game.item_forms import resolve_components, pack_path
        sources = ['Obj_BrokenBox_A_01', 'Obj_BrokenBox_A_03', 'Obj_BrokenRock_A_01',
                   'Obj_BrokenRock_A_02', 'Obj_Kokiri_Beehive_A_01', 'Obj_LiftRock_A_01',
                   'Obj_LiftRock_A_03', 'Obj_Plant_Grass_A_01', 'Obj_Plant_Grass_A_04',
                   *[f'Obj_Pot_A_{i:02}' for i in range(1, 9)],
                   'Obj_Tree_A_01', 'Obj_Tree_A_02', 'Obj_Tree_Tutorial_A_01']
        native = [{'Gyaml': source, 'Hash': codec.U64(100 + i), 'Translate': [1., 2., 3.],
                   'Dynamic': {'Drop__DropActor': 'Obj_RandoOnce_test'},
                   'Presence': {'FlagName': 'NativeCondition', 'IsNegation': True}}
                  for i, source in enumerate(sources)]
        raw = codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': native}})
        maps = {'map': {'raw': raw}}
        records = [{'kind': 'pickup', 'flag': f'Rando.Check.test{i}',
                    'variants': [{'resource': 'map', 'index': i, 'source': source}]}
                   for i, source in enumerate(sources)]
        tables, raw_maps = copy.deepcopy(self.tables), {}
        files = textures.build_files(records, maps, raw_maps, self.pack, self.read, tables)
        after = codec.load(raw_maps['map'])['root']['Actors']
        self.assertEqual(len(after), len(native))
        for i, record in enumerate(records):
            source = sources[i]
            with self.subTest(source=source):
                variant = record['variants'][0]
                self.assertNotIn('texture_skip', variant)
                actor = variant['textured_actor']
                expected = dict(native[i], Gyaml=actor)
                self.assertEqual(after[i], expected)  # hash, condition, drop and transform untouched
                pack = sarc(files[f'Pack/Actor/{actor}.pack.zs'][0])
                components = resolve_components(pack, actor, codec)
                original = resolve_components(self.pack(source), source, codec)
                for key, value in original.items():
                    if key not in ('ModelInfoRef', 'AIInfoRef', 'PreActorSettingRef'):
                        self.assertEqual(components[key], value)
                model = codec.load(pack[pack_path(components['ModelInfoRef'])])['root']
                self.assertEqual(model['SubModels'][0]['FmdbName'], model['FmdbName'])
                self.assertFalse(model['IsExclusiveControl'])
                nodes = ainb.AINB.from_binary(pack[f'AI/{actor}.root.ainb']).as_dict()['Nodes']
                query = next(n for n in nodes if n['Name'] == 'QueryGetNonStructGameDataBool'
                             and n['Parameters']['Inputs']['String'][0]['Default Value'] == record['flag'])
                actions = [n for n in nodes if n['Name'] == 'OneshotModelSetMaterialVisible']
                def value(index, checked):
                    node = nodes[index]
                    if index == query['Node Index']:
                        return checked
                    self.assertEqual(node['Name'], 'QueryInvertBool')
                    return not value(node['Parameters']['Inputs']['Bool'][0]['Node Index'], checked)
                # Simulate consecutive updates of the same live actor: no re-entry
                # into a selector or a scene reload may be needed to update a tree.
                for checked in (False, True, False):
                    visibility = {}
                    for action in actions:
                        every_frame = next(p['Default Value'] for p in action['Properties']['Bool']
                                           if p['Name'] == 'ExecuteEveryFrame')
                        self.assertTrue(every_frame, 'Live trees must update after collection without respawning')
                        inputs = action['Parameters']['Inputs']
                        access = inputs['Int'][0]['Default Value']
                        visibility.setdefault(access, set()).add(value(inputs['Bool'][0]['Node Index'], checked))
                    self.assertEqual(visibility, {0: {checked}, 1: {not checked}})
                for table in ('ActorInfo', 'GameActorInfo'):
                    self.assertEqual(sum(row['__RowId'] == actor for row in tables[table]), 1)
                actor_row = next(r for r in tables['ActorInfo'] if r['__RowId'] == actor)
                self.assertFalse(actor_row['UsePreActorRenderer'])
                game_row = next(r for r in tables['GameActorInfo'] if r['__RowId'] == actor)
                native_game_row = next(r for r in self.tables['GameActorInfo'] if r['__RowId'] == source)
                self.assertEqual(game_row.get('IsRespawn'), native_game_row.get('IsRespawn'))


if __name__ == '__main__':
    unittest.main()
