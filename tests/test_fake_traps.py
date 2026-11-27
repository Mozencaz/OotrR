"""Fake item traps (``fake_item_traps``). NUP-dependent tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest
from collections import Counter

from oot_rando.catalog import traps as t
from oot_rando.logic import rando_options

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_names_round_trip_and_fit_the_game(self):
        from oot_rando.game.remake_world import actor_item, item_actor
        from oot_rando.patching.soul_adapter import MAX_ACTOR_NAME
        traps = [t.trap_item(item) for item in t.ALL_TRAPPED] + [t.trap_item(item, 2) for item in t.TRAPPED]
        actors = [t.trap_actor(trap) for trap in traps]
        self.assertEqual(len(set(actors)), len(actors))
        self.assertEqual([a for a in actors + [t.SENSOR_ACTOR] if len(a) > MAX_ACTOR_NAME], [])
        self.assertEqual(t.trap_actor('Trap: Bow #2'), 'Item_Trap_Bow2')
        for trap in traps:
            item = t.trapped_item(trap)
            self.assertIn(item, t.ALL_TRAPPED)
            self.assertEqual(item_actor(trap, 'KokiriForest'), t.trap_actor(trap))
            self.assertEqual(actor_item(t.trap_actor(trap), 'KokiriForest'), trap)
        self.assertFalse(t.is_trap_actor('Item_Trap_Unknown'))
        self.assertFalse(t.is_trap_actor('Item_Trap_ForestMedallion2'))     # extras: one copy
        for wrong in ('Trap: Rupees (5)', 'Trap: Bow #3', 'Trap: Forest Medallion #2', 'Bow'):
            with self.assertRaises(ValueError):
                t.trapped_item(wrong)
        with self.assertRaises(ValueError):
            t.trap_item('Rupees (5)')

    def test_traps_go_into_chests_and_pickups_only(self):
        from oot_rando.game.item_forms import can_take
        actor = t.trap_actor(t.trap_item('Progressive Hookshot'))
        self.assertTrue(can_take(actor, 'chest'))
        self.assertTrue(can_take(actor, 'world'))
        for form in ('shop', 'event'):
            self.assertFalse(can_take(actor, form), form)

    def test_placed_traps_include_pickups(self):
        from oot_rando.game.item_forms import WORLD_PREFIX
        from oot_rando.patching.fake_traps import placed_traps
        placements = [{'after': 'Item_Trap_Bow'}, {'after': WORLD_PREFIX + 'Item_Trap_Hookshot2'},
                      {'after': WORLD_PREFIX + 'Item_Hookshot'}, {'after': 'Item_Hookshot'}]
        self.assertEqual(placed_traps(placements), ['Trap: Bow', 'Trap: Progressive Hookshot #2'])

    def test_levels(self):
        pool = ['Bow', 'Progressive Hookshot', 'Rupees (5)']
        self.assertEqual(t.planned_traps(pool, 'none'), [])
        self.assertEqual(t.planned_traps(pool, 'some'), ['Trap: Progressive Hookshot', 'Trap: Bow'])
        plentiful = t.planned_traps(pool, 'plentiful')
        self.assertEqual(plentiful[:2], ['Trap: Progressive Hookshot', 'Trap: Bow'])
        self.assertEqual(plentiful[-2:], ['Trap: Progressive Hookshot #2', 'Trap: Bow #2'])
        # Every medallion, stone and song, in the pool or not.
        self.assertEqual(plentiful[2:-2], [t.trap_item(i) for i in t.EXTRA_TRAPPED])
        self.assertEqual(len(t.EXTRA_TRAPPED), 9 + 12)

    def test_each_trap_replaces_the_cheapest_filler(self):
        from oot_rando.randomizer.full_randomizer import add_fake_traps
        pool = ['Bow', 'Rupees (200)', 'Progressive Hookshot', 'Rupee (1)', 'Bow', 'Rupees (5)', 'Iron Boots']
        result = add_fake_traps(pool, Counter({'Rupee (1)': 1, 'Rupees (5)': 1, 'Rupees (200)': 1}))
        self.assertEqual(len(result), len(pool))
        self.assertEqual(sorted(i for i in result if t.is_trap_item(i)),
                         ['Trap: Bow', 'Trap: Iron Boots', 'Trap: Progressive Hookshot'])   # one per item
        self.assertNotIn('Rupee (1)', result)
        self.assertNotIn('Rupees (5)', result)
        self.assertNotIn('Rupees (200)', result)
        self.assertEqual(Counter(result)['Bow'], 2)      # real copies are kept

    def test_most_important_traps_first_when_filler_runs_out(self):
        from oot_rando.randomizer.full_randomizer import add_fake_traps
        pool = ['Iron Boots', 'Progressive Hookshot', 'Bow', 'Rupees (5)']
        result = add_fake_traps(pool, Counter({'Rupees (5)': 1}))
        self.assertEqual([i for i in result if t.is_trap_item(i)], ['Trap: Progressive Hookshot'])
        self.assertEqual(add_fake_traps(pool, Counter()), pool)

    def test_option_off_keeps_seed_identity(self):
        values = rando_options.defaults()
        self.assertEqual(values['fake_item_traps'], 'none')
        self.assertNotIn('fake_item_traps', rando_options.recorded(values))
        for level in ('some', 'plentiful'):
            self.assertIn('fake_item_traps', rando_options.recorded(dict(values, fake_item_traps=level)))

    def test_not_offered_to_archipelago(self):
        from oot_rando.archipelago.bridge import ap_option_specs, full_options
        self.assertNotIn('fake_item_traps', {spec['name'] for spec in ap_option_specs()})
        self.assertEqual(full_options({})[0]['fake_item_traps'], 'none')

    def test_texts(self):
        from oot_rando.patching.fake_traps import trap_texts
        self.assertIn('trap', trap_texts('USen')[0])
        self.assertIn('piège', trap_texts('EUfr')[0])


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class Game(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(NUP)
        d = dictionaries(cls.nup)
        members = effective_members(cls.nup)
        cls.members = members
        cls.read = staticmethod(lambda path: decompress(cls.nup.read(members[path]), d))

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def test_sensor_freezes_characters_around_link(self):
        from oot_rando.formats import byml_codec
        from oot_rando.formats.inspect_resources import sarc
        from oot_rando.patching import fake_traps as f
        pack = sarc(f.build_sensor_pack(self.read))
        name = t.SENSOR_ACTOR
        attack = byml_codec.load(pack[f.ATTACK_PARAM.format(name)])['root']['AttackParams']
        self.assertEqual([a['DamageElements'] for a in attack], [[f.FROZEN_ELEMENT]])
        sensor = byml_codec.load(pack[f.SENSOR_PARAM.format(name)])['root']
        # Hits the player as an enemy attack (the Sun's Song sensor hits enemies only).
        self.assertEqual(sensor['EnableLayerHitMask'], 'HitToPlayer')
        self.assertEqual(sensor['LayerSensor'], 'EnemyAttack')
        self.assertNotIn('SubLayerSensor', sensor)
        contacts = byml_codec.load(pack[f.CONTROLLER_SET.format(name)])['root']['CColSensorNamePathAry']
        self.assertEqual([c['FilePath'] for c in contacts],
                         ['Work/' + f.PLAYER_CONTACT[:-len('.bgyml')] + '.gyml'])
        self.assertEqual(byml_codec.load(pack[f.PLAYER_CONTACT])['root']['LayerHitMask'], 'EnemyAttackReceipt')
        # The same affiliation as the game's freezing objects (trap chest, Twinrova's ice field).
        chest = byml_codec.load(sarc(self.read(f'Pack/Actor/{f.TRAP_CHEST}.pack.zs'))[
            f'Actor/{f.TRAP_CHEST}.engine__actor__ActorParam.bgyml'])['root']['Components']
        components = byml_codec.load(pack[f'Actor/{name}.engine__actor__ActorParam.bgyml'])['root']['Components']
        self.assertEqual(components['AffiliationRef'], chest['AffiliationRef'])
        # Its own AI: wait for the end of the get event, attack for a while, then die.
        import ainb
        self.assertEqual(components['AIInfoRef'], '?' + f.SENSOR_AI_INFO.format(name))
        self.assertEqual(byml_codec.load(pack[f.SENSOR_AI_INFO.format(name)])['root'],
                         {'RootAIRef': f'Work/AI/Root/{name}.root.ain'})
        nodes = ainb.AINB.from_binary(pack[f.SENSOR_AI.format(name)]).as_dict()['Nodes']
        self.assertEqual([n['Name'] for n in nodes], ['', 'ExecuteGenericCounter', '', 'ExecuteGenericCounter',
                                                      'ExecuteSensorHitSetupAttack', 'OneShotDeathRequestDeath'])
        self.assertEqual([c['Node Index'] for c in nodes[0]['Plugs']['Child']], [1, 2, 5])
        self.assertEqual([c['Node Index'] for c in nodes[2]['Plugs']['Child']], [3, 4])
        frames = [next(p['Default Value'] for p in nodes[i]['Properties']['Float'] if p['Name'] == 'BaseFrameTime')
                  for i in (1, 3)]
        self.assertEqual(frames, [f.SENSOR_WAIT_FRAMES, f.SENSOR_ATTACK_FRAMES])
        self.assertEqual(components['DeathRef'], f.DEATH)
        # The Sun's Song keeps the shared condition sensor AI.
        self.assertEqual(pack[f.TEMPLATE_AI], sarc(self.read(f'Pack/Actor/{f.SENSOR_TEMPLATE}.pack.zs'))[f.TEMPLATE_AI])
        shape = byml_codec.load(pack[f.SHAPE_PARAM.format(name)])['root']['Cylinder'][0]
        self.assertEqual(shape['Radius'], f.SENSOR_RADIUS)
        # Nothing of the Sun's Song left: no effect link, no old name.
        self.assertFalse([k for k in pack if f.SENSOR_TEMPLATE in k])
        params = byml_codec.load(pack[f'Actor/{name}.engine__actor__ActorParam.bgyml'])['root']['Components']
        self.assertNotIn('ELinkRef', params)
        self.assertTrue(all(f.SENSOR_TEMPLATE not in str(v) for v in params.values()))

    def test_every_trap_builds_with_the_real_name(self):
        from oot_rando.formats import msbt
        from oot_rando.formats.inspect_resources import sarc
        from oot_rando.patching import fake_traps as f
        from oot_rando.patching.soul_adapter import MESSAGE_FILE, RSDB_FILES
        traps = [t.trap_item(item) for item in t.TRAPPED]
        archive = 'Mals/USen.Product.110.sarc.zs'
        modified, new = f.build_trap_files(self.read, traps, [archive])
        message = msbt.load(sarc(modified[archive])[MESSAGE_FILE])
        native = msbt.load(sarc(self.read(archive))[MESSAGE_FILE])
        for trap in traps:
            actor = t.trap_actor(trap)
            self.assertIn(f'Pack/Actor/{actor}.pack.zs', new)
            pouch = f.pouch_name(self.read, t.model_actor(trap))
            self.assertEqual(message.get(actor + '_Name'), native.get(pouch + '_Name'), trap)
            self.assertIn(b'trap', message.get(actor + '_GetMessage'))
        self.assertIn(f'Pack/Actor/{t.SENSOR_ACTOR}.pack.zs', new)
        # Child Link can be frozen (vanilla: adult only); nothing else in his pack changes.
        from oot_rando.formats import byml_codec
        child,native_child = sarc(modified[f.CHILD_PACK]), sarc(self.read(f.CHILD_PACK))
        self.assertEqual([k for k in native_child if child[k] != native_child[k]], [f.CHILD_CONDITION])
        self.assertTrue(byml_codec.load(child[f.CHILD_CONDITION])['root']['IsEnableFrozen'])
        self.assertFalse(byml_codec.load(native_child[f.CHILD_CONDITION])['root']['IsEnableFrozen'])
        # ... with adult Link's ice shell; the other users and shared tables do not change.
        from oot_rando.formats import xlink
        native, shell = self.read(f.ELINK), modified[f.ELINK]
        for key, source in f.FROZEN_CALLS.items():
            adult = xlink.call_tree(native, f.ADULT_EFFECTS, source)
            self.assertNotEqual(xlink.call_tree(native, f.CHILD_EFFECTS, (key,)), adult)
            self.assertEqual(xlink.call_tree(shell, f.CHILD_EFFECTS, (key,)), adult)
        # Whole-body shell: 16 poses and the two cap pieces, under no grid.
        tree = xlink.call_tree(shell, f.CHILD_EFFECTS, ('Condition_Frozen',))
        self.assertEqual((len(tree), tree[0][5]), (20, xlink.BLEND))
        self.assertNotIn(xlink.GRID, [row[5] for row in tree])
        self.assertEqual(f.child_ice_shell(shell), shell)
        before, after = xlink.Xlink(native), xlink.Xlink(shell)
        self.assertEqual(native[before.condition_pos:], shell[after.condition_pos:])
        child = before.user(f.CHILD_EFFECTS)
        self.assertEqual(child.build(), native[child.start:child.end])
        for name_hash, start in zip(before.hashes, before.offsets):
            moved = after.offsets[before.hashes.index(name_hash)]
            if start != child.start:
                self.assertEqual(native[start:before.ends[start]], shell[moved:after.ends[moved]])
        for table in f.RSDB_TABLES:
            rows = {r['__RowId'] for r in byml_codec.load(modified[RSDB_FILES[table]])['root']}
            self.assertIn(t.SENSOR_ACTOR, rows)

    def test_hook_freezes_once_per_trap(self):
        from oot_rando.formats.evfl_tools import params_by_event, parse_flow
        from oot_rando.patching.fake_traps import add_trap_hook, trap_records
        from oot_rando.patching.key_adapter import ACTION_GUIDE_FLOW
        raw = self.read(ACTION_GUIDE_FLOW)
        records = trap_records(['Trap: Bow', 'Trap: Progressive Hookshot'])
        patched, report = add_trap_hook(raw, records)
        flow = parse_flow(patched)
        params = params_by_event(flow)
        vanilla = params_by_event(parse_flow(raw))
        self.assertEqual({k: v for k, v in params.items() if k in vanilla}, vanilla)
        self.assertEqual(params['RandoTrapFreeze_Bow'], {'ActorName': t.SENSOR_ACTOR})
        self.assertEqual(params['RandoTrapGot_Bow'], {'GameDataName': 'IsGet.Item_Trap_Bow', 'Index': -1})
        self.assertEqual(params['RandoTrapSprung_Hookshot'],
                         {'GameDataName': 'RandoTrap.Hookshot', 'Value': True, 'Index': -1})
        events = {e.name: e for e in flow.flowchart.events}
        # Got and not sprung → sprung, then the sensor; sprung → the next check.
        done = events['RandoTrapDone_Bow'].data
        self.assertEqual(done.cases[0].v.name, 'RandoTrapGot_Hookshot')
        self.assertEqual(done.cases[1].v.name, 'RandoTrapSprung_Bow')
        self.assertEqual(events['RandoTrapSprung_Bow'].data.nxt.v.name, 'RandoTrapFreeze_Bow')
        self.assertEqual([r['start'] for r in report], ['RandoTrapGot_Bow', 'RandoTrapGot_Hookshot'])
        with self.assertRaises(ValueError):
            add_trap_hook(patched, records)

    def test_plan_places_one_trap_per_major_item_in_chests(self):
        from oot_rando.logic.world import World
        from oot_rando.randomizer import full_randomizer
        from game_fixture import scan_maps
        _, groups, enemies = scan_maps()
        options = dict(rando_options.defaults(), fake_item_traps='some')
        result = full_randomizer.plan(World(), options, groups, enemies, 'traps', True)
        placed = [p for p in result['placements'] if t.is_trap_item(p['item'])]
        self.assertTrue(placed)
        self.assertTrue(all(p['form'] == 'chest' and p['after'] == t.trap_actor(p['item']) for p in placed))
        items = Counter(p['item'] for p in result['placements'])
        for p in placed:
            self.assertEqual(items[p['item']], 1)
            self.assertGreaterEqual(items[t.trapped_item(p['item'])], 1)   # the real item is there too
        _, groups, enemies = scan_maps()
        plain = full_randomizer.plan(World(), rando_options.defaults(), groups, enemies, 'traps', True)
        self.assertEqual(len(plain['placements']), len(result['placements']))
        self.assertFalse([p for p in plain['placements'] if t.is_trap_item(p['item'])])


    def test_plentiful_plan_uses_pickups_too(self):
        from oot_rando.game.item_forms import canonical_of, is_derived
        from oot_rando.logic.world import World
        from oot_rando.randomizer import full_randomizer
        from game_fixture import scan_world
        _, groups, enemies, extra = scan_world()
        options = dict(rando_options.defaults(), fake_item_traps='plentiful', tokensanity='all',
                       shuffle_freestanding_items='all')
        result = full_randomizer.plan(World(), options, groups, enemies, 'traps', True, extra=extra)
        placed = [p for p in result['placements'] if t.is_trap_item(p['item'])]
        self.assertEqual(Counter(p['form'] for p in placed).keys() - {'chest', 'world'}, set())
        self.assertIn('world', {p['form'] for p in placed})
        for p in placed:
            after = canonical_of(p['after']) if is_derived(p['after']) else p['after']
            self.assertEqual(after, t.trap_actor(p['item']))
        items = Counter(p['item'] for p in placed)
        self.assertEqual(max(items.values()), 1)       # each copy is its own trap
        self.assertIn('Trap: Progressive Hookshot #2', items)
        self.assertIn('Trap: Forest Medallion', items)
        self.assertIn('Trap: Prelude of Light', items)


if __name__ == '__main__':
    unittest.main()
