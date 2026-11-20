"""Song lessons without their cutscene (patching/song_lessons.py)."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import song_adapter as songs
from oot_rando.patching import song_lessons as lessons

NUP = os.environ.get('OOT_NUP')
MALON = lessons.BY_AP['Song from Malon']
FLAG = 'RandoCheck.test.song#Song from Malon'


class Units(unittest.TestCase):
    def test_lessons_match_the_song_locations(self):
        sites = {ap: (stem, event, actor) for ap, stem, event, actor, _ in songs.SONG_LOCATIONS}
        for lesson in lessons.LESSONS:
            self.assertEqual(sites[lesson.ap], (lesson.stem, lesson.grant, lesson.actor))
        # Every song location is either skipped or listed with its reason.
        self.assertEqual(set(sites), set(lessons.BY_AP) | set(lessons.NOT_SKIPPED))
        self.assertFalse(set(lessons.BY_AP) & set(lessons.NOT_SKIPPED))

    def test_option_off_skips_nothing(self):
        self.assertEqual(lessons.lesson_locations(False), ())
        self.assertEqual(lessons.lesson_locations(None), ())
        self.assertEqual(len(lessons.lesson_locations(True)), 10)

    def test_songs_given_here_get_a_harp(self):
        from oot_rando.patching import song_models
        for lesson in lessons.LESSONS:
            self.assertIn(lesson.actor, song_models.SONG_COLOURS)

    def test_options_are_shown_in_the_gui(self):
        from oot_rando.logic import rando_options
        from oot_rando.gui.randomizer_gui import SETTING_GROUPS
        for name in ('skip_song_lessons', 'skip_story_timelines'):
            option = rando_options.BY_NAME[name]
            self.assertEqual(option.default, False)
            self.assertTrue(option.supported(True))
            self.assertIn(name, [n for _, _, names in SETTING_GROUPS for n in names])


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class GameFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        d, members = dictionaries(nup), effective_members(nup)
        cls.read = staticmethod(lambda name: decompress(nup.read(members[lessons.flow_path(name)]), d))
        cls.scene, cls.trigger = cls.read(MALON.stem), cls.read(MALON.trigger)

    def _chain(self, raw, entry_name):
        from oot_rando.patching.event_patch import _flow
        chart = _flow(raw).flowchart
        entry = next(e for e in chart.entry_points if e.name == entry_name)
        order, event = [], entry.main_event.v
        while event is not None and len(order) < 20:
            order.append((event.name, dict(event.data.params.data) if getattr(event.data, 'params', None) else {}))
            event = event.data.nxt.v if getattr(event.data, 'nxt', None) is not None else None
        return order

    def test_vanilla_lesson_gives_epona_song(self):
        self.assertEqual(lessons.given_item(self.scene, MALON), {'actor': 'Item_Melody_EponaSong', 'flag': None})

    def test_malon_gives_the_item_with_its_pose_then_the_quest_writes(self):
        out, report = lessons.give_in_trigger(self.trigger, self.scene, MALON, 'Item_Hookshot', FLAG)
        self.assertTrue(lessons.trigger_applied(out, MALON, 'Item_Hookshot', FLAG))
        self.assertFalse(lessons.trigger_applied(self.trigger, MALON, 'Item_Hookshot', FLAG))
        chain = self._chain(out, 'GetEponaSong_MelodyGet_Epona')
        names = [name for name, _ in chain]
        base = 'RandoLesson_Event1_'
        start = names.index(base + 'Played')
        self.assertEqual(names[start:], [base + 'Played', base + 'Get', base + 'Collected',
                                         base + 'State0', base + 'State1'])
        params = dict(chain)
        self.assertEqual(params[base + 'Played']['GameDataName'], 'HavePlayedEvent.Dm_MelodyGet_Epona')
        self.assertEqual(params[base + 'Get']['ActorName'], 'Item_Hookshot')
        self.assertEqual(params[base + 'Collected']['GameDataName'], FLAG)
        self.assertEqual(params[base + 'State0']['GameDataName'], 'Forbid_MelodyGet_Epona')
        self.assertEqual(params[base + 'State1']['StepName'], 'AfterGetEponaSong')
        self.assertNotIn('Event1', names)
        self.assertEqual(report['sites'], [{'transition': 'Event1', 'chain': names[start:]}])

    def test_every_lesson_gives_its_item_in_its_trigger(self):
        from oot_rando.patching.event_info import new_subflows
        from oot_rando.patching.story_fixes import second_malon_after_talon
        for lesson in lessons.LESSONS:
            with self.subTest(lesson.ap):
                scene, trigger = self.read(lesson.stem), self.read(lesson.trigger)
                if lesson.trigger == MALON.trigger:
                    trigger = second_malon_after_talon(trigger)[0]
                given = lessons.given_item(scene, lesson)
                self.assertEqual(given, {'actor': lesson.actor, 'flag': None})
                out, report = lessons.give_in_trigger(trigger, scene, lesson, given['actor'], FLAG)
                self.assertTrue(lessons.trigger_applied(out, lesson, given['actor'], FLAG))
                self.assertEqual(len(report['cut']), len(lesson.cut))
                added = new_subflows({lesson.trigger: out}, lambda name: self.read(name))
                self.assertTrue(added)
                self.assertTrue(all(lessons.GET_CALL in calls for calls in added.values()))
                with self.assertRaises(ValueError):
                    lessons.give_in_trigger(out, scene, lesson, given['actor'], FLAG)

    def test_lesson_state(self):
        def state(ap):
            lesson = lessons.BY_AP[ap]
            return [(kind, first, second, params.get('GameDataName') if params else None)
                    for kind, first, second, params in lessons.scene_state(self.read(lesson.stem), lesson)]
        self.assertEqual(state('Song from Impa'), [])
        self.assertEqual(state('Song from Windmill'), [
            ('action', 'GameDataActor', 'EventTriggerSetGameDataBool', 'KakarikoVillage_Windmill_IsHighSpeed')])
        # Bolero's own IsGet is left to the item get.
        self.assertEqual(state('Sheik in Crater'), [
            ('action', 'GameDataActor', 'EventTriggerAddOrSubGameDataInt', 'AllSage_MeetSheikCount'),
            ('call', 'AllSage', 'MeetSheik_And_Gone', None)])

    def test_kakariko_waits_for_the_loading_screen(self):
        lesson = lessons.BY_AP['Sheik in Kakariko']
        _, report = lessons.give_in_trigger(self.read(lesson.trigger), self.read(lesson.stem), lesson,
                                            lesson.actor, None)
        self.assertEqual(report['sites'][0]['chain'][:3], ['RandoLesson_Event68_Played',
                                                           'RandoLesson_Event68_LoadingWait',
                                                           'RandoLesson_Event68_Get'])

    def test_ice_cavern_keeps_its_music(self):
        lesson = lessons.BY_AP['Sheik in Ice Cavern']
        _, report = lessons.give_in_trigger(self.read(lesson.trigger), self.read(lesson.stem), lesson,
                                            lesson.actor, None)
        self.assertEqual([site['transition'] for site in report['sites']], ['Event281', 'Event283'])
        self.assertEqual(sorted(report['music']), ['Event286', 'Event287'])

    def test_ocarina_is_refused(self):
        placed = songs.patch_flow(self.scene, {'params': [['Event11', 'ActorName', 'Item_Melody_EponaSong',
                                                           'Item_Ocarina_Fairy']]})
        with self.assertRaises(ValueError):
            lessons.given_item(placed, MALON)


if __name__ == '__main__':
    unittest.main()
