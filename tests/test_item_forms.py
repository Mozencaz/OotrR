import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.game.item_forms import (NATIVE_WORLD, WORLD_POUCH_FLAGS, WORLD_TEMPLATE, build_pack, canonical_of,
                                       form_actor, is_derived, is_world_derived, resolve_components,
                                       _table_components)

# Components that make the gold token's AI save the skulltula it drops from
# (REALAZK pickup_pack/kit.rs, MIT, ae9e4063: REFS and LIFE_REF).
TOKEN_KIT_REFS = ('AIInfoRef', 'BlackboardRef', 'DeathRef', 'GameLifeConditionRef')


def doc(root):
    return byml_codec.dump({'endian': '<', 'version': 7, 'root': root})


def fake_packs():
    """Minimal gold-token template + bomb bag source, shaped like the game packs."""
    template = {
        f'Actor/{WORLD_TEMPLATE}.engine__actor__ActorParam.bgyml': doc({'Components': {
            'GameParameterTableRef': f'?GameParameter/GameParameterTable/{WORLD_TEMPLATE}.engine__actor__GameParameterTable.bgyml',
            'PouchContentRef': '?Component/PouchContentParam/Token.game__component__PouchContentParam.bgyml'}}),
        f'GameParameter/GameParameterTable/{WORLD_TEMPLATE}.engine__actor__GameParameterTable.bgyml': doc({
            '$parent': 'Work/GameParameter/GameParameterTable/Obj_Item_Base.engine__actor__GameParameterTable.gyml'}),
        'GameParameter/GameParameterTable/Obj_Item_Base.engine__actor__GameParameterTable.bgyml': doc({
            'Category': 'GameParameterTableDefault', 'Components': {
                'DropBoundParam': '?GameParameter/DropBoundParam/Obj_Item_Base.game__drop__DropBoundParam.bgyml'}}),
        'GameParameter/DropBoundParam/Obj_Item_Base.game__drop__DropBoundParam.bgyml': doc({'CliffHeight': 9.0}),
        'Component/PouchContentParam/Token.game__component__PouchContentParam.bgyml': doc({'DefaultAutoGet': True}),
    }
    expansion = '?GameParameter/ExpansionMaxNumActor/Item_BombBag_Small.game__actor__ExpansionMaxNumActor.bgyml'
    source = {
        'Actor/Item_BombBag_Small.engine__actor__ActorParam.bgyml': doc({'Components': {
            'GameParameterTableRef': '?GameParameter/GameParameterTable/Item_BombBag_Small.engine__actor__GameParameterTable.bgyml',
            'PouchContentRef': '?Component/PouchContentParam/BombBag.game__component__PouchContentParam.bgyml'}}),
        'GameParameter/GameParameterTable/Item_BombBag_Small.engine__actor__GameParameterTable.bgyml': doc({
            'Category': 'GameParameterTableDefault', 'Components': {
                'ExpansionMaxNumActor': expansion,
                'DropBoundParam': '?GameParameter/DropBoundParam/Other.game__drop__DropBoundParam.bgyml'}}),
        expansion[1:]: doc({'GameData': 'Bomb', 'MaxNum': 20}),
        'Component/PouchContentParam/BombBag.game__component__PouchContentParam.bgyml': doc({'GetType': 1}),
    }
    return {WORLD_TEMPLATE: template, 'Item_BombBag_Small': source}


