"""Mido keeps the path to the Deku Tree until his wall is down (open forest). NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.patching.qol_patches import (EXP_AND, EXP_NOT, EXP_PUSH, MIDO_PAST_WALL, MIDO_SCHEDULE, MIDO_WALL_FLAG,
                                            keep_mido_at_his_wall)
from oot_rando.patching.soul_adapter import murmur3

NUP = os.environ.get('OOT_NUP')
GAMEDATA = 'GameData/GameDataList.Product.110.byml.zs'
STATIC = 'Banc/KokiriForest/KokiriForest_Child_Static.bcett.byml.zs'
DYNAMIC = 'Banc/KokiriForest/KokiriForest_Child_Dynamic.bcett.byml.zs'


def doc(root):
    return byml_codec.dump({'endian': '<', 'version': 7, 'root': root})


def evaluate(steps, values):
    """Run a BoolExp program on ``values`` (hash → bool), with the codes the patch uses."""
    stack = []
    for step in steps:
        code = step[0]
        if code in EXP_PUSH.values():
            stack.append(values[step[1]])
        elif code == EXP_NOT:
            stack.append(not stack.pop())
        elif code == EXP_AND:
            right, left = stack.pop(), stack.pop()
            stack.append(left and right)
        else:
            raise ValueError(f'Code {code} not used by the patch')
    [result] = stack
    return result


def schedule_entry(flag):
    return {'ActionSchedule': [{'ActionType': byml_codec.U32(murmur3('Action4'))}], 'ConditionFlag': flag}


class SyntheticTests(unittest.TestCase):
    def setUp(self):
        self.schedule = doc({'ConditionalSchedule': [schedule_entry('Meet_DekuTree_IsCompleted_Exp')]
                             + [schedule_entry(flag) for flag in MIDO_PAST_WALL],
                             'DefaultSchedule': {'ActionSchedule': []}})
        castle = 'Goto_HyruleCastle_IsCompleted_Exp'
        self.gamedata = doc({'Data': {
            'Bool': [{'DefaultValue': True, 'Hash': byml_codec.U32(murmur3(MIDO_WALL_FLAG)), 'ResetTypeValue': 8,
                      'SaveFileIndex': 0},
                     {'DefaultValue': False, 'Hash': byml_codec.U32(murmur3('Get_StoneOfForest_Complete_Mido_TalkEnd')),
                      'ResetTypeValue': 8, 'SaveFileIndex': 0}],
            'BoolExp': [{'Hash': byml_codec.U32(murmur3(castle)), 'ResetTypeValue': 0, 'SaveFileIndex': -1,
                         'Values': [[byml_codec.U64(1), byml_codec.U64(3683238313)],
                                    [byml_codec.U64(2), byml_codec.U64(1275749364)]]}]}, 'MetaData': {}})

    def test_past_wall_schedules_need_the_wall_down(self):
        schedule_raw, gamedata_raw = keep_mido_at_his_wall(self.schedule, self.gamedata)
        flags = [e['ConditionFlag'] for e in byml_codec.load(schedule_raw)['root']['ConditionalSchedule']]
        self.assertEqual(flags, ['Meet_DekuTree_IsCompleted_Exp'] + list(MIDO_PAST_WALL.values()))
        expressions = {e['Hash']: e for e in byml_codec.load(gamedata_raw)['root']['Data']['BoolExp']}
        wall = murmur3(MIDO_WALL_FLAG)
        for condition, name in MIDO_PAST_WALL.items():
            with self.subTest(condition=condition):
                row = expressions[murmur3(name)]
                self.assertEqual((row['ResetTypeValue'], row['SaveFileIndex']), (0, -1))
                steps = row['Values']
                for wall_up in (False, True):
                    for met in (False, True):
                        values = {murmur3(condition): met, wall: wall_up}
                        self.assertEqual(evaluate(steps, values), met and not wall_up)

    def test_a_bool_condition_is_pushed_as_a_bool(self):
        _, gamedata_raw = keep_mido_at_his_wall(self.schedule, self.gamedata)
        rows = {e['Hash']: e for e in byml_codec.load(gamedata_raw)['root']['Data']['BoolExp']}
        talk = rows[murmur3(MIDO_PAST_WALL['Get_StoneOfForest_Complete_Mido_TalkEnd'])]['Values']
        castle = rows[murmur3(MIDO_PAST_WALL['Goto_HyruleCastle_IsCompleted_Exp'])]['Values']
        self.assertEqual(talk[0], [EXP_PUSH['Bool'], murmur3('Get_StoneOfForest_Complete_Mido_TalkEnd')])
        self.assertEqual(castle[0], [EXP_PUSH['BoolExp'], murmur3('Goto_HyruleCastle_IsCompleted_Exp')])

    def test_refuses_an_unknown_schedule(self):
        other = doc({'ConditionalSchedule': [schedule_entry('Meet_DekuTree_IsCompleted_Exp')]})
        with self.assertRaises(ValueError):
            keep_mido_at_his_wall(other, self.gamedata)


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(NUP)
        members, d = effective_members(cls.nup), dictionaries(cls.nup)
        cls.read = staticmethod(lambda path: cls.nup.read(members[path]))
        cls.unpack = staticmethod(lambda path: decompress(cls.read(path), d))

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def test_vanilla_expressions_use_the_same_codes(self):
        """'A and not B' in the game: [push A], [push B], [not], [and]."""
        data = byml_codec.load(self.unpack(GAMEDATA))['root']['Data']
        rows = {e['Hash']: e['Values'] for e in data['BoolExp']}
        steps = rows[murmur3('DoorOfTime_IsAfterStep03_AND_SageOfForest_NotCompleted_Exp')]
        self.assertEqual(steps, [[EXP_PUSH['BoolExp'], murmur3('DoorOfTime_IsAfter_Step03_Exp')],
                                 [EXP_PUSH['BoolExp'], murmur3('SageOfForest_IsCompleted_Exp')], [EXP_NOT], [EXP_AND]])
        steps = rows[murmur3('GerudoFortress_GoToPrison_AND_Step01_Exp')]
        self.assertEqual(steps[0], [EXP_PUSH['Bool'], murmur3('GerudoFortress_GoToPrison')])

    def test_mido_never_stands_past_his_wall_while_it_is_up(self):
        schedule_raw, gamedata_raw = keep_mido_at_his_wall(self.read(MIDO_SCHEDULE), self.unpack(GAMEDATA))
        static = byml_codec.load(self.unpack(STATIC))['root']['Actors']
        dynamic = byml_codec.load(self.unpack(DYNAMIC))['root']['Actors']
        mido = next(a for a in static if a['Gyaml'] == 'Npc_Kokiri_Mido_Child')
        [wall] = [a for a in dynamic if (a.get('Presence') or {}).get('FlagName') == MIDO_WALL_FLAG]
        linked = {link['Dst'] for link in mido['Links']}
        anchors = {a['Gyaml']: a['Translate'] for a in static if a['Hash'] in linked}
        # The path runs towards +x there: home on the village side, the Deku Tree beyond.
        self.assertLess(mido['Translate'][0], wall['Translate'][0])
        action = {murmur3(name.removeprefix('Anchor')): x for name, (x, _, _) in anchors.items()}
        expressions = {e['Hash']: e['Values'] for e in byml_codec.load(gamedata_raw)['root']['Data']['BoolExp']}
        guarded = set()
        for entry in byml_codec.load(schedule_raw)['root']['ConditionalSchedule']:
            action_type = entry['ActionSchedule'][0].get('ActionType')
            if action_type is not None and action[action_type] > wall['Translate'][0]:
                guarded.add(entry['ConditionFlag'])
                steps = expressions[murmur3(entry['ConditionFlag'])]
                self.assertFalse(evaluate(steps, {steps[0][1]: True, murmur3(MIDO_WALL_FLAG): True}))
                self.assertTrue(evaluate(steps, {steps[0][1]: True, murmur3(MIDO_WALL_FLAG): False}))
        self.assertEqual(guarded, set(MIDO_PAST_WALL.values()))


if __name__ == '__main__':
    unittest.main()
