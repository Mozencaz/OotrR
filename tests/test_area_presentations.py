"""Area presentations never play: pre-marked flags or a skip window left on frame one."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.patching import area_presentations as ap
from oot_rando.patching.qol_patches import AREA_PRESENTATIONS
from oot_rando.formats.evfl_tools import next_events, parse_flow

NUP = os.environ.get('OOT_NUP')
# First arrivals whose own event moves a quest: their flag must never be pre-set.
QUEST_ARRIVALS = ('Dm_DeathMtTrail_0000', 'Dm_Zora_0000', 'Dm_DesertColossus_0000', 'Dm_HrlCastle_0005',
                  'Dm_Deku_0000', 'Dm_Goron_0000', 'Dm_ForestTemple_0000', 'Goto_GerudoTrainingGround',
                  'Dm_DeathMtCrater_0000')


class Tables(unittest.TestCase):
    def test_every_presentation_has_one_mechanism(self):
        self.assertEqual(set(ap.PREMARKED) | set(ap.AUTO_SKIPPED), set(AREA_PRESENTATIONS))
        self.assertFalse(set(ap.PREMARKED) & set(ap.AUTO_SKIPPED))
        self.assertEqual(len(ap.PREMARKED), 11)

    def test_quest_arrivals_are_never_premarked(self):
        for name in QUEST_ARRIVALS:
            self.assertIn(name, ap.AUTO_SKIPPED)

    def test_start_values_mark_played_and_visited(self):
        values = ap.start_values()
        self.assertEqual(len(values), 2 * len(ap.PREMARKED))
        self.assertTrue(all(value is True for value in values.values()))
        for played, visit in ap.PREMARKED.values():
            self.assertTrue(played.startswith('HavePlayedEvent.'))
            self.assertTrue(visit.startswith('IsVisitLocation.'))
        self.assertIn('HavePlayedEvent.Goto_SpritTemple', values)   # the game's spelling

    def test_premarked_visits_match_the_frames(self):
        for scene, (_, visit) in ap.PREMARKED.items():
            if scene in ap.LOCATION_FRAMES:
                self.assertEqual(visit, 'IsVisitLocation.' + ap.LOCATION_FRAMES[scene])

    def test_scenes_marked_played_mark_their_area_visited(self):
        # Kaepora's first field arrival marks the Hyrule Field and castle scenes played:
        # without the visits the map showed "???" for both areas (27/11).
        from oot_rando.patching.story_fixes import story_start_values
        from oot_rando.patching import child_castle_skip
        values = dict(story_start_values(), **ap.start_values(), **child_castle_skip.START_VALUES)
        visited = ap.with_area_visits(values)
        self.assertIs(visited['IsVisitLocation.HyruleField'], True)
        self.assertIs(visited['IsVisitLocation.HyruleCastle'], True)
        for scene, area in ap.LOCATION_FRAMES.items():
            if values.get('HavePlayedEvent.' + scene) is True:
                self.assertIs(visited['IsVisitLocation.' + area], True, scene)
        self.assertEqual({k: v for k, v in visited.items() if k in values}, values)
        # Played false, or not set: nothing added.
        self.assertEqual(ap.with_area_visits({'HavePlayedEvent.Dm_Kakariko_0000': False}),
                         {'HavePlayedEvent.Dm_Kakariko_0000': False})


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class NativePresentations(unittest.TestCase):
    def test_location_frames_cover_every_area_name_frame(self):
        from oot_rando.formats.evfl_tools import parse_flow
        from evfl.event import ActionEvent
        found = {}
        for path in self.members:
            if not (path.startswith('Event/EventFlow/') and path.endswith('.bfevfl.zs')):
                continue
            raw = self.read(path)
            if b'EventTriggerOpenLocationUI' not in raw:
                continue
            names = {e.data.params.data['LocationName'] for e in parse_flow(raw).flowchart.events
                     if isinstance(e.data, ActionEvent) and e.data.actor_action.v.v == 'EventTriggerOpenLocationUI'}
            self.assertEqual(len(names), 1, path)
            found[path[len('Event/EventFlow/'):-len('.bfevfl.zs')]] = \
                names.pop()[len('Work/Location/'):].split('.')[0]
        self.assertEqual(found, ap.LOCATION_FRAMES)

    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.members = effective_members(cls.nup)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        from oot_rando.formats.inspect_resources import decompress
        return decompress(self.nup.read(self.members[path]), self.d)

    def banc_entrances(self):
        from oot_rando.formats.inspect_resources import Byml
        found = {}
        for path in self.members:
            if path.startswith('Banc/') and path.endswith('.bcett.byml.zs'):
                for actor in Byml(self.read(path)).root.get('Actors', []) or []:
                    if actor.get('Gyaml') == 'FieldAndDungeonEntranceEventRequestActor':
                        dynamic = actor.get('Dynamic') or {}
                        found.setdefault(dynamic.get('InitEventFlag'), set()).add(dynamic.get('InitEventName'))
        return found

    def test_premarked_flags_are_native_saved_bools(self):
        from oot_rando.formats.inspect_resources import Byml
        from oot_rando.patching.soul_adapter import GAMEDATA, murmur3
        entries = {e['Hash']: e for e in Byml(self.read(GAMEDATA)).root['Data']['Bool']}
        for name in ap.start_values():
            self.assertIn(murmur3(name), entries, name)
            self.assertGreaterEqual(entries[murmur3(name)]['SaveFileIndex'], 0, name)

    def test_premarked_visit_flags_match_the_name_frames(self):
        from oot_rando.patching.qol_patches import add_skip_window, flow_path
        for name, (_, visit) in ap.PREMARKED.items():
            _, records = add_skip_window(self.read(flow_path(name)))
            self.assertEqual({r['location_ui']['visit'] for r in records if 'location_ui' in r}, {visit}, name)

    def test_premarked_flags_gate_an_entrance_or_an_arrival_switch(self):
        from oot_rando.patching.qol_patches import flow_path
        from evfl.event import SwitchEvent
        entrances = self.banc_entrances()
        arrive = parse_flow(self.read(flow_path('Dm_SY_BancChangeArrive'))).flowchart
        switches = {e.data.params.data.get('EventName') for e in arrive.events if isinstance(e.data, SwitchEvent)
                    and e.data.actor_query.v.v == 'EventQueryHavePlayedEvent' and e.data.params is not None}
        for name, (played, _) in ap.PREMARKED.items():
            gated = played in entrances or played[len('HavePlayedEvent.'):] in switches
            self.assertTrue(gated, name)

    def test_auto_skip_jumps_to_the_window_end(self):
        from oot_rando.patching.qol_patches import flow_path
        files, report = ap.presentation_files(self.read)
        self.assertEqual(set(files), {flow_path(n) for n in AREA_PRESENTATIONS})
        for name in ap.AUTO_SKIPPED:
            chart = parse_flow(files[flow_path(name)]).flowchart
            entries = {e.name: e for e in chart.entry_points}
            for record in report[name]:
                # Waits for the loading screen first, else the screen stays black (19/11).
                wait = entries[record['entry']].main_event.v
                self.assertEqual(wait.data.actor.v.identifier.name, 'UISystemActor')
                self.assertEqual(wait.data.actor_action.v.v, 'EventWaitCloseLoadingFade')
                self.assertEqual(wait.data.params.data, {'IsWaitEnd': True})
                # No skip window is entered (stuck event, 19/11): quest steps, fade-in, frame.
                step = wait.data.nxt.v
                kept = []
                while step.name.startswith(ap.AUTO_PREFIX):
                    kept.append(step.data.params.data['StepName'])
                    step = step.data.nxt.v
                self.assertEqual(step.name, record['auto'])
                self.assertEqual(kept, record['kept'])
                self.assertEqual(step.data.actor_action.v.v, 'EventEventFadeIn')
                frame = step.data.nxt.v
                self.assertEqual(frame.data.actor_action.v.v, 'EventTriggerOpenLocationUI')
                self.assertEqual(frame.data.nxt.v.data.params.data['GameDataName'],
                                 record['location_ui']['visit'])
                reached, stack = set(), [wait]
                while stack:
                    event = stack.pop()
                    if event is None or event.name in reached:
                        continue
                    reached.add(event.name)
                    stack.extend(next_events(event))
                    self.assertNotIn(getattr(getattr(event.data, 'actor_action', None), 'v', None) and
                                     event.data.actor_action.v.v,
                                     ('EventTriggerSkipAcceptStart', 'EventTriggerSkipEnd'), name)
        for name in ap.PREMARKED:
            self.assertFalse(any(r.get('auto') for r in report[name]))
            # The + windows wait for the loading screen too.
            chart = parse_flow(files[flow_path(name)]).flowchart
            entries = {e.name: e for e in chart.entry_points}
            for record in report[name]:
                wait = entries[record['entry']].main_event.v
                self.assertEqual(wait.data.actor_action.v.v, 'EventWaitCloseLoadingFade')
                self.assertEqual(wait.data.nxt.v.data.actor_action.v.v, 'EventTriggerSkipAcceptStart')
        self.assertTrue(all(r['loading_wait'] for records in report.values() for r in records))
        for name in AREA_PRESENTATIONS:
            self.assertEqual(ap.expected_flow(name, self.read(flow_path(name)), report[name]),
                             files[flow_path(name)])
        self.assertEqual(report['Dm_ForestTemple_0000'][0]['kept'], ['Step05'])

    def test_without_start_flags_everything_is_auto_skipped(self):
        _, report = ap.presentation_files(self.read, premarked=False)
        self.assertTrue(all(r.get('auto') for records in report.values() for r in records))

    def test_expected_flow_rebuilds_the_patch(self):
        from oot_rando.patching.qol_patches import flow_path
        files, report = ap.presentation_files(self.read)
        for name in ('Dm_ForestTemple_0000', 'Goto_FireTemple', 'Dm_GerudoValley_0000'):
            original = self.read(flow_path(name))
            self.assertEqual(ap.expected_flow(name, original, report[name]), files[flow_path(name)])


if __name__ == '__main__':
    unittest.main()