class DerivedGameParameterTests(unittest.TestCase):
    def test_derived_bomb_bag_keeps_bag_capacity(self):
        packs = fake_packs()
        raw, _ = build_pack('Obj_Rando_Item_BombBag_Small', packs.get, byml_codec)
        files = sarc(raw)
        components = resolve_components(files, 'Obj_Rando_Item_BombBag_Small', byml_codec)
        table = _table_components(files, components['GameParameterTableRef'], byml_codec)
        self.assertIn('ExpansionMaxNumActor', table)
        capacity = byml_codec.load(files[table['ExpansionMaxNumActor'][1:]])['root']
        self.assertEqual((capacity['GameData'], capacity['MaxNum']), ('Bomb', 20))
        # The pickup keeps the template's own drop parameters.
        self.assertEqual(table['DropBoundParam'],
                         '?GameParameter/DropBoundParam/Obj_Item_Base.game__drop__DropBoundParam.bgyml')

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_real_derived_actors_carry_every_item_parameter(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(os.environ['OOT_NUP'])
        d, members = dictionaries(nup), effective_members(nup)

        def read_pack(name):
            path = f'Pack/Actor/{name}.pack.zs'
            return sarc(decompress(nup.read(members[path]), d)) if path in members else None

        for canonical in ('Item_BombBag_Small', 'Item_BulletBag_Medium', 'Item_Quiver_Large',
                          'Item_Gauntlet_Silver', 'Item_NutBag_Small'):
            source = read_pack(canonical)
            wanted = set(_table_components(source, resolve_components(source, canonical, byml_codec)
                                           .get('GameParameterTableRef'), byml_codec))
            for derived in ('Obj_Rando_' + canonical, 'Shop_Rando_' + canonical):
                with self.subTest(derived=derived):
                    files = sarc(build_pack(derived, read_pack, byml_codec)[0])
                    components = resolve_components(files, derived, byml_codec)
                    table = _table_components(files, components['GameParameterTableRef'], byml_codec)
                    self.assertLessEqual(wanted, set(table))
                    for ref in table.values():
                        if isinstance(ref, str) and ref.startswith('?'):
                            self.assertIn(ref[1:], files)


class SkulltulaDropTests(unittest.TestCase):
    def test_skulltula_drops_are_token_kits(self):
        self.assertEqual(form_actor('Item_Token_Gold', 'world', skulltula_drop=True), 'Obj_Token_Gold')
        self.assertEqual(form_actor('TBox_Rupee_Red', 'world', skulltula_drop=True), 'Obj_Rupee_Red_GS')
        self.assertEqual(form_actor('Obj_Heart_Piece', 'world', skulltula_drop=True), 'Obj_Heart_Piece_GS')
        self.assertEqual(form_actor('Item_Hookshot', 'world', skulltula_drop=True), 'Obj_Rando_Item_Hookshot')
        # Other world locations keep the native pickups.
        self.assertEqual(form_actor('TBox_Rupee_Red', 'world'), 'Obj_Rupee_Red')
        self.assertEqual(form_actor('Obj_Heart_Piece', 'world'), 'Obj_Heart_Piece')

    def test_kit_names_round_trip_and_fit(self):
        from oot_rando.patching.soul_adapter import MAX_ACTOR_NAME
        for canonical in NATIVE_WORLD:
            actor = form_actor(canonical, 'world', skulltula_drop=True)
            with self.subTest(actor=actor):
                if actor == WORLD_TEMPLATE:
                    self.assertFalse(is_derived(actor))
                    continue
                self.assertTrue(is_world_derived(actor))
                self.assertEqual(canonical_of(actor), canonical)
                self.assertLessEqual(len(actor), MAX_ACTOR_NAME)
        self.assertFalse(is_derived('Obj_Token_Gold_GS'))
        self.assertFalse(is_derived('Enemy_Unknown_GS'))

    def test_kit_keeps_token_behaviour_and_always_plays_get_event(self):
        packs = fake_packs()
        packs['TBox_Rupee_Red'] = {
            'Actor/TBox_Rupee_Red.engine__actor__ActorParam.bgyml': doc({'Components': {
                'ModelInfoRef': '?Component/ModelInfo/Obj_Rupee_Red.engine__component__ModelInfo.bgyml',
                'PouchContentRef': '?Component/PouchContentParam/Red.game__component__PouchContentParam.bgyml'}}),
            'Component/ModelInfo/Obj_Rupee_Red.engine__component__ModelInfo.bgyml': doc({'FmdbName': 'Rupee'}),
            'Component/PouchContentParam/Red.game__component__PouchContentParam.bgyml': doc({
                'PlayGetEventManyTimes': False}),
        }
        template = packs[WORLD_TEMPLATE]
        param = f'Actor/{WORLD_TEMPLATE}.engine__actor__ActorParam.bgyml'
        components = byml_codec.load(template[param])['root']['Components']
        components.update({key: f'Work/Component/{key}/Item_Token_Gold.gyml' for key in TOKEN_KIT_REFS})
        template[param] = doc({'Components': components})
        files = sarc(build_pack('Obj_Rupee_Red_GS', packs.get, byml_codec)[0])
        kit = resolve_components(files, 'Obj_Rupee_Red_GS', byml_codec)
        for key in TOKEN_KIT_REFS:
            self.assertEqual(kit[key], f'Work/Component/{key}/Item_Token_Gold.gyml')
        self.assertEqual(kit['ModelInfoRef'], '?Component/ModelInfo/Obj_Rupee_Red.engine__component__ModelInfo.bgyml')
        pouch = byml_codec.load(files[kit['PouchContentRef'][1:]])['root']
        self.assertEqual({key: pouch[key] for key in WORLD_POUCH_FLAGS}, WORLD_POUCH_FLAGS)
        self.assertEqual(pouch['PouchActor'], 'Work/Actor/TBox_Rupee_Red.engine__actor__ActorParam.gyml')


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
class RealPackNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.d, cls.members = dictionaries(cls.nup), effective_members(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read_raw(self, path):
        return self.decompress(self.nup.read(self.members[path]), self.d)

    def read_pack(self, name):
        path = f'Pack/Actor/{name}.pack.zs'
        return sarc(self.read_raw(path)) if path in self.members else None

    def test_soul_actor_name_is_its_own(self):
        """IsGet.<ActorName> is the flag the enemies wait for: it must be the soul's name."""
        from oot_rando.patching import soul_adapter
        item = 'Soul (Skulltula)'
        actor = soul_adapter.soul_actor(item)
        _, new = soul_adapter.build_soul_files(self.read_raw, [item])
        files = sarc(new[f'Pack/Actor/{actor}.pack.zs'][0])
        ref = resolve_components(files, actor, byml_codec)['ActorNameRef']
        self.assertEqual(ref.split('/')[-1].split('.')[0], actor)
        packs = {actor: files}
        derived = sarc(build_pack('Obj_Rando_' + actor, lambda n: packs.get(n) or self.read_pack(n), byml_codec)[0])
        ref = resolve_components(derived, 'Obj_Rando_' + actor, byml_codec)['ActorNameRef']
        self.assertEqual(ref.split('/')[-1].split('.')[0], actor)

    def _setters_after_push(self, raw):
        import ainb
        nodes = ainb.AINB.from_binary(raw).as_dict()['Nodes']
        push = next(n['Node Index'] for n in nodes if n['Name'] == 'OneShotPouchContentPushToPouchOwnInEvent')
        for node in nodes:
            children = [p['Node Index'] for p in node.get('Plugs', {}).get('Child', [])]
            if node['Node Type'] == 'Element_Sequential' and children and children[0] == push:
                return [nodes[i]['Parameters']['Inputs']['String'][0]['Default Value'] for i in children[1:]]
        return []

    def test_soul_get_event_writes_its_flag(self):
        """The game never writes IsGet for new names: the soul's own get event does."""
        from oot_rando.patching import soul_adapter
        from oot_rando.patching.repeatable_adapter import instrument_pickup_event, EVENT_PACK, EVENT_MEMBER
        item = 'Soul (DekuBaba)'
        actor = soul_adapter.soul_actor(item)
        _, new = soul_adapter.build_soul_files(self.read_raw, [item])
        files = sarc(new[f'Pack/Actor/{actor}.pack.zs'][0])
        components = resolve_components(files, actor, byml_codec)
        param = byml_codec.load(files[components['EventPerformerRef'][1:]])['root']
        self.assertEqual(param['EventUniqueAin'], soul_adapter.soul_event_ain(actor))
        member = soul_adapter.soul_event_member(actor)
        self.assertEqual(self._setters_after_push(files[member]), ['IsGet.' + actor])
        # World pickup (gold-token template) runs the same flagged event.
        packs = {actor: files}
        derived = 'Obj_Rando_' + actor
        world = sarc(build_pack(derived, lambda n: packs.get(n) or self.read_pack(n), byml_codec)[0])
        wc = resolve_components(world, derived, byml_codec)
        wparam = byml_codec.load(world[wc['EventPerformerRef'][1:]])['root']
        self.assertEqual(wparam['EventUniqueAin'], soul_adapter.soul_event_ain(actor))
        self.assertEqual(world[member], files[member])
        # First-collection pot pickup of a soul: check flag then soul flag.
        event = sarc(self.read_raw(EVENT_PACK))[EVENT_MEMBER]
        raw = instrument_pickup_event(event, 'Rando.Check.x', 'X.event.root', actor, ('IsGet.' + actor,))
        self.assertEqual(self._setters_after_push(raw), ['Rando.Check.x', 'IsGet.' + actor])

    def test_soul_is_member_of_native_isget_struct(self):
        """Chests add the soul by name (GetPouchContent): only the IsGet struct records it."""
        from oot_rando.patching import soul_adapter
        items = ['Soul (Gohma)', 'Soul (GohmaLarva)']
        modified, _ = soul_adapter.build_soul_files(self.read_raw, items)
        data = byml_codec.load(modified[soul_adapter.GAMEDATA])['root']['Data']
        struct = next(e for e in data['Struct'] if e['Hash'] == soul_adapter.murmur3('IsGet'))
        members = {m['Hash']: m['Value'] for m in struct['DefaultValue']}
        bools = {e['Hash'] for e in data['Bool']}
        for item in items:
            actor = soul_adapter.soul_actor(item)
            flag = soul_adapter.murmur3('IsGet.' + actor)
            self.assertEqual(members.get(soul_adapter.murmur3(actor)), flag)
            self.assertIn(flag, bools)
        original = byml_codec.load(self.read_raw(soul_adapter.GAMEDATA))['root']['Data']
        before = next(e for e in original['Struct'] if e['Hash'] == soul_adapter.murmur3('IsGet'))
        self.assertEqual(struct['DefaultValue'][:len(before['DefaultValue'])], before['DefaultValue'])
        self.assertEqual(len(struct['DefaultValue']), len(before['DefaultValue']) + len(items))

    def test_derived_heart_piece_is_contact_pickup(self):
        for canonical in ('Obj_Heart_Piece', 'Obj_Heart_Container'):
            with self.subTest(canonical=canonical):
                derived = form_actor(canonical, 'world', skulltula_drop=True)
                files = sarc(build_pack(derived, self.read_pack, byml_codec)[0])
                components = resolve_components(files, derived, byml_codec)
                self.assertIn('AutoPickUp', components['AttentionSenderRef'])
                self.assertEqual(components['ActorNameRef'].split('/')[-1].split('.')[0], canonical)
                pouch = byml_codec.load(files[components['PouchContentRef'][1:]])['root']
                self.assertEqual(pouch['PouchActor'], f'Work/Actor/{canonical}.engine__actor__ActorParam.gyml')

    def test_derived_world_pickup_has_no_gold_token_aura(self):
        # Item with its own effect user (Heart Piece) and item without (Hover Boots).
        for canonical, expected in (('Obj_Heart_Piece', 'Obj_Heart_Piece'), ('Item_HoverBoot', None)):
            with self.subTest(canonical=canonical):
                derived = form_actor(canonical, 'world', skulltula_drop=True)
                files = sarc(build_pack(derived, self.read_pack, byml_codec)[0])
                components = resolve_components(files, derived, byml_codec)
                for key in ('ELinkRef', 'SLinkRef'):
                    ref = components.get(key)
                    self.assertNotIn('Token_Gold', ref or '')
                    if expected is None:
                        self.assertIsNone(ref)
                    else:
                        self.assertEqual(byml_codec.load(files[ref[1:]])['root']['UserName'], expected)

    def test_every_skulltula_drop_is_a_token_kit(self):
        """What REALAZK's kit check verifies (pickup_pack/kit.rs, MIT, ae9e4063): the
        token's AI, blackboard, death and life refs, a pouch that always plays the get
        event, and a pickup taken on contact. The kit names are free in the game."""
        token = resolve_components(self.read_pack(WORLD_TEMPLATE), WORLD_TEMPLATE, byml_codec)
        for canonical in NATIVE_WORLD:
            actor = form_actor(canonical, 'world', skulltula_drop=True)
            if actor == WORLD_TEMPLATE:
                continue
            with self.subTest(actor=actor):
                self.assertNotIn(f'Pack/Actor/{actor}.pack.zs', self.members)
                files = sarc(build_pack(actor, self.read_pack, byml_codec)[0])
                components = resolve_components(files, actor, byml_codec)
                for key in TOKEN_KIT_REFS + ('AttentionSenderRef', 'PhysicsRef'):
                    self.assertEqual(components[key], token[key], key)
                pouch = byml_codec.load(files[components['PouchContentRef'][1:]])['root']
                self.assertEqual({key: pouch.get(key) for key in WORLD_POUCH_FLAGS}, WORLD_POUCH_FLAGS)
                self.assertIs(pouch['DefaultAutoGet'], True)
                # The item's own resources (model, pouch, game parameters) travel in the pack.
                source = self.read_pack(canonical)
                for ref in components.values():
                    if isinstance(ref, str) and ref.startswith('?') and ref[1:] in source:
                        self.assertTrue(ref[1:] in files, ref)


if __name__ == '__main__':
    unittest.main()
