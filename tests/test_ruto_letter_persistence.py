"""Lake Hylia's shuffled letter records its check independently of its reward."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching.repeatable_adapter import prepare_repeatables, build_repeatable_packs

RESOURCE = 'Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs'
GID = 'HyruleField#letter#474136620438465634'


def fixture(reward='Obj_RandoWater_Item_Hookshot'):
    placement = {'id': GID, 'source': 'quest', 'before': 'Obj_Bottle_Letter',
                 'after': reward, 'underwater': True,
                 'patches': [{'resource': RESOURCE, 'path': ['Actors', 0, 'Gyaml'],
                              'before': 'Obj_Bottle_Letter'}]}
    return ({'placements': [placement], 'matches': {GID: {}}},
            {RESOURCE: {'root': {'Actors': [{'Gyaml': 'Obj_Bottle_Letter',
                                            'Hash': 474136620438465634}]}}})


class RutoPersistenceTests(unittest.TestCase):
    def test_letter_gets_its_own_saved_check(self):
        plan, maps = fixture()
        records = prepare_repeatables(plan, maps)
        self.assertEqual(len(records), 1)
        record, placement = records[0], plan['placements'][0]
        self.assertEqual(record['kind'], 'placed')
        self.assertTrue(record['underwater'])
        self.assertEqual(record['canonical'], 'Item_Hookshot')
        self.assertTrue(record['flag'].startswith('Rando.Check.'))
        self.assertEqual(placement['first_collect_flag'], record['flag'])
        self.assertEqual(plan['matches'][GID]['first_collect_flag'], record['flag'])
        self.assertEqual(placement['reward_actor'], 'Obj_RandoWater_Item_Hookshot')
        self.assertEqual(placement['after'], record['actor'])

    def test_other_quest_rewards_keep_their_native_adapter(self):
        plan, maps = fixture()
        plan['placements'][0]['before'] = 'Item_Ocarina_Fairy'
        self.assertEqual(prepare_repeatables(plan, maps), [])


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class NativeRutoPersistenceTests(unittest.TestCase):
    def test_native_letter_has_no_persistent_hash_and_generated_pickups_write_after_get(self):
        import ainb
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        from oot_rando.game.world_maps import effective_members
        from oot_rando.game.item_forms import GLOW_ELINK, resolve_components
        from oot_rando.patching.soul_adapter import RSDB_FILES
        from oot_rando.patching.repeatable_adapter import LARGE_GET_TYPE
        nup = Nup(os.environ['OOT_NUP'])
        try:
            dic, members = dictionaries(nup), effective_members(nup)

            def read_raw(path):
                return decompress(nup.read(members[path]), dic)

            def read_pack(actor):
                path = f'Pack/Actor/{actor}.pack.zs'
                return sarc(read_raw(path)) if path in members else None

            schema = byml_codec.load(read_raw('GameData/GameDataList.Product.110.byml.zs'))['root']
            self.assertNotIn(474136620438465634,
                             {int(r['Hash']) for r in schema['Data']['Bool64bitKey']})
            for reward in ('Obj_RandoWater_Item_Hookshot', 'Obj_RandoWater_TBox_Rupee_Red'):
                with self.subTest(reward=reward):
                    plan, maps = fixture(reward)
                    record, = prepare_repeatables(plan, maps)
                    tables = {name: byml_codec.load(read_raw(path))['root']
                              for name, path in RSDB_FILES.items()}
                    new = build_repeatable_packs([record], read_pack, read_raw, tables)
                    files = sarc(new[f'Pack/Actor/{record["actor"]}.pack.zs'][0])
                    components = resolve_components(files, record['actor'], byml_codec)
                    pouch = byml_codec.load(files[components['PouchContentRef'][1:]])['root']
                    self.assertTrue(pouch['PlayGetEventManyTimes'])
                    self.assertEqual(pouch['GetType'], LARGE_GET_TYPE)
                    self.assertEqual(components['ELinkRef'], '?' + GLOW_ELINK)
                    event = ainb.AINB.from_binary(files[f'AI/{record["event_filename"]}.ainb']).as_dict()['Nodes']
                    drop = ainb.AINB.from_binary(files[f'AI/{record["actor"]}.root.ainb']).as_dict()['Nodes']
                    self.assertNotIn('OneShotSetNonStructGameDataBool', [n['Name'] for n in drop])
                    self.assertIn('OneShotGenericDeleteThisActor', [n['Name'] for n in drop])
                    setter, = [n for n in event if n['Name'] == 'OneShotSetNonStructGameDataBool']
                    sequence, = [n for n in event if any(p['Node Index'] == setter['Node Index']
                                                         for p in n.get('Plugs', {}).get('Child', []))]
                    steps = [event[p['Node Index']]['Name'] for p in sequence['Plugs']['Child']]
                    self.assertEqual(steps, ['OneShotPouchContentPushToPouchOwnInEvent',
                                             'OneShotSetNonStructGameDataBool'])
                    self.assertEqual(setter['Parameters']['Inputs']['String'][0]['Default Value'], record['flag'])
        finally:
            nup.stream.close()
