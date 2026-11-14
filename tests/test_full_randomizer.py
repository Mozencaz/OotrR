"""Tests of the complete randomizer. NUP-dependent tests are skipped when absent.

Set OOT_NUP to the local game to run the integration tests.
"""
import _src_path  # noqa: F401  (src on sys.path)
import os
import struct
import unittest
import zlib

from oot_rando.formats import byml_codec
from oot_rando.formats.byml_writer import patch_strings
from oot_rando.randomizer.full_randomizer import DetRandom
from oot_rando.formats.inspect_resources import Byml, sarc
from oot_rando.logic import rando_options
from oot_rando.randomizer.randomizer_core import Settings, settings_identity
from oot_rando.game.resource_allocations import add_resources
from oot_rando.patching.soul_adapter import family_of, murmur3, soul_actor, soul_item

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_deterministic_rng(self):
        a, b = DetRandom('x'), DetRandom('x')
        self.assertEqual([a.below(7) for _ in range(20)], [b.below(7) for _ in range(20)])
        self.assertEqual(sorted(DetRandom('y').shuffle(range(10))), list(range(10)))

    def test_options_refuse_unsupported(self):
        values = rando_options.defaults()
        rando_options.validate(values, supported_only=True)
        for name, value in (('bridge', 'open'), ('shuffle_smallkeys', 'keysanity'), ('trials', 0),
                            ('shuffle_smallkeys', 'dungeon')):
            with self.assertRaises(ValueError):
                rando_options.validate(dict(values, **{name: value}), supported_only=True)
        with self.assertRaises(ValueError):
            rando_options.validate({'unknown': 1})
        for key in rando_options.PRESETS:
            rando_options.validate(rando_options.preset(key), supported_only=True)

    def test_ap_yaml_roundtrip_and_off(self):
        values = rando_options.preset('everything')
        imported, ignored = rando_options.from_ap_yaml(rando_options.to_ap_yaml(values))
        self.assertEqual(imported, values)
        self.assertEqual(ignored, [])
        imported, ignored = rando_options.from_ap_yaml(
            'Ocarina of Time:\n  shopsanity: off\n  bridge: {open: 50}\n  foo: 1\n')
        self.assertEqual(imported['shopsanity'], 'off')
        self.assertEqual(imported['bridge'], 'open')
        self.assertTrue(any('bridge' in m for m in ignored) and any('foo' in m for m in ignored))

    def test_settings_identity_unchanged_without_full(self):
        settings = Settings('seed')
        self.assertNotIn('full', settings.to_dict())
        full = Settings('seed', randomize_chests=False, full=rando_options.defaults())
        self.assertIn('full', full.to_dict())
        self.assertNotEqual(settings_identity(settings), settings_identity(full))
        with self.assertRaises(ValueError):
            Settings('seed', randomize_chests=True, full=rando_options.defaults()).validate()

    def test_byml_codec_types_and_sarc(self):
        document = {'endian': '>', 'version': 7, 'root': {
            'a': [1, byml_codec.U32(4000000000), byml_codec.I64(-5), byml_codec.U64(1 << 40),
                  1.5, byml_codec.F64(2.25), True, 'txt', None], 'b': {'c': 'txt'}, 'd': {'c': 'txt'}}}
        raw = byml_codec.dump(document)
        loaded = byml_codec.load(raw)
        self.assertEqual(loaded['root'], document['root'])
        self.assertEqual([type(v) for v in loaded['root']['a'][:6]],
                         [int, byml_codec.U32, byml_codec.I64, byml_codec.U64, float, byml_codec.F64])
        self.assertEqual(Byml(raw).root['b'], {'c': 'txt'})
        files = {'A/x.bgyml': raw, 'B/y.bin': b'1234567'}
        self.assertEqual(sarc(byml_codec.build_sarc(files)), files)

    def test_presence_bool_leaves(self):
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': [{'Gyaml': 'Enemy_Keese', 'Hash': 1}]}})
        patched = patch_strings(raw, [
            {'path': ('Actors', 0, 'Presence', 'FlagName'), 'before': None, 'after': 'IsGet.Item_Soul_Keese'},
            {'path': ('Actors', 0, 'Presence', 'IsNegation'), 'before': None, 'after': False},
            {'path': ('Actors', 0, 'Presence', 'IsCheckLazy'), 'before': None, 'after': False}])
        self.assertEqual(Byml(patched).root['Actors'][0]['Presence'],
                         {'FlagName': 'IsGet.Item_Soul_Keese', 'IsNegation': False, 'IsCheckLazy': False})
        with self.assertRaises(ValueError):
            patch_strings(raw, [{'path': ('Actors', 0, 'Gyaml'), 'before': 'Enemy_Keese', 'after': True}])

    def test_restbl_add_entries(self):
        names = b'x' * 160 + struct.pack('<I', 5)
        entries = sorted([(10, 1), (zlib.crc32(b'Old/File'), 7)])
        raw = b'RESTBL' + struct.pack('<IIII', 1, 160, 2, 1) + b''.join(struct.pack('<II', *e) for e in entries) + names
        out, records = add_resources(raw, {'Pack/Actor/Item_Soul_A.pack.zs': 8192})
        count = struct.unpack_from('<I', out, 14)[0]
        table = [struct.unpack_from('<II', out, 22 + i * 8) for i in range(count)]
        self.assertEqual(count, 3)
        self.assertEqual(table, sorted(table))
        self.assertIn((zlib.crc32(b'Pack/Actor/Item_Soul_A.pack'), 8192), table)
        self.assertTrue(out.endswith(names))
        with self.assertRaises(ValueError):
            add_resources(raw, {'Old/File.zs': 1})

    def test_soul_families(self):
        self.assertEqual(murmur3('IsGet.Item_Hookshot'), 4288212312)
        self.assertEqual(family_of('Enemy_Keese_Fire'), 'Keese')
        self.assertEqual(family_of('Enemy_Dodongo'), 'Dodongo')
        self.assertEqual(family_of('Enemy_DungeonBoss_Dodongo'), 'KingDodongo')
        self.assertEqual(family_of('Enemy_Skulltula_Truth'), 'Skulltula')
        for excluded in ('Enemy_Skulltula_Gold', 'Enemy_Poe', 'Enemy_Scrub_Business', 'Enemy_Keese_Dictionary',
                         'Enemy_MiddleBoss_IronKnuckle_Nabooru', 'Enemy_DungeonBoss_Ganondorf'):
            self.assertIsNone(family_of(excluded), excluded)
        self.assertEqual(soul_actor(soul_item('Region:ForestTemple')), 'Item_Soul_R_ForestTemple')


