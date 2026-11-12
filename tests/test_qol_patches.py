"""Skippable cutscenes/dialogues and the one-click install. NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import json
import os
import tempfile
import unittest
from pathlib import Path

from oot_rando.randomizer.randomizer_core import Settings, settings_identity
from oot_rando.randomizer.randomizer_services import archive_previous_seeds, is_randomizer_seed
from oot_rando.patching.randomize_kokiri import TITLE

NUP = os.environ.get('OOT_NUP')


class SettingsTests(unittest.TestCase):
    def test_new_skips_do_not_change_earlier_seed_identity(self):
        settings = Settings('identity')
        self.assertNotIn('skip_auto_dialogues', settings.to_dict())
        self.assertEqual(settings_identity(settings), settings_identity(Settings.from_dict(settings.to_dict())))
        enabled = Settings('identity', skip_locked_cutscenes=True, skip_auto_dialogues=True, skip_chest_cutscenes=True)
        restored = Settings.from_dict(enabled.to_dict())
        self.assertTrue(restored.skip_auto_dialogues and restored.skip_locked_cutscenes and restored.skip_chest_cutscenes)
        self.assertNotEqual(settings_identity(settings), settings_identity(enabled))

    def test_skip_only_seed_is_valid(self):
        Settings('skip', randomize_chests=False, open_forest=False, skip_locked_cutscenes=True).validate_supported()
        with self.assertRaises(ValueError):
            Settings('skip', skip_locked_cutscenes=1).validate()

    def test_npc_dialogue_skips_are_removed(self):
        self.assertFalse(hasattr(Settings('x'), 'skip_npc_dialogues'))
        with self.assertRaises(TypeError):
            Settings('x', skip_npc_dialogues=True)
        old = Settings.from_dict({'seed': 'ancien', 'skip_npc_dialogues': True, 'skip_saria_dialogue': True})
        self.assertNotIn('skip_npc_dialogues', old.to_dict())
        self.assertEqual(settings_identity(old), settings_identity(Settings('ancien')))

    def test_removed_first_skips_fold_into_the_general_ones(self):
        legacy = Settings.from_dict({'seed': 'ancien', 'skip_intro': True})
        self.assertTrue(legacy.skip_locked_cutscenes)
        self.assertNotIn('skip_intro', legacy.to_dict())
        off = Settings.from_dict({'seed': 'ancien', 'skip_intro': False})
        self.assertFalse(off.skip_locked_cutscenes)
        with self.assertRaises(ValueError):
            Settings.from_dict({'seed': 'ancien', 'skip_intro': 1})


class ArchiveTests(unittest.TestCase):
    def seed(self, parent, ident):
        folder = parent / ('OoT_Randomizer_' + ident[:16])
        (folder / 'romfs').mkdir(parents=True)
        (folder / 'manifest.json').write_text(json.dumps({'title_id': TITLE, 'seed_id': ident}), encoding='utf-8')
        return folder

    def test_only_our_seeds_are_moved(self):
        with tempfile.TemporaryDirectory() as directory:
            mods = Path(directory) / TITLE
            old = self.seed(mods, 'a' * 64)
            other = mods / 'ootrshaders'
            other.mkdir()
            fake = mods / 'OoT_Randomizer_bbbbbbbbbbbbbbbb'
            fake.mkdir()
            self.assertTrue(is_randomizer_seed(old))
            self.assertFalse(is_randomizer_seed(fake))
            moved = archive_previous_seeds(mods, Path(directory) / 'archive')
            self.assertEqual([p.name for p in moved], [old.name])
            self.assertFalse(old.exists())
            self.assertTrue(other.exists() and fake.exists())


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class NupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(NUP)
        cls.members = effective_members(cls.nup)
        from oot_rando.patching import qol_patches
        cls.q = qol_patches
        cls.events = decompress(cls.nup.read(cls.members[qol_patches.EVENT_SETTINGS]), dictionaries(cls.nup))

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        return self.nup.read(self.members[path])

    def test_every_disable_skip_is_removed(self):
        from oot_rando.formats.inspect_resources import Byml
        files, report = self.q.cutscene_files(self.read)
        self.assertIn(self.q.INTRO, files)
        self.assertEqual(report, ['Dm_Kokiri_0000', 'Dm_StaffCredit_0005', 'Dm_Title_0005'])
        locked = [p for p in self.members if p.startswith(self.q.LISTS) and self.q.DISABLE_SKIP in
                  str(Byml(files.get(p) or self.read(p)).root)]
        self.assertEqual(locked, [])
        for path, data in files.items():
            self.assertEqual(len(data), len(self.read(path)))

    def test_dialogues_use_flowchart_category(self):
        from oot_rando.formats.inspect_resources import Byml
        patched, summary = self.q.patch_dialogues(self.events, areas=False)
        self.assertEqual(summary['area_rows'], 0)
        self.assertGreater(summary['rows'], 0)
        work = lambda name: 'Work/' + self.q.LISTS + name + self.q.SUFFIX + '.gyml'
        sources = {work(n) for n in self.q.NPC_STEP_START}
        rows = Byml(patched).root
        self.assertFalse([r for r in rows if r['EventSettingComponentList'] in sources])
        self.assertEqual(len(patched), len(self.events))
        # Only the component list column changes.
        for before, after in zip(Byml(self.events).root, rows):
            self.assertEqual({k: v for k, v in before.items() if k != 'EventSettingComponentList'},
                             {k: v for k, v in after.items() if k != 'EventSettingComponentList'})

    def test_area_presentation_rows_pause_like_flowchart_events(self):
        from oot_rando.formats.inspect_resources import Byml
        patched, summary = self.q.patch_dialogues(self.events, step_start=False, areas=True)
        work = lambda name: 'Work/' + self.q.LISTS + name + self.q.SUFFIX + '.gyml'
        before, after = Byml(self.events).root, Byml(patched).root
        changed = [(b, a) for b, a in zip(before, after) if b != a]
        self.assertEqual(len(changed), summary['area_rows'])
        flows = {'Work/Event/EventFlow/' + name + '.evfc' for name in self.q.AREA_PRESENTATIONS}
        for b, a in changed:
            self.assertIn(b['FlowchartFileName'], flows)
            self.assertEqual(b['EventSettingComponentList'], work('NoPauseEvent'))
            self.assertEqual(a['EventSettingComponentList'], work('FlowchartEvent'))
        changed_flows = {b['FlowchartFileName'] for b, _ in changed}
        self.assertIn('Work/Event/EventFlow/Dm_HrlField_0000.evfc', changed_flows)
        self.assertIn('Work/Event/EventFlow/Dm_Kakariko_0000.evfc', changed_flows)
        # Area entry camera moves and other NoPauseEvent rows are untouched.
        self.assertTrue([r for r in after if r['EventSettingComponentList'] == work('NoPauseEvent')])

    def _flow(self, path):
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        return decompress(self.read(path), dictionaries(self.nup))

    def test_area_presentations_get_a_native_skip_window(self):
        from oot_rando.patching.event_patch import _flow, _snapshot
        files, report = self.q.area_presentation_files(self._flow)
        self.assertEqual(set(report), set(self.q.AREA_PRESENTATIONS))
        self.assertNotIn('Dm_HrlCastle_0000', self.q.AREA_PRESENTATIONS)   # it talks
        for name in self.q.AREA_PRESENTATIONS:
            path = self.q.flow_path(name)
            before, after = _flow(self._flow(path)).flowchart, _flow(files[path]).flowchart
            added = {e.name for e in after.events} - {e.name for e in before.events}
            deferred = [r for r in report[name] if 'location_ui' in r]
            self.assertEqual(len(added), len({r['entry'] for r in report[name]}) + len(report[name])
                             + 2 * len(deferred), name)
            entries = {e.name: e for e in after.entry_points}
            events = {e.name: e for e in after.events}
            for record in report[name]:
                start = entries[record['entry']].main_event.v
                self.assertEqual(start.data.actor_action.v.v, 'EventTriggerSkipAcceptStart')
                end = events[record['after']].data.nxt.v
                self.assertEqual(end.data.actor_action.v.v, 'EventTriggerSkipEnd')
            # The name frame opens only after the window, when it was not skipped.
            self.assertTrue(deferred, name)
            opened = [e for e in after.events if getattr(e.data, 'actor_action', None) is not None
                      and e.data.actor_action.v.v == self.q.LOCATION_UI_ACTION]
            self.assertTrue(opened and all(e.name.startswith('RandoLocationUI_') for e in opened), name)
            for record in deferred:
                check = events[record['end']].data.nxt.v
                self.assertEqual(check.data.actor_query.v.v, 'EventQueryIsEventSkipedMostRecent')
                self.assertEqual(check.data.cases[1].v.data.actor_action.v.v, self.q.LOCATION_UI_ACTION)
                if 0 in check.data.cases:   # skipped: straight on, no frame
                    self.assertIs(check.data.cases[0].v, check.data.cases[1].v.data.nxt.v)
            # Every other original parameter is unchanged; the frame events became 1-frame waits.
            original = _snapshot(_flow(self._flow(path)))
            patched = _snapshot(_flow(files[path]))
            moved = {n for r in deferred for n in r['location_ui']['deferred']}
            self.assertEqual({k: v for k, v in patched.items() if k in original and k not in moved},
                             {k: v for k, v in original.items() if k not in moved})
            for n in moved:
                self.assertEqual(patched[n], {'IsWaitEnd': True, 'Frames': 1})
                self.assertEqual(events[n].data.actor_action.v.v, 'EventWait')

    def test_quick_chest_goes_from_lid_to_item(self):
        from evfl.common import Argument
        from oot_rando.patching.event_patch import _flow
        raw, report = self.q.quick_chest(self._flow(self.q.CHEST_FLOW))
        chart = _flow(raw).flowchart
        entry = next(e for e in chart.entry_points if e.name == 'Success_')
        fanfare = entry.main_event.v.data.cases[0].v
        opened = fanfare.data.nxt.v
        self.assertEqual(opened.data.entry_point_name, 'Open')
        # Link holds the item up (vanilla get pose) while the get window is open.
        chain, event = [], opened.data.nxt.v
        while event is not None and not hasattr(event.data, 'entry_point_name'):
            chain.append((event.data.actor.v.identifier.name, event.data.actor_action.v.v))
            event = event.data.nxt.v
        self.assertEqual(chain, [(a, b) for a, b, _ in self.q.CHEST_SHOW_ITEM])
        self.assertEqual(event.data.entry_point_name, 'Success_AddContent')
        hide = event.data.nxt.v
        self.assertEqual(hide.data.actor_action.v.v, 'EventDeleteShowItem')
        self.assertEqual(hide.data.nxt.v.data.entry_point_name, 'Success_Leave')
        show = opened.data.nxt.v
        self.assertIsInstance(show.data.params.data['Actor'], Argument)
        self.assertEqual(show.data.params.data['Actor'], 'ContentName')
        self.assertEqual(report['show_item'][0], show.name)
        # The lid animation (as long as the whole performance) is no longer awaited.
        lids = [e for e in chart.events if getattr(e.data, 'actor_action', None) is not None
                and e.data.actor_action.v.v == 'EventPlayAS' and e.data.params is not None
                and e.data.params.data.get('ASName') in self.q.CHEST_LID_ANIMATIONS]
        self.assertEqual(len(lids), 2)
        self.assertTrue(all(e.data.params.data['IsWaitEnd'] is False for e in lids))
        self.assertEqual(sorted(report['lid_not_awaited']), sorted(e.name for e in lids))

    def test_quick_small_chest_opens_the_lid_then_displays_the_item(self):
        from oot_rando.patching.event_patch import _flow, _snapshot
        source = self._flow(self.q.SMALL_CHEST_FLOW)
        raw, report = self.q.quick_small_chest(source)
        chart = _flow(raw).flowchart
        event = next(e for e in chart.entry_points if e.name == 'Success_').main_event.v
        chain = []
        while event is not None and len(chain) < 6:
            data = event.data
            chain.append(data.entry_point_name if hasattr(data, 'entry_point_name') else data.actor_action.v.v)
            event = data.nxt.v if getattr(data, 'nxt', None) is not None else None
        self.assertEqual(chain[:5], list(self.q.SMALL_CHEST_STEPS) + ['GetAnimationAction', 'Pack_ItemDisplay'])
        self.assertNotIn('Open', chain)
        lid = next(e for e in chart.events if e.name == 'RandoQuickChestLid')
        self.assertEqual(lid.data.params.data['ASName'], self.q.SMALL_CHEST_LID)
        self.assertIs(lid.data.params.data['IsWaitEnd'], False)
        # Nothing else changes: original parameters kept, /Open itself left in place.
        original, patched = _snapshot(_flow(source)), _snapshot(_flow(raw))
        self.assertEqual({k: v for k, v in patched.items() if k in original}, original)
        self.assertEqual(sorted(set(patched) - set(original)), sorted(report['added']))
        self.assertTrue(any(e.name == 'Open' for e in chart.entry_points))
        with self.assertRaises(ValueError):
            self.q.quick_small_chest(raw)

    def test_reported_cutscenes_get_windows_and_replay_their_writes(self):
        from oot_rando.patching.event_patch import _flow
        # Fade-outs (Gohma's blue warp, 11/11: Dm_Deku_0010 fades to white then the scene
        # changes; with a window the screen stayed white): such an entry gets no window.
        # The Kokiri Forest presentation fades out before its Dm_Kokiri_0050 transition.
        for name in ('Dm_Deku_0010', 'Dm_Kokiri_0045'):
            with self.assertRaises(ValueError):
                self.q.add_skip_windows_with_replay(self._flow(self.q.flow_path(name)))
        self.assertEqual(self.q.skip_action_class('UISystemActor', 'EventEventFadeOut', {}), 'barrier')
        # Dialogues are never covered (Saria at the ladder crashed when skipped; the Deku
        # Tree's talk before entering it is the same kind of flow): turbo A instead.
        for name in ('Dm_Kokiri_0060', 'Dm_Kokiri_0075'):
            with self.assertRaises(ValueError):
                self.q.add_skip_windows_with_replay(self._flow(self.q.flow_path(name)))
        self.assertIn('EventTalk', self.q.dialogue_actions(_flow(self._flow(self.q.flow_path('Dm_Kokiri_0060'))).flowchart))

    def test_world_changes_are_never_skippable(self):
        # Deku Tree water (11/11): skipping the switch cutscene left the water up.
        name = 'InsideTheDekuTree_Gimmick'
        try:
            _, report = self.q.add_skip_windows_with_replay(self._flow(self.q.flow_path(name)))
        except ValueError:
            report = []
        entries = {w['entry'] for w in report}
        self.assertNotIn('InsideTheDekuTree_Gimmick_RoomG_WaterLevelDrop', entries)
        self.assertNotIn('InsideTheDekuTree_Gimmick_CandleAndSpiderWeb', entries)
        self.assertEqual(self.q.skip_action_class('EventRequestActor', 'EventTriggerSetEventBool', {'Bool': True}),
                         'barrier')

    def test_skip_action_classes(self):
        c = self.q.skip_action_class
        self.assertEqual(c('EventWorldManagerController', 'Event_SetDemoPaletteTransitionForTimeline', {}), 'cosmetic')
        self.assertEqual(c('EventSystemActor', 'EventTransition', {}), 'barrier')
        self.assertEqual(c('EventCamera', 'EventTriggerCameraSavePoint', {}), 'cosmetic')
        self.assertEqual(c('PouchSystemActor', 'EventTriggerAddOrRemovePouchContent', {}), 'barrier')
        self.assertEqual(c('Npc', 'EventTalk', {'ChoiceNumber': 2}), 'barrier')
        self.assertEqual(c('Npc', 'EventTalk', {'ChoiceNumber': 0}), 'cosmetic')
        self.assertEqual(c('GameDataActor', 'EventTriggerSetGameDataBool', {'GameDataName': 'X', 'Value': True}), 'replay')
        self.assertEqual(c('GameDataActor', 'EventTriggerAddOrSubGameDataInt', {}), 'barrier')
        self.assertEqual(c('Player_Event', 'EventPlayerWarpToTargetPosAndRot', {}), 'replay')
        self.assertEqual(c('Npc', 'EventSomethingUnknown', {}), 'barrier')

    def test_kokiri_sword_chest_skips_sword_cutscene(self):
        from oot_rando.patching.event_patch import _flow, _snapshot
        source = self._flow(self.q.SWORD_CHEST_FLOW)
        raw, report = self.q.skip_kokiri_sword_cutscene(source)
        chart = _flow(raw).flowchart
        entry = {e.name: e for e in chart.entry_points}['GetSword']
        seen, event = [], entry.main_event.v
        while event is not None and getattr(event.data, 'nxt', None) is not None:
            seen.append(event)
            event = event.data.nxt.v
        names = [e.data.params.data.get('EventName') for e in seen
                 if e.data.params is not None and 'EventName' in e.data.params.data]
        self.assertEqual(names, ['Dm_SY_Treasurebox'])   # chest performance kept, Dm_Kokiri_0063 gone
        self.assertEqual(report['to'], event.name)
        before, after = _snapshot(_flow(source)), _snapshot(_flow(raw))
        self.assertEqual(after, before)
        with self.assertRaises(ValueError):
            self.q.skip_kokiri_sword_cutscene(raw)  # never applied twice

    def test_deku_tree_gift_is_given_back_in_game(self):
        from oot_rando.patching.event_patch import _flow, _snapshot, add_collection_markers, patch_event_params
        path = 'Event/EventFlow/Dm_Kokiri_0130.bfevfl.zs'
        spec = self.q.GIFT_AFTER_CUTSCENE[path]
        source = patch_event_params(self._flow(path), [('Event22', 'ActorName', 'Item_Stone_Forest', 'Item_HoverBoot')])
        source = add_collection_markers(source, {'Event22': 'RandoCheck.test.boss'})[0]
        raw, bypass = self.q.bypass_cutscene_gift(source, spec['event'])
        self.assertEqual(bypass, {'actor': 'Item_HoverBoot', 'flag': 'RandoCheck.test.boss', 'resume': 'Event49'})
        chart = _flow(raw).flowchart
        events = {e.name: e for e in chart.events}
        self.assertEqual(self.q._predecessors(chart, events['Event22']), [])
        self.assertEqual([e.name for e, _, _ in self.q._predecessors(chart, events['RandoCollected_Event22'])],
                         ['Event22'])   # (only the unreachable add)
        self.assertEqual(events['Event106'].data.nxt.v.name, 'Event49')   # the cutscene goes on
        self.assertEqual(_snapshot(_flow(raw)), _snapshot(_flow(source)))
        with self.assertRaises(ValueError):
            self.q.bypass_cutscene_gift(raw, spec['event'])   # never applied twice
        # Back in the forest: Link's normal item get, then the collection flag.
        escape = self._flow(spec['flow'])
        given, report = self.q.give_gift_after(escape, spec['after'], bypass['actor'], bypass['flag'])
        events = {e.name: e for e in _flow(given).flowchart.events}
        gift = events[self.q.GIFT_GET_EVENT]
        self.assertIs(events[spec['after']].data.nxt.v, gift)
        self.assertEqual((gift.data.res_flowchart_name, gift.data.entry_point_name), self.q.GIFT_GET_TARGET)
        self.assertEqual(gift.data.params.data, {'ActorName': 'Item_HoverBoot', 'IsNpcEventStarter': False})
        marker = gift.data.nxt.v
        self.assertEqual(marker.data.params.data['GameDataName'], 'RandoCheck.test.boss')
        self.assertEqual(marker.data.nxt.v.name, 'Event1')                 # then the quest step, as before
        self.assertEqual(report['marker'], marker.name)
        with self.assertRaises(ValueError):
            self.q.give_gift_after(given, spec['after'], 'Item_HoverBoot')   # never applied twice
        # Vanilla: the flow returning to the forest has Link's normal animations, and the
        # target entry exists (gift without a giver, as Skull Kid's heart piece).
        player = next(a for a in _flow(escape).flowchart.actors if a.identifier.name == 'Player_Event')
        self.assertEqual(player.params.data['UseEventAS'], '使用しない')
        target = {e.name for e in _flow(self._flow('Event/EventFlow/Dm_SY_GetInEvent.bfevfl.zs')).flowchart.entry_points}
        self.assertIn(self.q.GIFT_GET_TARGET[1], target)

    def test_ocarina_guide_runs_on_item_get_while_ocarina_is_held(self):
        from oot_rando.patching.event_patch import _flow, _snapshot
        source = self._flow(self.q.ACTION_GUIDE_FLOW)
        raw, report = self.q.ocarina_guide_on_get(source)
        chart = _flow(raw).flowchart
        entry = {e.name: e for e in chart.entry_points}['ActionGuide']
        held = entry.main_event.v
        self.assertEqual(held.data.actor_query.v.v, 'EventQueryIsExistInPouch')
        self.assertEqual(held.data.params.data, {'Actor': 'Item_Ocarina_Fairy', 'Num': 1})
        guide, original = held.data.cases[0].v, held.data.cases[1].v
        self.assertEqual((guide.data.res_flowchart_name, guide.data.entry_point_name),
                         ('', 'OpenActionGuideSceenForOcarina'))
        self.assertIs(guide.data.nxt.v, original)
        self.assertEqual(original.data.actor_query.v.v, 'EventQueryCheckPouchContentCategory')
        before, after = _snapshot(_flow(source)), _snapshot(_flow(raw))
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)
        with self.assertRaises(ValueError):
            self.q.ocarina_guide_on_get(raw)  # never applied twice


if __name__ == '__main__':
    unittest.main()
