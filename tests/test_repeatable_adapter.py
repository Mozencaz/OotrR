import _src_path  # noqa: F401  (src on sys.path)
import copy
import math
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.patching.repeatable_adapter import (prepare_repeatables, patch_repeatable_sources,
                                instrument_pickup_event, register_repeatable_flags,
                                add_sold_out_board, limit_shop_stock, shop_stock_edits)
from oot_rando.formats.inspect_resources import sarc, decompress


class RepeatableSourceTests(unittest.TestCase):
    def fixtures(self, original_presence=None, explicit=True):
        actor = {'Hash': byml_codec.U64(98765432123456789), 'Gyaml': 'Obj_Pot_A_01',
                 'Translate': [1., 2., 3.], 'Dynamic': {'Drop__DropTable': 'original-table'}}
        if explicit:
            actor['Dynamic']['Drop__DropActor'] = 'Obj_Rupee_Green'
        if original_presence:
            actor['Presence'] = original_presence
        original = {'Actors': [actor], 'AiGroups': []}
        raw = byml_codec.dump({'root': original, 'endian': '<', 'version': 7})
        maps = {'map': {'root': original, 'raw': raw}}
        plan = {'placements': [{'id': 'zone#pots#98765432123456789', 'source': 'pots',
                'after': 'Obj_Rando_Item_BombBag_Small', 'before': 'Obj_Rupee_Green',
                'patches': [{'resource': 'map', 'path': ['Actors', 0, 'Dynamic', 'Drop__DropActor']}]}],
                'matches': {}}
        return plan, maps

    def test_shuffled_source_keeps_its_map_entry_but_for_its_drop(self):
        """No Presence and no vanilla copy: the game remembers a broken source by its
        hash until the scene changes, as for the vanilla one."""
        for explicit in (True, False):
            with self.subTest(explicit=explicit):
                plan, maps = self.fixtures(explicit=explicit)
                actor = maps['map']['root']['Actors'][0]
                actor['Links'] = [{'Name': 'Cut', 'Src': actor['Hash'], 'Dst': byml_codec.U64(2**63+3)}]
                actor['Phive'] = {'Placement': {'ID': actor['Hash']}}
                maps['map']['raw'] = byml_codec.dump({'root': maps['map']['root'], 'endian': '<', 'version': 7})
                records = prepare_repeatables(plan, maps)
                self.assertEqual(records[0]['variants'], [{'resource': 'map', 'index': 0, 'native_once': False}])
                patched = copy.deepcopy(maps['map']['root'])
                patched['Actors'][0]['Dynamic']['Drop__DropActor'] = records[0]['actor']
                raw_maps = {'map': byml_codec.dump({'root': patched, 'endian': '<', 'version': 7})}
                self.assertEqual(patch_repeatable_sources(records, maps, raw_maps), [])
                result = byml_codec.load(raw_maps['map'])['root']['Actors']
                self.assertEqual(len(result), 1)
                self.assertNotIn('Presence', result[0])
                self.assertEqual(result[0]['Dynamic']['Drop__DropActor'], records[0]['actor'])
                expected = copy.deepcopy(maps['map']['root']['Actors'][0])
                expected['Dynamic']['Drop__DropActor'] = records[0]['actor']
                self.assertEqual(result[0], expected)
                self.assertEqual(plan['placements'][0]['reward_actor'], 'Obj_Rando_Item_BombBag_Small')

    def test_minor_rewards_use_the_short_get(self):
        from oot_rando.patching.repeatable_adapter import LARGE_GET_TYPE, MEDIUM_GET_TYPE, get_type
        from oot_rando.patching.soul_adapter import murmur3
        self.assertEqual((LARGE_GET_TYPE, MEDIUM_GET_TYPE), (murmur3('Large'), murmur3('Medium')))
        # Their native pickup (no GetType): Medium still posed (Discord 15/11, 0.6.1).
        for actor in ('TBox_Rupee_Green', 'TBox_Rupee_Gold', 'TBox_ArrowBundle_Large', 'TBox_DekuNutBundle',
                      'Item_BombBundle_Small', 'Item_DekuStickBundle_Small', 'Obj_Heart', 'Tbox_MagicJar_Large'):
            self.assertIsNone(get_type(actor), actor)
        self.assertEqual(get_type('Item_BombchuBundle_Small'), MEDIUM_GET_TYPE)   # Large natively
        for actor in ('Item_Hookshot', 'Obj_Heart_Piece', 'Obj_Heart_Container', 'Item_Token_Gold',
                      'Item_Soul_Keese', 'TBox_Shield_Deku'):
            self.assertEqual(get_type(actor), LARGE_GET_TYPE, actor)

    def test_minor_rewards_keep_the_native_pickup_window(self):
        # Discord 17/11: every pot rupee showed "You got a Green Rupee!".
        from oot_rando.patching.repeatable_adapter import LARGE_GET_TYPE, MEDIUM_GET_TYPE, pickup_pouch_settings
        for actor in ('TBox_Rupee_Green', 'Item_BombBundle_Small', 'Obj_Heart'):
            self.assertEqual(pickup_pouch_settings(actor), {'PlayGetEventManyTimes': False,
                                                            'IsAutoSaveAfterPlayGet': True}, actor)
        self.assertEqual(pickup_pouch_settings('Item_BombchuBundle_Large')['GetType'], MEDIUM_GET_TYPE)
        key = pickup_pouch_settings('Item_Hookshot')
        self.assertEqual((key['PlayGetEventManyTimes'], key['GetType']), (True, LARGE_GET_TYPE))

    def test_native_once_pot_keeps_presence_without_a_second_source(self):
        presence = {'FlagName': 'IceCavern_Room07_RedRupeePot_IsCrushed', 'IsNegation': True, 'IsCheckLazy': True}
        plan, maps = self.fixtures(presence)
        records = prepare_repeatables(plan, maps)
        self.assertTrue(records[0]['variants'][0]['native_once'])
        raw_maps = {}
        self.assertEqual(patch_repeatable_sources(records, maps, raw_maps), [])
        self.assertEqual(maps['map']['root']['Actors'][0]['Presence'], presence)

    def test_saved_bool_is_the_only_save_data_added(self):
        plan, maps = self.fixtures()
        records = prepare_repeatables(plan, maps)
        schema = {'Data': {'Bool': [{'Hash': byml_codec.U32(123), 'DefaultValue': False,
                    'SaveFileIndex': 0, 'ResetTypeValue': 8}],
                    'Bool64bitKey': [{'Hash': byml_codec.U64(98765432123456789),
                    'SaveFileIndex': 0, 'ResetTypeValue': 88}]},
                  'MetaData': {'SaveDataSize': [100], 'SaveDataOffsetPos': [80],
                               'AllDataSaveSize': 100, 'AllDataSaveOffset': 80}}
        raw = byml_codec.dump({'root': schema, 'endian': '<', 'version': 7})
        after, report = register_repeatable_flags(raw, records)
        result = byml_codec.load(after)['root']
        self.assertEqual(result['MetaData']['SaveDataSize'], [108])
        self.assertEqual(result['MetaData']['SaveDataOffsetPos'], [88])
        self.assertEqual(result['MetaData']['AllDataSaveOffset'], 88)
        self.assertEqual(report['saved_bytes_added'], 8)
        self.assertEqual(len(result['Data']['Bool']), 2)
        # The source's own broken-state key is the vanilla one, untouched.
        self.assertEqual(result['Data']['Bool64bitKey'], schema['Data']['Bool64bitKey'])
        with self.assertRaisesRegex(ValueError, '(?i)collision'):
            register_repeatable_flags(after, records)

    def test_shuffled_shop_item_gets_its_own_once_actor(self):
        shelf = {'id': 'Market#shop#Shop_Bottle_Fish#3', 'source': 'shop', 'after': 'Shop_Rando_Item_Hookshot',
                 'before': 'Shop_Bottle_Fish', 'patches': [{'resource': 'map', 'path': ['Actors', 0, 'Gyaml']}]}
        refill = {'id': 'Market#shop#Shop_ArrowBundle_01#0', 'source': 'shop', 'after': 'Shop_DekuNutBundle_01',
                  'before': 'Shop_ArrowBundle_01', 'patches': [{'resource': 'map', 'path': ['Actors', 1, 'Gyaml']}]}
        plan = {'placements': [shelf, refill], 'matches': {shelf['id']: {}}}
        records = prepare_repeatables(plan, {})
        self.assertEqual(len(records), 1)            # a native refill stays as it is
        record = records[0]
        self.assertEqual(record['kind'], 'shop')
        self.assertTrue(record['actor'].startswith('Shop_RandoOnce_'))
        self.assertEqual((record['canonical'], record['original_reward_actor']), ('Item_Hookshot', 'Shop_Rando_Item_Hookshot'))
        self.assertEqual(record['variants'], [])     # the shelf keeps its Presence: none added
        self.assertEqual(shelf['after'], record['actor'])
        self.assertEqual(plan['matches'][shelf['id']]['first_collect_flag'], record['flag'])
        self.assertEqual([(s['resource'], s['index'], s['shelf']) for s in record['shelves']],
                         [('map', 0, 'Shop_Bottle_Fish')])
        seller = {'Gyaml': 'Npc_Shop', 'Hash': 7, 'Links': [{'Dst': 100, 'Name': 'ForSale', 'Src': 7}]}
        actors = [{'Gyaml': 'Shop_Bottle_Fish', 'Hash': 100, 'Dynamic': {'ShopItemIndex': 3},
                   'Translate': [1.0, 2.0, 3.0], 'Rotate': [0.0, math.pi / 2, 0.0], 'SRTHash': 9},
                  {'Gyaml': 'Shop_ArrowBundle_01', 'Hash': 101}, seller]
        maps = {'map': {'raw': byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': actors}}),
                        'root': {'Actors': actors}}}
        self.assertEqual(shop_stock_edits(records, maps), {'Npc_Shop': {3: 'Shop_Bottle_Fish'}})
        output = {}
        self.assertEqual(patch_repeatable_sources(records, maps, output), ['map'])
        result = byml_codec.load(output['map'])['root']['Actors']
        board = result[-1]
        self.assertEqual(board['Gyaml'], 'Shop_Board_SoldOut')
        self.assertEqual(int(board['Hash']), record['shelves'][0]['board_hash'])
        self.assertAlmostEqual(board['Translate'][0], 1.0 - 0.25)   # behind the shelf
        self.assertAlmostEqual(board['Translate'][2], 3.0)
        self.assertEqual(board['SRTHash'], 9)
        self.assertEqual([(int(l['Dst']), l['Name']) for l in result[0]['Links']],
                         [(record['shelves'][0]['board_hash'], 'Reference')])

    def test_native_sold_out_board_is_not_doubled(self):
        actors = [{'Gyaml': 'Shop_DekuStick', 'Hash': 1, 'Translate': [0.0, 0.0, 0.0],
                   'Links': [{'Dst': 2, 'Name': 'Reference', 'Src': 1}]},
                  {'Gyaml': 'Shop_Board_SoldOut', 'Hash': 2}]
        self.assertIsNone(add_sold_out_board(actors, 0, 3))
        self.assertEqual(len(actors), 2)

    def test_shop_goods_of_shuffled_slots_are_sold_once(self):
        def good(actor):
            return {'Actor': f'Work/Actor/{actor}.engine__actor__ActorParam.gyml', 'StockNum': -1}
        param = {'GoodsList': [good('Shop_Heart'), good('Shop_DekuStick'), good('Shop_DekuNutBundle_01')]}
        pack = byml_codec.build_sarc({
            'Component/ShopParam/Npc.game__component__ShopParam.bgyml':
                byml_codec.dump({'endian': '<', 'version': 7, 'root': param}),
            'Actor/Npc.engine__actor__ActorParam.bgyml': b'other'})
        raw, changed = limit_shop_stock(pack, {1: 'Shop_DekuStick'})
        self.assertEqual(changed, [1])
        files = sarc(raw)
        goods = byml_codec.load(files['Component/ShopParam/Npc.game__component__ShopParam.bgyml'])['root']['GoodsList']
        self.assertEqual([g['StockNum'] for g in goods], [-1, 1, -1])
        self.assertEqual(files['Actor/Npc.engine__actor__ActorParam.bgyml'], b'other')
        with self.assertRaisesRegex(ValueError, 'not found'):
            limit_shop_stock(pack, {2: 'Shop_DekuStick'})   # another shelf in that slot

    def test_uncombinable_presence_fails_instead_of_bypassing_original_requirement(self):
        plan, maps = self.fixtures({'FlagName': 'QuestGate', 'IsNegation': False})
        with self.assertRaisesRegex(ValueError, 'Conditional presence'):
            prepare_repeatables(plan, maps)


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class LocalGraphTests(unittest.TestCase):
    def test_shop_item_ai_sets_and_reads_its_own_sold_out_flag(self):
        import ainb
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        from oot_rando.patching.repeatable_adapter import SHOP_AI_MEMBER, as_command, instrument_shop_ai, _refers
        nup = Nup(os.environ['OOT_NUP'])
        try:
            dic, members = dictionaries(nup), effective_members(nup)
            raw = sarc(decompress(nup.read(members['Pack/Actor/Shop_ArrowBundle_01.pack.zs']), dic))[SHOP_AI_MEMBER]
        finally:
            nup.stream.close()
        before = ainb.AINB.from_binary(raw).as_dict()
        after = ainb.AINB.from_binary(instrument_shop_ai(raw, 'Rando.Check.test', 'Shop_RandoOnce_test.root')).as_dict()
        self.assertEqual(before['Commands'], after['Commands'])
        nodes = {n['Node Index']: n for n in after['Nodes']}
        setter, query, delete, native = after['Nodes'][len(before['Nodes']):]
        self.assertEqual((setter['Name'], query['Name'], delete['Name']),
                         ('OneShotSetNonStructGameDataBool', 'QueryGetNonStructGameDataBool', 'OneShotGenericDeleteThisActor'))
        visibility = next(n for n in after['Nodes'] if n['Node Type'] == 'Element_BoolSelector'
                          and _refers(n.get('Parameters'), query['Node Index']))
        self.assertEqual({p['Name']: p['Node Index'] for p in visibility['Plugs']['Child']}['True'], native['Node Index'])
        # Bought: hidden while the shop's own stock says sold out, deleted otherwise.
        sold_out = next(n['Node Index'] for n in after['Nodes'] if n['Name'] == 'QueryShopItemIsSoldOut')
        self.assertEqual(native['Queries'], [sold_out])
        branches = {p['Name']: nodes[p['Node Index']] for p in native['Plugs']['Child']}
        self.assertEqual(branches['True']['Name'], 'OneShotGameModelControllerSetVisible')
        self.assertIs(branches['True']['Parameters']['Inputs']['Bool'][0]['Default Value'], False)
        self.assertEqual(branches['False']['Node Index'], delete['Node Index'])
        put = next(n['Node Index'] for n in after['Nodes'] if n['Name'] == 'ExecuteShopItemPutInPouch')
        put_parent = next(n for n in after['Nodes'] if any(p['Node Index'] == put for p in n['Plugs'].get('Child', [])))
        self.assertNotIn(visibility['Node Index'], [p['Node Index'] for p in put_parent['Plugs']['Child']])
        for node in (setter, query):
            self.assertEqual(node['Parameters']['Inputs']['String'][0]['Default Value'], 'Rando.Check.test')
        parents = [n for n in after['Nodes'] if any(p['Node Index'] == setter['Node Index']
                                                     for p in n['Plugs'].get('Child', []))]
        steps = {(nodes[p['Node Index']]['Name'], as_command(nodes[p['Node Index']]))
                 for parent in parents for p in parent['Plugs']['Child']}
        self.assertEqual(len(parents), 2)   # bought with a get demo, or put in the pouch
        self.assertIn(('ExecuteASPlay', 'Rotate_GetDemo'), steps)
        self.assertIn(('ExecuteShopItemPutInPouch', None), steps)
        readers = [i for i, n in nodes.items() if _refers(n.get('Parameters'), query['Node Index'])]
        self.assertEqual(len(readers), 2)   # model visibility and sold out message
        self.assertEqual([i for i, n in nodes.items() if i != sold_out and _refers(n.get('Parameters'), sold_out)],
                         [native['Node Index']])

    def test_native_pickup_graph_adds_flag_after_pouch_action_and_preserves_commands(self):
        import ainb
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(os.environ['OOT_NUP'])
        try:
            dic = dictionaries(nup)
            members = effective_members(nup)
            pack = sarc(decompress(nup.read(members['Pack/AI.Global.Product.111.pack.zs']), dic))
            raw = pack['AI/PouchContent.event.root.ainb']
            before = ainb.AINB.from_binary(raw).as_dict()
            after = ainb.AINB.from_binary(instrument_pickup_event(raw, 'Rando.Check.test', 'RandoOnce_test.event.root')).as_dict()
            self.assertEqual(before['Commands'], after['Commands'])
            self.assertEqual(len(after['Nodes']), len(before['Nodes']) + 4)
            seq, setter = after['Nodes'][len(before['Nodes']):len(before['Nodes']) + 2]
            self.assertEqual(after['Nodes'][seq['Plugs']['Child'][0]['Node Index']]['Name'], 'OneShotPouchContentPushToPouchOwnInEvent')
            self.assertEqual(seq['Plugs']['Child'][1]['Node Index'], setter['Node Index'])
            self.assertEqual(setter['Parameters']['Inputs']['String'][0]['Default Value'], 'Rando.Check.test')
            guarded = ainb.AINB.from_binary(instrument_pickup_event(raw, 'Rando.Check.test',
                       'RandoOnce_test.event.root', 'Item_BombBag_Small')).as_dict()
            sequence, saved, can_add, selector = guarded['Nodes'][len(before['Nodes']):len(before['Nodes']) + 4]
            self.assertEqual(can_add['Name'], 'QueryPouchMgrIsEnablePushToPouch')
            self.assertEqual(can_add['Parameters']['Inputs']['String'][0]['Default Value'], 'Item_BombBag_Small')
            branches = {x['Name']: x['Node Index'] for x in selector['Plugs']['Child']}
            self.assertEqual(branches['True'], sequence['Node Index'])
            self.assertEqual(guarded['Nodes'][branches['False']]['Name'], 'OneshotDoNothing')
            self.assertEqual(sequence['Plugs']['Child'][1]['Node Index'], saved['Node Index'])
            flag_query, flag_selector = guarded['Nodes'][-2:]
            self.assertEqual(flag_query['Name'], 'QueryGetNonStructGameDataBool')
            self.assertEqual(flag_query['Parameters']['Inputs']['String'][0]['Default Value'], 'Rando.Check.test')
            flag_branches = {p['Name']: p['Node Index'] for p in flag_selector['Plugs']['Child']}
            self.assertEqual(guarded['Nodes'][flag_branches['True']]['Name'], 'OneshotDoNothing')
            self.assertEqual(flag_branches['False'], selector['Node Index'])
            original_push = sequence['Plugs']['Child'][0]['Node Index']
            incoming = [p['Node Index'] for n in guarded['Nodes'][:len(before['Nodes'])]
                        for p in n.get('Plugs', {}).get('Child', []) if p['Node Index'] == original_push]
            self.assertEqual(incoming, [])

        finally:
            nup.stream.close()

    def test_repeatable_pickups_fall_like_native_drops(self):
        """Pots, trees, rocks...: the first-collection pickup is built on a falling drop."""
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.item_forms import DROP_TEMPLATE, resolve_components
        from oot_rando.game.world_maps import effective_members
        from oot_rando.patching.repeatable_adapter import build_repeatable_packs
        from oot_rando.patching.soul_adapter import RSDB_FILES
        nup = Nup(os.environ['OOT_NUP'])
        try:
            dic, members = dictionaries(nup), effective_members(nup)

            def read_raw(path):
                return decompress(nup.read(members[path]), dic)

            def read_pack(actor):
                path = f'Pack/Actor/{actor}.pack.zs'
                return sarc(read_raw(path)) if path in members else None

            tables = {name: byml_codec.load(read_raw(path))['root'] for name, path in RSDB_FILES.items()}
            records = [{'id': f'zone#{source}#{i}', 'actor': f'Obj_RandoOnce_{i:016x}', 'canonical': canonical,
                        'kind': 'pickup', 'flag': f'Rando.Check.{i:016x}',
                        'event_filename': f'RandoOnce_{i:016x}.event.root', 'variants': []}
                       for i, (source, canonical) in enumerate((('trees', 'Item_Hookshot'), ('pots', 'TBox_Rupee_Red'),
                                                                ('crates', 'Item_Dungeon_SmallKey')))]
            new = build_repeatable_packs(records, read_pack, read_raw, tables)
            rupee = resolve_components(read_pack('Obj_Rupee_Green'), 'Obj_Rupee_Green', byml_codec)
            nut = resolve_components(read_pack(DROP_TEMPLATE), DROP_TEMPLATE, byml_codec)
        finally:
            nup.stream.close()
        for record in records:
            actor = record['actor']
            with self.subTest(canonical=record['canonical']):
                raw, template = new[f'Pack/Actor/{actor}.pack.zs']
                self.assertEqual(template, f'Pack/Actor/{DROP_TEMPLATE}.pack.zs')
                files = sarc(raw)
                components = resolve_components(files, actor, byml_codec)
                for key in ('BlackboardRef', 'DeathRef', 'AttentionSenderRef'):
                    self.assertEqual(components[key], rupee[key], key)
                self.assertEqual(components['PhysicsRef'], nut['PhysicsRef'])
                self.assertNotIn('GameLifeConditionRef', components)
                # The first-collection event and pouch settings stay the pickup's own.
                event = byml_codec.load(files[components['EventPerformerRef'][1:]])['root']
                self.assertEqual(event['EventUniqueAin'], f'Work/AI/Root/Event/{record["event_filename"]}.ain')
                self.assertIn(f'AI/{record["event_filename"]}.ainb', files)
                pouch = byml_codec.load(files[components['PouchContentRef'][1:]])['root']
                from oot_rando.patching.repeatable_adapter import is_minor_reward
                # Minor rewards: the get window only for the first item of its kind ever got.
                self.assertIs(pouch['PlayGetEventManyTimes'], not is_minor_reward(record['canonical']))
                self.assertEqual(pouch['PouchActor'], f'Work/Actor/{record["canonical"]}.engine__actor__ActorParam.gyml')
                for rows in tables.values():
                    self.assertEqual(sum(1 for row in rows if row['__RowId'] == actor), 1)
                # Its own drop AI: deleted on spawn once the check is collected.
                info = byml_codec.load(files[components['AIInfoRef'][1:]])['root']
                self.assertEqual(info['RootAIRef'], f'Work/AI/Root/{actor}.root.ain')
                self.assertIn(f'AI/{actor}.root.ainb', files)

    def test_respawned_drop_deletes_itself_once_collected(self):
        import ainb
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        from oot_rando.patching.repeatable_adapter import (DROP_AI_MEMBER, EVENT_MEMBER, EVENT_PACK,
                                                           instrument_drop_ai)
        nup = Nup(os.environ['OOT_NUP'])
        try:
            dic, members = dictionaries(nup), effective_members(nup)
            pack = sarc(decompress(nup.read(members[EVENT_PACK]), dic))
        finally:
            nup.stream.close()
        raw = pack[DROP_AI_MEMBER]
        before = ainb.AINB.from_binary(raw).as_dict()
        after = ainb.AINB.from_binary(instrument_drop_ai(raw, 'Rando.Check.test', 'Obj_RandoOnce_test.root',
                                                         pack[EVENT_MEMBER])).as_dict()
        self.assertEqual(before['Commands'], after['Commands'])
        self.assertEqual(after['Filename'], 'Obj_RandoOnce_test.root')
        # Every native node is kept as it was, but for the start-up sequence's first step.
        count = len(before['Nodes'])
        query, delete, keep, selector = after['Nodes'][count:]
        changed = [i for i in range(count) if before['Nodes'][i] != after['Nodes'][i]]
        self.assertEqual(len(changed), 1)
        start = after['Nodes'][changed[0]]
        self.assertEqual(start['Node Type'], 'Element_Sequential')
        self.assertEqual(start['Plugs']['Child'][0]['Node Index'], selector['Node Index'])
        self.assertEqual(start['Plugs']['Child'][1:], before['Nodes'][changed[0]]['Plugs']['Child'])
        root = after['Nodes'][after['Commands'][0]['Root Node Index']]
        self.assertIn(start['Node Index'], [p['Node Index'] for p in root['Plugs']['Child']])
        self.assertEqual(query['Name'], 'QueryGetNonStructGameDataBool')
        self.assertEqual(query['Parameters']['Inputs']['String'][0]['Default Value'], 'Rando.Check.test')
        self.assertIs({p['Name']: p['Default Value'] for p in query['Properties']['Bool']}['OutputOnlyOnEnter'], True)
        self.assertEqual(selector['Queries'], [query['Node Index']])
        branches = {p['Name']: p['Node Index'] for p in selector['Plugs']['Child']}
        self.assertEqual(branches, {'True': delete['Node Index'], 'False': keep['Node Index']})
        self.assertEqual(delete['Name'], 'OneShotGenericDeleteThisActor')
        self.assertIs({p['Name']: p['Default Value'] for p in delete['Properties']['Bool']}['IsFade'], False)
        self.assertEqual(keep['Name'], 'OneshotDoNothing')


if __name__ == '__main__':
    unittest.main()
