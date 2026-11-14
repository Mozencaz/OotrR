import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.patching.qol_patches import (MIDO_GUARD_FLAG, MIDO_PASS_TALK, MIDO_SCHEDULE, MIDO_WALL_FLAG,
                                            keep_mido_at_post)

NUP = os.environ.get('OOT_NUP')
STORY = ['Meet_DekuTree_IsAfter_Step02_Exp', 'Goto_HyruleCastle_IsCompleted_Exp']


def schedule(flags):
    default = {'ActionSchedule': [{'StartTime': 0, 'Setting': {'ArrivalAS': 'Act_Arrogant'}}],
               'EventEntry': [{'$type': 'game__aischedule__OnPlayerTalk', 'EventName': MIDO_PASS_TALK}]}
    states = [{'ConditionFlag': flag, 'ActionSchedule': [{'StartTime': 0}], 'EventEntry': []} for flag in flags]
    return byml_codec.dump({'endian': '<', 'version': 7,
                            'root': {'ConditionalSchedule': states, 'DefaultSchedule': default}})


class MidoPostTests(unittest.TestCase):
    def test_wall_and_guard_states_come_last(self):
        # The last true state wins: while the wall stands, Mido stays at his post
        # (default schedule, pass talk) and guards when the player comes near.
        patched, summary = keep_mido_at_post(schedule([MIDO_GUARD_FLAG] + STORY))
        root = byml_codec.load(patched)['root']
        states = root['ConditionalSchedule']
        self.assertEqual([s['ConditionFlag'] for s in states], STORY + [MIDO_WALL_FLAG, MIDO_GUARD_FLAG])
        post = states[-2]
        self.assertEqual(post['EventEntry'], root['DefaultSchedule']['EventEntry'])
        self.assertEqual(post['ActionSchedule'], root['DefaultSchedule']['ActionSchedule'])
        self.assertEqual(summary['order'][-2:], [MIDO_WALL_FLAG, MIDO_GUARD_FLAG])

    def test_refuses_unknown_or_patched_schedules(self):
        with self.assertRaises(ValueError):
            keep_mido_at_post(schedule(STORY + [MIDO_GUARD_FLAG]))
        patched, _ = keep_mido_at_post(schedule([MIDO_GUARD_FLAG] + STORY))
        with self.assertRaises(ValueError):
            keep_mido_at_post(patched)

    @unittest.skipUnless(NUP, 'OOT_NUP not set')
    def test_game_schedule(self):
        from oot_rando.formats.inspect_nup import Nup
        nup = Nup(NUP)
        try:
            patched, summary = keep_mido_at_post(nup.read(nup.latest('romfs/' + MIDO_SCHEDULE)))
        finally:
            nup.stream.close()
        self.assertEqual(summary['order'][-3:],
                         ['Goto_HyruleCastle_IsCompleted_Exp', MIDO_WALL_FLAG, MIDO_GUARD_FLAG])
        self.assertEqual(len(summary['order']), 7)


if __name__ == '__main__':
    unittest.main()
