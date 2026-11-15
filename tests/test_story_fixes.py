"""Story locks of the remake (patching/story_fixes.py). NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats.byml_writer import patch_strings
from oot_rando.formats.inspect_resources import Byml
from oot_rando.patching import story_fixes as s

NUP = os.environ.get('OOT_NUP')


class SheikUnits(unittest.TestCase):
    def test_presence_added_to_the_only_sheik(self):
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': [
            {'Gyaml': 'Obj_TimeTemple_MasterSword_A_01', 'Hash': 1},
            {'Gyaml': s.SHEIK, 'Hash': 2}]}})
        edits = s.sheik_presence_edits(Byml(raw).root)
        root = Byml(patch_strings(raw, edits)).root
        self.assertEqual(root['Actors'][1]['Presence'], s.SHEIK_PRESENCE_ENTRY)
        self.assertNotIn('Presence', root['Actors'][0])
        with self.assertRaises(ValueError):    # never applied twice
            s.sheik_presence_edits(root)
        with self.assertRaises(ValueError):    # no Sheik
            s.sheik_presence_edits({'Actors': [{'Gyaml': 'Npc_X'}]})


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class GameFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        return self.decompress(self.nup.read(self.nup.latest('romfs/' + path)), self.d)

    def chart(self, raw):
        from oot_rando.patching.event_patch import _flow
        return {e.name: e for e in _flow(raw).flowchart.events}

    def check_kept(self, source, raw):
        from oot_rando.patching.event_patch import _flow, _snapshot
        before, after = _snapshot(_flow(source)), _snapshot(_flow(raw))
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)

    def test_darunia_gift_while_never_played(self):
        source = self.read(s.FIRE_STONE_FLOW)
        raw, _ = s.darunia_gift_after_dungeon(source)
        events = self.chart(raw)
        check = events['Event39'].data            # past SariaMelodyPlay (quest done)...
        given = check.cases[0].v
        self.assertEqual(given.name, 'RandoDaruniaGiftGiven')
        self.assertEqual(given.data.params.data, {'GameDataName': s.DARUNIA_GIFT_PLAYED, 'Index': -1})
        self.assertEqual(given.data.cases[1].v.name, 'Event31')        # ...gift scene if never played
        self.assertEqual(given.data.cases[1].v.data.params.data['EventName'], 'Dm_Goron_0030')
        self.assertEqual(check.cases[1].v.name, 'Event31')             # vanilla path unchanged
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.darunia_gift_after_dungeon(raw)

    def test_gift_scene_never_moves_the_quest_back(self):
        source = self.read(s.DARUNIA_GIFT_FLOW)
        raw, report = s.keep_fire_quest_forward(source)
        events = self.chart(raw)
        guard = next(e for e in events.values()
                     if getattr(e.data, 'nxt', None) is not None and e.data.nxt.v is not None
                     and e.data.nxt.v.name == 'RandoFireQuestForward')
        self.assertIsNotNone(guard)
        cases = events['RandoFireQuestForward'].data.cases
        self.assertEqual(cases[1].v.name, 'Event121')                  # vanilla: still before the step
        self.assertEqual(cases[0].v.name, report['skip_to'])           # quest already further
        self.check_kept(source, raw)

    def test_second_malon_waits_for_talon(self):
        source = self.read(s.EPONA_FLOW)
        raw, _ = s.second_malon_after_talon(source)
        events = self.chart(raw)
        awake = events['Event38'].data.cases[1].v
        self.assertEqual(awake.name, 'RandoTalonAwake')
        self.assertEqual(awake.data.params.data, {'GameDataName': s.TALON_AWAKE, 'Index': -1})
        self.assertEqual(awake.data.cases[0].v.name, 'Event36')
        away = awake.data.cases[1].v
        self.assertEqual(away.data.params.data, {'GameDataName': s.SECOND_MALON, 'Value': False, 'Index': -1})
        self.check_kept(source, raw)

    def test_bombchu_bowling_open(self):
        source = self.read(s.BOWLING_FLOW)
        raw, _ = s.open_bombchu_bowling(source)
        cases = self.chart(raw)['Event137'].data.cases
        self.assertIs(cases[0].v, cases[1].v)
        self.check_kept(source, raw)

    def test_temple_sheik(self):
        raw = self.read(s.TEMPLE_MAP)
        root = Byml(patch_strings(raw, s.sheik_presence_edits(Byml(raw).root))).root
        sheik = [a for a in root['Actors'] if a.get('Gyaml') == s.SHEIK]
        self.assertEqual(len(sheik), 1)
        self.assertEqual(sheik[0]['Presence'], s.SHEIK_PRESENCE_ENTRY)

    def test_flags_exist_in_the_game_data(self):
        from oot_rando.patching.soul_adapter import GAMEDATA, murmur3
        data = Byml(self.read(GAMEDATA)).root['Data']
        bools = {e['Hash'] for e in data['Bool']}
        exps = {e['Hash'] for e in data['BoolExp']}
        for name in (s.DARUNIA_GIFT_PLAYED, s.TALON_AWAKE, s.SECOND_MALON):
            self.assertIn(murmur3(name), bools, name)
        for name in (s.AFTER_SARIA_PLAY, s.SHEIK_PRESENCE):
            self.assertIn(murmur3(name), exps, name)


if __name__ == '__main__':
    unittest.main()
