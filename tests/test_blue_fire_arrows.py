"""Ice arrows enter native red-ice melting without changing other attacks."""
import _src_path  # noqa: F401
import copy
from collections import Counter
import os
import unittest

from oot_rando.archipelago.bridge import to_ap_yaml
from oot_rando.formats import byml_codec as b
from oot_rando.formats.inspect_resources import sarc
from oot_rando.patching import blue_fire_arrows as a
from oot_rando.patching.soul_adapter import murmur3


class OptionsAndLogic(unittest.TestCase):
    def test_option_roundtrips_through_ap_and_preserves_old_settings(self):
        from oot_rando.logic import rando_options as options
        from oot_rando.archipelago.bridge import ap_option_specs, full_options
        self.assertFalse(options.defaults()['blue_fire_arrows'])
        self.assertNotIn('blue_fire_arrows', options.recorded(options.defaults()))
        self.assertTrue(next(s for s in ap_option_specs() if s['name'] == 'blue_fire_arrows'))
        for enabled in (False, True):
            values = options.validate({'blue_fire_arrows': enabled}, supported_only=True)
            parsed, ignored = options.from_ap_yaml(to_ap_yaml(values))
            self.assertFalse(ignored)
            self.assertEqual(parsed['blue_fire_arrows'], enabled)
            self.assertEqual(full_options({'blue_fire_arrows': enabled})[0]['blue_fire_arrows'], enabled)

    def test_blue_fire_needs_option_bow_arrows_magic_and_adult(self):
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        world = World()
        for enabled in (False, True):
            logic = Logic(world, {'blue_fire_arrows': enabled})
            rule = logic.compile('Blue_Fire')
            for bow in (0, 1):
                for arrows in (0, 1):
                    for magic in (0, 1):
                        state = logic.new_state(Counter({'Bow': bow, 'Ice Arrows': arrows, 'Magic Meter': magic}))
                        for age in ('child', 'adult'):
                            self.assertEqual(bool(rule(state, state.counts, age)),
                                             bool(enabled and bow and arrows and magic and age == 'adult'))
            state = logic.new_state(Counter({'Blue Fire': 1}))
            self.assertTrue(rule(state, state.counts, 'adult'))


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class Resources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.addClassCleanup(cls.nup.stream.close)
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    def read(self, path):
        raw = self.nup.read(self.nup.latest('romfs/' + path))
        return self.decompress(raw, self.d) if path.endswith('.zs') else raw

    def test_only_ice_attack_identifier_changes(self):
        raw = self.read(a.ARROW_PACK)
        before, after = sarc(raw), sarc(a.patch_arrow(raw))
        expected = b.load(before[a.ATTACK])
        rows = expected['root']['AttackParams']
        ice = next(r for r in rows if r['AttackType'] == murmur3('IceArrow'))
        ice.update(AttackIdentifier=a.IDENTIFIER, AttackIdentifierHash=murmur3(a.IDENTIFIER))
        self.assertEqual(b.load(after[a.ATTACK]), expected)
        self.assertEqual({k: v for k, v in before.items() if k != a.ATTACK},
                         {k: v for k, v in after.items() if k != a.ATTACK})

    def test_all_variants_preserve_native_resources_and_are_idempotent(self):
        import ainb
        for path, fix in a.resource_fixes():
            with self.subTest(path=path):
                raw = self.read(path)
                result = fix(raw)
                self.assertEqual(fix(result), result)
                if path == a.ARROW_PACK:
                    continue
                before, after = sarc(raw), sarc(result)
                self.assertEqual(set(before), set(after))
                for k in before:
                    if k != a.AI:
                        self.assertEqual(before[k], after[k], k)
                old = ainb.AINB.from_binary(before[a.AI]).as_dict()
                new = ainb.AINB.from_binary(after[a.AI]).as_dict()
                self.assertEqual(len(new['Nodes']), len(old['Nodes']) + 5)
                for i, node in enumerate(old['Nodes']):
                    if i not in (28, 31, 45):
                        self.assertEqual(node, new['Nodes'][i], i)
                self.assertEqual(old['Commands'], new['Commands'])
                self.assertEqual(old['Blackboard'], new['Blackboard'])
        self.assertNotIn('Pack/Actor/Obj_RedIce_A_03.pack.zs', dict(a.resource_fixes()))

    def test_hit_query_matches_native_interface(self):
        import ainb
        files = sarc(self.read('Pack/AI.Global.Product.111.pack.zs'))
        native = ainb.AINB.from_binary(files['AI/_LocalModule_7498b5490eff.module.ainb']).as_dict()['Nodes'][1]
        patched = sarc(a.patch_ice(self.read(a.ICE_PACKS[0])))
        query = next(n for n in ainb.AINB.from_binary(patched[a.AI]).as_dict()['Nodes']
                     if n['Name'] == 'QuerySensorHitIsHitAttackIdentifier')
        expected = copy.deepcopy(native)
        for key in ('GUID', 'Node Index'):
            expected[key] = query[key]
        expected['Parameters']['Inputs']['String'][0]['Default Value'] = a.IDENTIFIER
        self.assertEqual(query, expected)

    def test_melt_entry_accepts_only_ice_or_correct_flame_and_latches(self):
        """Evaluate the produced entry graph across a hit and a following frame."""
        import ainb
        raw = a.patch_ice(self.read(a.ICE_PACKS[0]))
        nodes = ainb.AINB.from_binary(sarc(raw)[a.AI]).as_dict()['Nodes']
        for attack in ('', 'NormalArrow', 'FireArrow', 'LightArrow', a.IDENTIFIER):
            for flame, target in ((False, False), (True, False), (True, True)):
                blackboard = {0: False}
                current_attack = attack

                def value(p):
                    if p['Node Index'] >= 0:
                        return query(p['Node Index'], p['Output Index'])
                    if 'Blackboard Index' in p:
                        return blackboard[p['Blackboard Index']]
                    return p['Default Value']

                def query(index, output=0):
                    if index == 51:
                        return False if output == 0 else flame
                    if index == 48:
                        return target
                    node = nodes[index]
                    inputs = node['Parameters']['Inputs']
                    if node['Name'] == 'QuerySensorHitIsHitAttackIdentifier':
                        return current_attack == inputs['String'][0]['Default Value']
                    if node['Name'] == 'QueryLogicalDisjunction':
                        return any(value(p) for p in inputs['Bool'])
                    self.fail('Unexpected entry query: ' + node['Name'])

                def selected(index):
                    node = nodes[index]
                    condition = value(node['Parameters']['Inputs']['Bool'][0])
                    return next(p['Node Index'] for p in node['Plugs']['Child']
                                if p['Name'] == str(bool(condition)))

                entered = selected(28) == 45 and selected(45) == 31
                self.assertEqual(entered, attack == a.IDENTIFIER or (flame and target))
                if entered:
                    children = nodes[31]['Plugs']['Child']
                    position = selected(children[0]['Node Index'])
                    self.assertEqual(position, 5 if attack == a.IDENTIFIER else 27)
                    self.assertEqual([p['Node Index'] for p in children[1:]], [43, 41])
                    self.assertEqual([p['Node Index'] for p in nodes[43]['Plugs']['Child']], [30, 42, 4])
                    # Native node 30 sets IsFireHit. The next frame has no attack or message.
                    blackboard[0] = nodes[30]['Parameters']['Inputs']['Bool'][0]['Default Value']
                    current_attack, flame = '', False
                    self.assertEqual(selected(28), 45)
                    self.assertEqual(selected(45), 31)
                    self.assertEqual(selected(children[0]['Node Index']), 5)

    def test_grown_ai_gets_room_in_the_resource_table(self):
        """The shared AI has its own RESTBL entry: once it outgrew it, no red ice loaded."""
        from oot_rando.game.resource_allocations import allocation
        from oot_rando.patching.randomize_kokiri import RESTBL
        from oot_rando.randomizer.randomizer_core import compress_changed, grow_resource_table
        read = lambda path: self.nup.read(self.nup.latest('romfs/' + path))  # noqa: E731
        extra = {p: fix(self.read(p)) for p, fix in a.resource_fixes()}
        files, growths = {}, {}
        compress_changed(extra, files, growths, read, self.d)
        grow_resource_table(files, growths, {}, read, self.d)
        game, seed = self.read(RESTBL), self.decompress(files[RESTBL], self.d)
        size = len(sarc(extra[a.ICE_PACKS[0]])[a.AI])
        self.assertGreater(size, allocation(game, a.AI))   # the bug: the patched AI did not fit
        self.assertGreaterEqual(allocation(seed, a.AI),
                                allocation(game, a.AI) + size - len(sarc(self.read(a.ICE_PACKS[0]))[a.AI]))

    def test_unknown_or_partial_graph_is_rejected(self):
        import ainb
        from oot_rando.patching.ap_mailbox import ainb_to_binary
        files = sarc(self.read(a.ICE_PACKS[0]))
        doc = ainb.AINB.from_binary(files[a.AI]).as_dict()
        doc['Nodes'][30]['Parameters']['Inputs']['Bool'][0]['Default Value'] = False
        with self.assertRaisesRegex(ValueError, 'Unexpected red-ice AI'):
            a.patch_ai(ainb_to_binary(doc))
        doc = ainb.AINB.from_binary(a.patch_ai(files[a.AI])).as_dict()
        doc['Nodes'][62]['Parameters']['Inputs']['String'][0]['Default Value'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            a.patch_ai(ainb_to_binary(doc))


if __name__ == '__main__':
    unittest.main()
