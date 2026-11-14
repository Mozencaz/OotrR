"""Songs as items: placement rules, flow operations, text-only gets on the game's flows."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import song_adapter as songs

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_song_actors_match_the_logic_items(self):
        from oot_rando.game.remake_world import actor_item, item_actor
        for item, (actor, _) in songs.SONGS.items():
            self.assertEqual(actor_item(actor, ''), item)
            self.assertEqual(item_actor(item, None), actor)
        self.assertEqual(sorted(t for _, t in songs.SONGS.values()), list(range(12)))
        self.assertEqual(len(songs.song_gifts()), 12)
        self.assertEqual({a for _, _, _, a, _ in songs.SONG_LOCATIONS}, {a for a, _ in songs.SONGS.values()})

    def test_placement_rules(self):
        melody, other = 'Item_Melody_SariaSong', 'Item_Hookshot'
        allowed = songs.song_allowed
        # Vanilla: song locations are never shuffled, songs never placed.
        self.assertFalse(allowed('song', 'chest', melody))
        self.assertTrue(allowed('song', 'chest', other))
        # Song locations only, both ways.
        self.assertTrue(allowed('shuffled', 'song', melody))
        self.assertFalse(allowed('shuffled', 'song', other))
        self.assertFalse(allowed('shuffled', 'boss', melody))
        # Dungeon rewards: songs at song or boss sources; anything at a song location.
        self.assertTrue(allowed('dungeon', 'boss', melody))
        self.assertFalse(allowed('dungeon', 'fairy', melody))
        self.assertTrue(allowed('dungeon', 'song', other))
        # Anywhere a cutscene gives it with its text only; never chests or pickups.
        for source in songs.TEXT_ONLY_SOURCES:
            self.assertTrue(allowed('any', source, melody))
        for source in ('chest', 'shop', 'skulltula', 'npc', 'freestanding', 'pots'):
            self.assertFalse(allowed('any', source, melody))

    def _plan(self, placements, mode='any', flags=None, kinds=None):
        kinds = kinds or {}
        return songs.plan_song_flows(placements, flags or {}, mode, lambda stem: [f'F/{stem}'],
                                     lambda resource, event: kinds.get((resource, event), 'silent'))

    def test_song_location_ops(self):
        ops = self._plan([{'source': 'song', 'ap': ['Sheik in Crater'], 'before': 'Item_Melody_FireBolero',
                           'after': 'Item_Hookshot',
                           'variants': [{'resource': 'F/Dm_MelodyGet_Fire', 'event': 'Event192'}]}],
                         flags={'Song from Windmill': 'RandoCheck.x.song#Song from Windmill'})
        fire = ops['F/Dm_MelodyGet_Fire']
        self.assertTrue(fire['teaching'])
        self.assertEqual(fire['text_get'], [['Event192', 'Item_Hookshot', True]])
        self.assertEqual(fire['neutralize'], ['Event1'])      # Bolero's own flag never written
        windmill = ops['F/Npc_Hylia_009_Adult']['params']
        self.assertEqual({e for e, *_ in windmill}, {'Event9', 'Event17', 'Event31', 'Event69'})
        self.assertTrue(all(p[3] == 'RandoCheck.x.song#Song from Windmill' for p in windmill))

    def test_song_flag_follows_the_placed_song(self):
        ops = self._plan([{'source': 'song', 'ap': ['Sheik in Crater'], 'before': 'Item_Melody_FireBolero',
                           'after': 'Item_Melody_SunSong',
                           'variants': [{'resource': 'F/Dm_MelodyGet_Fire', 'event': 'Event192'}]}], 'shuffled')
        self.assertEqual(ops['F/Dm_MelodyGet_Fire']['params'],
                         [['Event1', 'GameDataName', 'IsGet.Item_Melody_FireBolero', 'IsGet.Item_Melody_SunSong']])

    def test_unchanged_song_location_is_untouched(self):
        self.assertEqual(self._plan([{'source': 'song', 'ap': ['Song from Saria'], 'before': 'Item_Melody_SariaSong',
                                      'after': 'Item_Melody_SariaSong', 'variants': []}], 'shuffled'), {})

    def test_sun_song_teaching_is_in_another_flow(self):
        ops = self._plan([{'source': 'song', 'ap': ['Song from Royal Familys Tomb'], 'before': 'Item_Melody_SunSong',
                           'after': 'Item_Melody_TimeSong',
                           'variants': [{'resource': 'F/Dm_MelodyGet_Sun_03', 'event': 'Event34'}]}], 'shuffled')
        self.assertTrue(ops['F/Dm_MelodyGet_Sun']['teaching'])
        self.assertNotIn('teaching', ops['F/Dm_MelodyGet_Sun_03'])

    def test_song_at_a_source_with_its_own_display(self):
        # Ocarina of Time: silent add (Event70) + its own get window (Event229): no second window.
        variants = [{'resource': 'F/Dm_MelodyGet_Time', 'event': 'Event70'},
                    {'resource': 'F/Dm_MelodyGet_Time', 'event': 'Event229'}]
        ops = self._plan([{'source': 'quest', 'ap': ['HF Ocarina of Time Item'], 'before': 'Item_Ocarina_Time',
                           'after': 'Item_Melody_StormSong', 'variants': variants}],
                         kinds={('F/Dm_MelodyGet_Time', 'Event229'): 'display'})
        self.assertEqual(ops['F/Dm_MelodyGet_Time']['text_get'],
                         [['Event229', 'Item_Melody_StormSong', False], ['Event70', 'Item_Melody_StormSong', False]])

    def test_song_refused_by_other_sources(self):
        with self.assertRaises(ValueError):
            self._plan([{'source': 'chest', 'ap': ['X'], 'before': 'TBox_Rupee_Green', 'after': 'Item_Melody_SunSong',
                         'variants': []}])

    def test_pose_after_cutscene_sources_are_known(self):
        from oot_rando.game.extra_sources import EVENT_GIFTS
        from oot_rando.patching.qol_patches import GIFT_AFTER_CUTSCENE
        stems = {path.split('/')[-1].split('.')[0] for path in GIFT_AFTER_CUTSCENE}
        located = {ap[0] for _, ap, _, sites in EVENT_GIFTS if any(stem in stems for stem, _, _ in sites)}
        self.assertEqual(located, set(songs.POSE_AFTER_CUTSCENE))

    def test_received_songs_are_text_only(self):
        from oot_rando.patching.ap_mailbox import records
        record, = records([{'item': 'Sarias Song', 'location': 'L1', 'player': 'Ami'}])
        self.assertEqual(record['actor'], 'Item_Melody_SariaSong')


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(NUP)
        cls.d, cls.m = dictionaries(cls.nup), effective_members(cls.nup)
        cls.read = lambda self, p: decompress(cls.nup.read(cls.m[p]), cls.d)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def events(self, raw):
        from oot_rando.patching.event_patch import _flow
        return {e.name: e for e in _flow(raw).flowchart.events}

    def test_every_song_location_can_give_any_item_as_text(self):
        from evfl.event import SubFlowEvent
        from oot_rando.game.extra_sources import event_paths
        for ap, stem, event, actor, _ in songs.SONG_LOCATIONS:
            for flow in songs.location_flows(ap):
                for path in event_paths(self.m, flow):
                    with self.subTest(flow=path):
                        raw = songs.patch_flow(self.read(path), {'teaching': True})
                        left = [e for e in self.events(raw).values() if isinstance(e.data, SubFlowEvent)
                                and e.data.entry_point_name.startswith(songs.TEACHING_PREFIX)]
                        self.assertEqual(left, [])
            path = event_paths(self.m, stem)[0]
            with self.subTest(give=path):
                original = self.events(self.read(path))[event]
                self.assertEqual(original.data.params.data['ActorName'], actor)
                raw = songs.patch_flow(self.read(path), {'text_get': [[event, actor, True]]})
                events = self.events(raw)
                shown = events[songs.display_event_name(event)]
                self.assertIs(events[event].data.nxt.v, shown)
                self.assertEqual((shown.data.res_flowchart_name, shown.data.entry_point_name),
                                 (songs.GET_FLOW, songs.DISPLAY_ENTRY))

    def test_pose_gets_become_text_only(self):
        from oot_rando.game.extra_sources import EVENT_GIFTS, event_paths
        for source, ap, _, sites in EVENT_GIFTS:
            if source not in ('fairy', 'quest', 'boss'):
                continue
            for stem, event, _ in sites:
                for path in event_paths(self.m, stem):
                    with self.subTest(site=(path, event)):
                        raw = songs.patch_flow(self.read(path), {'text_get': [[event, 'Item_Melody_SunSong', True]]})
                        data = self.events(raw)[event].data
                        kind = songs.site_kind(self.read(path), event)
                        if kind == 'silent':
                            self.assertNotEqual(getattr(data, 'res_flowchart_name', None), songs.POSE_FLOW)

    def test_song_get_messages_exist(self):
        from oot_rando.formats import msbt
        from oot_rando.formats.inspect_resources import sarc
        from oot_rando.patching.soul_adapter import MESSAGE_FILE
        archives = [p for p in self.m if p.startswith('Mals/') and '.Product.110.' in p]
        self.assertTrue(archives)
        for archive in archives:
            labels = msbt.load(sarc(self.read(archive))[MESSAGE_FILE]).labels
            for actor, _ in songs.SONGS.values():
                with self.subTest(archive=archive, actor=actor):
                    self.assertIn(actor + '_GetMessage', labels)

    def test_windmill_queries(self):
        from oot_rando.game.extra_sources import event_paths
        stem, names, flag = songs.TRIGGER_QUERIES['Song from Windmill']
        events = self.events(self.read(event_paths(self.m, stem)[0]))
        for name in names:
            self.assertEqual(events[name].data.params.data['GameDataName'], flag)


if __name__ == '__main__':
    unittest.main()
