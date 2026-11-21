"""The altar's native ocarina invalid-condition must agree with the door setting."""
import itertools
import os
import unittest

import _src_path  # noqa: F401
from oot_rando.formats import byml_codec as codec
from oot_rando.patching import story_fixes as s
from oot_rando.patching.soul_adapter import murmur3


def evaluate(program, flags, enums=None):
    stack = []
    for op, *args in program:
        if op == 0:
            stack.append(flags.get(args[0], False))
        elif op == 1:
            stack.append((enums or {}).get(args[0]))
        elif op == 2:
            stack.append(stack.pop() == args[0])
        elif op == 5:
            stack.append(not stack.pop())
        else:
            b, a = stack.pop(), stack.pop()
            stack.append(a and b if op == 3 else a or b)
    assert len(stack) == 1
    return stack[0]


class DoorSongCondition(unittest.TestCase):
    @staticmethod
    def fixture():
        names = ['Market_Child_TimeTempleDoor_Opened'] + [
            'IsGet.' + stone for stone in s.STONE_SETS['all']]
        return codec.dump({'endian': '<', 'version': 7, 'root': {'Data': {
            'Bool': [{'Hash': codec.U32(murmur3(n))} for n in names],
            'BoolExp': [{'Hash': codec.U32(murmur3('Market_Child_TimeTempleDoor_OcarinaReacts')),
                         'ResetTypeValue': 0, 'SaveFileIndex': -1,
                         'Values': [[codec.U64(v) for v in x] for x in
                                    [[1, 931730378], [2, murmur3('Step05')], [5],
                                     [0, murmur3(names[0])], [4]]]}]}}})

    def check_modes(self, source):
        source_data = codec.load(source)['root']['Data']
        for requirement in ('song', 'vanilla', 'all'):
            raw, report = s.door_song_condition(source, requirement)
            self.assertTrue(s.door_song_condition_applied(raw, requirement))
            self.assertFalse(s.door_song_condition_applied(source, requirement))
            self.assertEqual(report['requirement'], requirement)
            data = codec.load(raw)['root']['Data']
            self.assertEqual(data['Bool'], source_data['Bool'])
            old = {int(e['Hash']): e for e in source_data['BoolExp']}
            new = {int(e['Hash']): e for e in data['BoolExp']}
            key = murmur3(s.DOOR_SONG_INVALID)
            self.assertEqual({k: v for k, v in new.items() if k != key},
                             {k: v for k, v in old.items() if k != key})
            program = new[key]['Values']
            for held in itertools.product((False, True), repeat=3):
                for opened in (False, True):
                    flags = {murmur3('IsGet.' + n): v for n, v in zip(s.STONE_SETS['all'], held)}
                    flags[murmur3(s.DOOR_OPENED)] = opened
                    enough = True if requirement == 'song' else all(held[1:] if requirement == 'vanilla' else held)
                    self.assertEqual(evaluate(program, flags), opened or not enough,
                                     (requirement, held, opened))
            with self.assertRaises(ValueError):
                s.door_song_condition(raw, requirement)

    def test_native_gate_blocks_song_before_ocarina_escape_step(self):
        source = self.fixture()
        native = codec.load(source)['root']['Data']['BoolExp'][0]['Values']
        self.assertTrue(evaluate(native, {}, {931730378: murmur3('Ready')}))
        self.assertFalse(evaluate(native, {}, {931730378: murmur3('Step05')}))
        self.check_modes(source)

    def test_rejects_unknown_settings_and_changed_game_data(self):
        source = self.fixture()
        with self.assertRaises(ValueError):
            s.door_song_condition(source, 'unknown')
        document = codec.load(source)
        document['root']['Data']['Bool'] = []
        with self.assertRaises(ValueError):
            s.door_song_condition(codec.dump(document))
        document = codec.load(source)
        document['root']['Data']['BoolExp'][0]['Values'] = [[codec.U64(5)]]
        with self.assertRaises(ValueError):
            s.door_song_condition(codec.dump(document))

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
    def test_native_pack_and_gamedata(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries, sarc
        from oot_rando.patching.game_defaults import GAMEDATA
        nup = Nup(os.environ['OOT_NUP'])
        try:
            d = dictionaries(nup)
            def read(path):
                return decompress(nup.read(nup.latest('romfs/' + path)), d)
            pack = sarc(read('Pack/Actor/Obj_TimeTemple_SpiritStoneBase_A_01.pack.zs'))
            param = codec.load(pack['GameParameter/ReplaceEventParam/'
                                   'Obj_TimeTemple_SpiritStoneBase_A_01.game__ocarina__ReplaceEventParam.bgyml'])['root']
            self.assertTrue(param['UseInvalidCondition'])
            self.assertEqual(param['InvalidGameData'], s.DOOR_SONG_INVALID)
            self.assertEqual(int(param['InvalidGameDataHash']), murmur3(s.DOOR_SONG_INVALID))
            self.assertIn('Market_Child_DoorOfTime_OpenDoor', param['EventName'])
            self.check_modes(read(GAMEDATA))
        finally:
            nup.stream.close()
