"""New-game defaults of the GameData list (patching/game_defaults.py). NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.patching import game_defaults as g
from oot_rando.patching.soul_adapter import murmur3

NUP = os.environ.get('OOT_NUP')
U32 = byml_codec.U32


def entry(name, default, save=0, reset=8, **extra):
    return dict({'Hash': U32(murmur3(name)), 'DefaultValue': default, 'SaveFileIndex': save,
                 'ResetTypeValue': reset}, **extra)


def gamedata():
    steps = ['NotReady', 'Ready', 'Step01']
    return byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Data': {
        'Bool': [entry('Gate', False), entry('Temp', False, save=-1), entry('Scene', False, reset=9)],
        'Int': [entry('Rupees', 0)],
        'Enum': [entry('Quest', U32(murmur3('NotReady')), RawValues=steps,
                       Values=[U32(murmur3(s)) for s in steps])],
    }}})


class Units(unittest.TestCase):
    def test_bool_int_enum_written(self):
        raw = g.set_new_game_defaults(gamedata(), {'Gate': True, 'Rupees': 99, 'Quest': 'Step01'})
        self.assertEqual(g.read_defaults(raw, ['Gate', 'Rupees', 'Quest']),
                         {'Gate': True, 'Rupees': 99, 'Quest': 'Step01'})
        # Nothing else changes.
        self.assertEqual(g.read_defaults(raw, ['Temp', 'Scene']), {'Temp': False, 'Scene': False})

    def test_empty_values_keep_the_bytes(self):
        raw = gamedata()
        self.assertIs(g.set_new_game_defaults(raw, {}), raw)

    def test_unsafe_entries_refused(self):
        for values in ({'Missing': True},           # unknown name
                       {'Temp': True},              # not saved
                       {'Scene': True},             # reset on map change
                       {'Rupees': True},            # wrong type
                       {'Gate': 1},                 # wrong type
                       {'Rupees': 2 ** 31},         # out of range
                       {'Quest': 'Step99'},         # unknown enum value
                       {'Gate': 1.5}):              # unsupported type
            with self.subTest(values=values), self.assertRaises(ValueError):
                g.set_new_game_defaults(gamedata(), values)
            with self.subTest(check=values), self.assertRaises(ValueError):
                g.check_defaults(gamedata(), values)

    def test_all_or_nothing(self):
        with self.assertRaises(ValueError):
            g.set_new_game_defaults(gamedata(), {'Gate': True, 'Missing': True})

    def test_other_reset_mask_on_request(self):
        raw = g.set_new_game_defaults(gamedata(), {'Scene': True}, allow_reset=(8, 9))
        self.assertEqual(g.read_defaults(raw, ['Scene']), {'Scene': True})


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class GameList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        nup = Nup(NUP)
        cls.raw = decompress(nup.read(nup.latest('romfs/' + g.GAMEDATA)), dictionaries(nup))

    def test_opening_flags_are_new_game_defaults(self):
        values = {'Npc_Hylia_Soldier_003_GateOpen': True, 'HyruleField_ArriveEntrance': True,
                  'HavePlayedEvent.Dm_HrlField_0020': True, 'GaveFishToJabJab': True,
                  'PlayerStatus.CurrentRupee': 99}
        raw = g.set_new_game_defaults(self.raw, values)
        self.assertEqual(g.read_defaults(raw, list(values)), values)
        before, after = byml_codec.load(self.raw), byml_codec.load(raw)
        for entries in before['root']['Data'].values():
            for e in entries:
                if isinstance(e, dict) and int(e.get('Hash', -1)) in {murmur3(n) for n in values}:
                    e['DefaultValue'] = values[next(n for n in values if murmur3(n) == int(e['Hash']))]
        self.assertEqual(before, after)    # only the requested defaults moved

    def test_expressions_are_refused(self):
        with self.assertRaises(ValueError):
            g.set_new_game_defaults(self.raw, {'Get_StoneOfWater_IsAfter_Step06_Exp': True})


if __name__ == '__main__':
    unittest.main()