class RoomLocks(unittest.TestCase):
    @staticmethod
    def enemy(hash_, locks):
        return {'resource': 'r', 'index': int(hash_), 'actor': 'Enemy_X', 'folder': 'F', 'hash': hash_,
                'presence': None, 'locks': locks}

    def test_primary_soul_gates_doors_and_others_spawn(self):
        from oot_rando.patching.soul_adapter import resolve_room_locks
        door = {'resource': 'r', 'index': 9, 'hash': '9', 'actor': 'Obj_SwitchShutter_A_02', 'presence': None}
        lock = {'counter': 'r#1', 'doors': [door]}
        candidates = [(self.enemy('1', [lock]), 'Keese', None), (self.enemy('2', [lock]), 'Keese', None),
                      (self.enemy('3', [lock]), 'Stalfos', None), (self.enemy('4', []), 'Stalfos', None)]
        kept, doors = resolve_room_locks(candidates)
        self.assertEqual([c[0]['hash'] for c in kept], ['1', '2', '4'])   # Stalfos of the room always spawns
        self.assertEqual([(d['hash'], d['soul'], d['flag']) for d in doors],
                         [('9', 'Keese', 'IsGet.Item_Soul_Keese')])

    def test_unpatchable_rooms_never_strand(self):
        from oot_rando.patching.soul_adapter import resolve_room_locks
        locked = {'resource': 'r', 'index': 9, 'hash': '9', 'actor': 'Obj_SwitchShutter_A_02',
                  'presence': {'FlagName': 'x'}}
        no_door = {'counter': 'r#2', 'doors': []}
        kept, doors = resolve_room_locks([(self.enemy('1', [{'counter': 'r#1', 'doors': [locked]}]), 'Keese', None),
                                          (self.enemy('2', [no_door]), 'Keese', None)])
        self.assertEqual((kept, doors), ([], []))

    def test_shared_door_conflict(self):
        from oot_rando.patching.soul_adapter import resolve_room_locks
        door = {'resource': 'r', 'index': 9, 'hash': '9', 'actor': 'Obj_SwitchShutter_A_02', 'presence': None}
        a, b = {'counter': 'r#1', 'doors': [door]}, {'counter': 'r#2', 'doors': [door]}
        kept, doors = resolve_room_locks([(self.enemy('1', [a]), 'Keese', None),
                                          (self.enemy('2', [b]), 'Stalfos', None)])
        self.assertEqual([c[1] for c in kept], ['Keese'])
        self.assertEqual([d['soul'] for d in doors], ['Keese'])

    def test_enemy_linked_straight_to_its_shutters_is_a_lock(self):
        # Deku Tree: the scrub links to its shutters itself (no Obj_EnemyCounter).
        from oot_rando.game.remake_world import enemy_counter_locks
        root = {'Actors': [
            {'Gyaml': 'Enemy_Scrub_Deku', 'Hash': 1, 'Links': [{'Dst': 2, 'Name': 'Reference'}]},
            {'Gyaml': 'Obj_SwitchShutter_A_02', 'Hash': 2},
            {'Gyaml': 'Obj_SwitchShutter_A_01', 'Hash': 3, 'Links': [{'Dst': 1, 'Name': 'Reference'}]},
            {'Gyaml': 'Enemy_Keese', 'Hash': 4}]}
        locks = enemy_counter_locks('r', root)
        self.assertEqual(set(locks), {1})
        self.assertEqual([(d['hash'], d['index']) for d in locks[1][0]['doors']], [('2', 1), ('3', 2)])
        self.assertTrue(locks[1][0]['direct'])

    def test_direct_locks_stay_out_of_the_scan_fingerprint(self):
        # Earlier Archipelago patches stay valid: the bound enemies and the logic are unchanged.
        from oot_rando.archipelago.bridge import scan_fingerprint
        counter = {'counter': 'r#9', 'doors': [{'hash': '2'}]}
        before = [{'hash': '1', 'locks': [counter]}, {'hash': '3', 'locks': []}]
        after = [{'hash': '1', 'locks': [counter, {'counter': 'r#1', 'direct': True, 'doors': [{'hash': '2'}]}]},
                 {'hash': '3', 'locks': [{'counter': 'r#3', 'direct': True, 'doors': [{'hash': '4'}]}]}]
        self.assertEqual(scan_fingerprint([], after, {}), scan_fingerprint([], before, {}))
        self.assertNotEqual(scan_fingerprint([], [{'hash': '1', 'locks': []}], {}), scan_fingerprint([], before, {}))


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.logic.world import World
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.remake_world import scan_maps
        from oot_rando.game.world_maps import effective_members
        cls.data = World()
        nup = Nup(NUP)
        try:
            _, cls.groups, cls.enemies = scan_maps(nup, dictionaries(nup), effective_members(nup))
        finally:
            nup.stream.close()

    def run_plan(self, overrides, seed):
        from oot_rando.randomizer import full_randomizer
        options = dict(rando_options.defaults(), **overrides)
        return full_randomizer.plan(self.data, options, self.groups, self.enemies, seed, True)

    def assert_valid(self, result, options):
        from oot_rando.randomizer import full_randomizer
        from oot_rando.game.remake_world import PROGRESSIVE
        items = {p['id']: p['item'] for p in result['placements']}
        replay = full_randomizer.replay(self.data, dict(rando_options.defaults(), **options),
                                        self.groups, self.enemies, items)
        self.assertTrue(replay['beatable'])
        self.assertEqual(replay['unreachable'], [])
        # Every progressive copy is its own token, as the replay names them.
        from oot_rando.game.item_forms import canonical_of, is_derived
        from oot_rando.patching.progressive import token_family
        self.assertEqual(replay['progressive'], result['progressive'])
        tokens = result['progressive']['tokens']
        for p in result['placements']:
            canonical = canonical_of(p['after']) if is_derived(p['after']) else p['after']
            self.assertEqual(token_family(canonical), p['item'] if p['item'] in PROGRESSIVE else None, p)
            self.assertEqual(canonical == tokens.get(p['id']), p['item'] in PROGRESSIVE, p)
        every = list(tokens.values()) + [n['token'] for n in result['progressive']['natives']]
        self.assertEqual(len(set(every)), len(every))

    def test_presets_beatable_and_ordered(self):
        for overrides in ({}, rando_options.PRESETS['prudent']['values'],
                          {'shuffle_enemy_spawns': 'bosses'},
                          rando_options.PRESETS['everything']['values']):
            for seed in ('t1', 't2'):
                with self.subTest(overrides=overrides, seed=seed):
                    self.assert_valid(self.run_plan(overrides, seed), overrides)

    def test_hookshot_copies_are_tokens(self):
        # Issue #23: no copy carries a fixed level; the first one found gives the hookshot.
        for seed in ('h1', 'h2'):
            result = self.run_plan({}, seed)
            copies = sorted(p['id'] for p in result['placements'] if p['item'] == 'Progressive Hookshot')
            self.assertEqual([result['progressive']['tokens'][g] for g in copies],
                             ['Item_Prog_Hookshot_1', 'Item_Prog_Hookshot_2'])

    def test_deterministic(self):
        a = self.run_plan({'shuffle_enemy_spawns': 'bosses'}, 'same')
        b = self.run_plan({'shuffle_enemy_spawns': 'bosses'}, 'same')
        self.assertEqual(a['placements'], b['placements'])


if __name__ == '__main__':
    unittest.main()
