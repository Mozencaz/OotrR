"""Key rings, dungeon-specific boss keys and one-time business scrubs.

NUP-dependent tests need OOT_NUP.
"""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.logic import rando_options
from oot_rando.patching import key_adapter as k

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_key_items_round_trip(self):
        from oot_rando.game.remake_world import actor_item, item_actor
        self.assertEqual(item_actor('Small Key Ring (Forest Temple)', 'HyruleField'), 'Item_KeyRing_ForestTemple')
        self.assertEqual(actor_item('Item_KeyRing_Ganon', ''), 'Small Key Ring (Ganons Castle)')
        self.assertEqual(actor_item('Item_BossKey_WaterTemple', 'KokiriForest'), 'Boss Key (Water Temple)')
        # Generic remake keys stay credited to the dungeon they are found in.
        self.assertEqual(item_actor('Boss Key (Fire Temple)', 'FireTemple'), 'Item_Dungeon_BossKey')
        self.assertFalse(k.is_key_actor('Item_Dungeon_SmallKey'))

    def test_generated_actor_names_fit_the_game(self):
        # 13/11 in game: generated actors of 30 and 33 characters crashed their item get.
        from oot_rando.game.remake_world import FOLDER_DUNGEON, actor_item
        from oot_rando.patching.key_adapter import RING_DUNGEONS, BOSS_KEY_DUNGEONS, ring_actor, boss_actor
        from oot_rando.patching.soul_adapter import MAX_ACTOR_NAME, REGION_CODES, soul_actor, soul_item
        names = [ring_actor(f) for f in RING_DUNGEONS] + [boss_actor(f) for f in BOSS_KEY_DUNGEONS]
        names += [soul_actor(soul_item('Region:' + folder))
                  for folder in sorted(set(FOLDER_DUNGEON) | set(REGION_CODES))]
        self.assertEqual([n for n in names if len(n) > MAX_ACTOR_NAME], [])
        self.assertEqual(len(set(names)), len(names))
        for folder in RING_DUNGEONS:
            self.assertEqual(actor_item(ring_actor(folder), ''), f'Small Key Ring ({FOLDER_DUNGEON[folder]})')

    def test_records_name_the_dungeon_struct(self):
        records = k.key_records(['Small Key Ring (Fire Temple)', 'Boss Key (Shadow Temple)'])
        ring = next(r for r in records if r['kind'] == 'ring')
        boss = next(r for r in records if r['kind'] == 'boss')
        self.assertEqual((ring['gamedata'], ring['count']), ('DungeonInfo.FireTemple.SmallKeyNum', 8))
        self.assertEqual(ring['applied'], 'RandoKeyRing.FireTemple')
        self.assertEqual(boss['gamedata'], 'DungeonInfo.ShadowTemple.IsGetBossKey')
        self.assertIn('Trousseau', k.key_texts('Item_KeyRing_FireTemple', 'EUfr')['Name'])

    def test_ring_counts_as_every_key_of_its_dungeon(self):
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        logic = Logic(World())
        logic.bundles['Small Key Ring (Forest Temple)'] = ('Small Key (Forest Temple)', 5)
        state = logic.new_state({'Small Key Ring (Forest Temple)': 1})
        self.assertEqual(state.counts['Small Key (Forest Temple)'], 5)
        other = logic.new_state()
        other.add('Small Key Ring (Forest Temple)')
        self.assertEqual(other.counts['Small Key (Forest Temple)'], 5)
        self.assertEqual(other.copy().counts['Small Key (Forest Temple)'], 5)   # never counted twice

    def test_options_tie_rings_and_moved_small_keys(self):
        values = rando_options.defaults()
        for small, rings in (('keysanity', 'off'), ('dungeon', 'off'), ('vanilla', 'all')):
            with self.assertRaises(ValueError):
                rando_options.validate(dict(values, shuffle_smallkeys=small, key_rings=rings), supported_only=True)
        for small in ('dungeon', 'any_dungeon', 'overworld', 'keysanity'):
            rando_options.validate(dict(values, shuffle_smallkeys=small, key_rings='all'), supported_only=True)
        for boss in ('any_dungeon', 'keysanity'):
            rando_options.validate(dict(values, shuffle_bosskeys=boss), supported_only=True)
        for price in ('low', 'regular', 'random'):
            rando_options.validate(dict(values, shuffle_scrubs=price), supported_only=True)

    def test_scrub_prices(self):
        from oot_rando.game.extra_sources import scrub_price
        entry = {'id': 'scrub#HF Deku Scrub Grotto', 'price': 100}
        self.assertEqual(scrub_price('low', 'seed', entry), 10)
        self.assertEqual(scrub_price('regular', 'seed', entry), 100)
        price = scrub_price('random', 'seed', entry)
        self.assertTrue(10 <= price <= 99)
        self.assertEqual(price, scrub_price('random', 'seed', entry))


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class NupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(NUP)
        cls.members = effective_members(cls.nup)
        cls.dictionaries = dictionaries(cls.nup)
        cls.read = lambda self, path: decompress(self.nup.read(self.members[path]), self.dictionaries)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def test_dungeon_struct_exists_for_every_key_dungeon(self):
        from oot_rando.patching.soul_adapter import GAMEDATA
        items = ([k.ring_item(f) for f in k.RING_DUNGEONS]
                 + [f'Boss Key ({k.FOLDER_DUNGEON[f]})' for f in k.BOSS_KEY_DUNGEONS])
        k.check_dungeon_data(self.read(GAMEDATA), k.key_records(items))
        with self.assertRaises(ValueError):
            k.check_dungeon_data(self.read(GAMEDATA), [{'kind': 'ring', 'gamedata': 'DungeonInfo.Nowhere.SmallKeyNum'}])

    def test_hook_checks_each_key_at_every_item_get(self):
        from oot_rando.patching.event_patch import _flow, _snapshot
        from oot_rando.patching.qol_patches import ocarina_guide_on_get
        source = ocarina_guide_on_get(self.read(k.ACTION_GUIDE_FLOW))[0]
        records = k.key_records(['Small Key Ring (Water Temple)', 'Boss Key (Forest Temple)'])
        raw, report = k.add_key_hook(source, records)
        chart = _flow(raw).flowchart
        events = {e.name: e for e in chart.events}
        start = {e.name: e for e in chart.entry_points}['ActionGuide'].main_event.v
        self.assertEqual(start.name, report[0]['start'])
        boss = events['RandoKeyHeld_BossKey_ForestTemple'].data
        give = boss.cases[0].v
        self.assertEqual(give.data.params.data['GameDataName'], 'DungeonInfo.ForestTemple.IsGetBossKey')
        ring = boss.cases[1].v.data                    # not held: next key check
        self.assertEqual(ring.params.data['Actor'], 'Item_KeyRing_WaterTemple')
        done = ring.cases[0].v.data
        add = done.cases[1].v.data                     # not yet applied: add the keys once
        self.assertEqual(add.params.data, {'GameDataName': 'DungeonInfo.WaterTemple.SmallKeyNum',
                                           'Value': 6, 'Index': -1})
        mark = add.nxt.v.data
        self.assertEqual(mark.params.data['GameDataName'], 'RandoKeyRing.WaterTemple')
        self.assertEqual(mark.nxt.v.name, 'RandoOcarinaHeld')   # then the vanilla get flow
        self.assertEqual(done.cases[0].v.name, 'RandoOcarinaHeld')
        before = _snapshot(_flow(source))
        after = _snapshot(_flow(raw))
        self.assertEqual({n: v for n, v in after.items() if n in before}, before)
        with self.assertRaises(ValueError):
            k.add_key_hook(raw, records)

    def test_one_time_scrubs_sell_through_their_sub_flow(self):
        from oot_rando.game.extra_sources import scan_npc_sources
        from evfl import EventFlow

        def read_event(path):
            flow = EventFlow()
            flow.read(self.read(path))
            return flow

        entries = {g: e for g, e in scan_npc_sources(self.members, read_event).items() if e['source'] == 'scrub'}
        self.assertEqual(sorted(entries), ['scrub#DMC Deku Scrub', 'scrub#HF Deku Scrub Grotto',
                                           'scrub#LW Deku Scrub Grotto Front', 'scrub#LW Deku Scrub Near Bridge'])
        bridge = entries['scrub#LW Deku Scrub Near Bridge']
        self.assertEqual(bridge['kind'], 'exact')
        self.assertEqual(bridge['vanilla'], 'Deku Stick Capacity')
        self.assertEqual(len(bridge['variants']), 3)
        self.assertEqual({v['param'] for v in bridge['variants']}, {'ActorName'})
        self.assertEqual(entries['scrub#HF Deku Scrub Grotto']['price'], 100)
        self.assertEqual(bridge['native_flag'], 'LostWood_Enemy_Scrub_Business_DekuStickPouch_01')


if __name__ == '__main__':
    unittest.main()
