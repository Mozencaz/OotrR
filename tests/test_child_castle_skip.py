"""Child Hyrule Castle made optional (skip_child_zelda). NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
from collections import Counter
import os
import unittest

from oot_rando.game.extra_sources import _entry
from oot_rando.logic import rando_options
from oot_rando.logic.rules import Logic
from oot_rando.logic.world import World
from oot_rando.patching import child_castle_skip as cs
from oot_rando.randomizer.full_randomizer import (CASTLE_JUNK, ap_settings, prepare, skipped_castle_check,
                                                  vname)
from oot_rando.formats.evfl_tools import params_by_event, parse_flow

NUP = os.environ.get('OOT_NUP')
LETTER, IMPA, FAIRY = 'quest#HC Zeldas Letter', 'song#Song from Impa', 'fairy#HC Great Fairy Reward'
TREE, SARIA, FILLER = 'HyruleCastle#gs#1', 'quest#LW Gift from Saria', 'KokiriForest#gs#1'


def source(source, gid, folder, location, actor, vanilla, resource):
    entry = _entry(source, 'event', gid, folder, actor, vanilla)
    entry.update(kind='exact', ap=[location], actors=[actor],
                 variants=[{'resource': resource, 'event': 'Event1', 'param': 'ActorName', 'before': actor}])
    return entry


def sources():
    fillers = {f'KokiriForest#gs#{n}': source('skulltula', f'KokiriForest#gs#{n}', 'KokiriForest', location,
                                              'Item_Rupee_Blue', 'Rupees (5)',
                                              'Banc/KokiriForest/KokiriForest_Static.bcett.byml.zs')
               for n, location in ((2, 'KF GS Bean Patch'), (3, 'KF GS House of Twins'))}
    return {**fillers,
        TREE: source('skulltula', TREE, 'HyruleCastle', 'HC GS Tree', 'Item_GoldSkulltulaToken',
                     'Gold Skulltula Token', 'Banc/HyruleCastle/HyruleCastle_Static.bcett.byml.zs'),
        SARIA: source('quest', SARIA, 'Npc', 'LW Gift from Saria', 'Item_Ocarina_Fairy', 'Ocarina',
                      'Event/EventFlow/Dm_Kokiri_0155.bfevfl.zs'),
        FILLER: source('skulltula', FILLER, 'KokiriForest', 'KF GS Know It All House', 'Item_Rupee_Blue',
                       'Rupees (5)', 'Banc/KokiriForest/KokiriForest_Static.bcett.byml.zs'),
    }


class CastleChecks(unittest.TestCase):
    def test_castle_checks_but_not_the_fairy(self):
        self.assertTrue(skipped_castle_check({'folder': 'HyruleCastle', 'source': 'pots', 'ap': ['HC GS Tree']}))
        self.assertTrue(skipped_castle_check({'folder': 'Npc', 'source': 'quest', 'ap': ['HC Zeldas Letter']}))
        self.assertTrue(skipped_castle_check({'folder': 'Npc', 'source': 'song', 'ap': ['Song from Impa']}))
        self.assertFalse(skipped_castle_check({'folder': 'Npc', 'source': 'fairy', 'ap': ['HC Great Fairy Reward']}))
        self.assertFalse(skipped_castle_check({'folder': 'GanonCastle', 'source': 'pots', 'ap': ['OGC GS']}))
        self.assertFalse(skipped_castle_check({'folder': 'Npc', 'source': 'quest', 'ap': ['LW Gift from Saria']}))

    def test_option_supported(self):
        option = rando_options.BY_NAME['skip_child_zelda']
        self.assertTrue(option.supported(True))
        self.assertIn(True, option.experimental)
        self.assertTrue(cs.enabled({'skip_child_zelda': True}))
        self.assertFalse(cs.enabled(rando_options.defaults()))


class CastleLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = World()

    def met_zelda_at_start(self, skip):
        options = dict(rando_options.defaults(), skip_child_zelda=skip)
        logic = Logic(self.data, ap_settings(options, True))
        state, _, _ = logic.sweep({'HC Zeldas Letter': None, 'Song from Impa': None}, logic.new_state(Counter()))
        return state.has('Met Zelda')

    def test_zelda_met_from_the_start(self):
        self.assertTrue(self.met_zelda_at_start(True))
        self.assertFalse(self.met_zelda_at_start(False))

    def test_skipping_zelda_does_not_open_the_closed_forest(self):
        options = dict(rando_options.defaults(), skip_child_zelda=True)
        logic = Logic(self.data, ap_settings(options, False))
        state, _, _ = logic.sweep({}, logic.new_state(Counter()))
        self.assertTrue(state.has('Met Zelda'))
        self.assertNotIn('Hyrule Field', state.reached['child'])
        cleared, _, _ = logic.sweep({}, logic.new_state(Counter({'Deku Tree Clear': 1})))
        self.assertIn('Hyrule Field', cleared.reached['child'])

    def test_shuffled_castle_checks_hold_green_rupees(self):
        options = dict(rando_options.defaults(), skip_child_zelda=True, tokensanity='all',
                       shuffle_quest_rewards=True)
        c = prepare(self.data, options, {}, [], 'castle-skip', True, extra=sources())
        self.assertEqual(c.castle_junk, [TREE])
        self.assertTrue(c.allowed(CASTLE_JUNK, TREE))
        self.assertFalse(c.allowed('Gold Skulltula Token', TREE))
        self.assertTrue(c.allowed('Gold Skulltula Token', SARIA))
        self.assertGreaterEqual(c.pool.count(CASTLE_JUNK), 1)
        self.assertEqual(len(c.pool), len(c.shuffled))
        # The castle's gifts are shuffled elsewhere, never left at their vanilla spot.
        for item in cs.MOVED_ITEMS:
            self.assertEqual(c.pool.count(item), 1, item)
            self.assertIn(item, c.progression)
            self.assertNotIn(item, c.start_items)
        for location in ('HC Zeldas Letter', 'Song from Impa'):
            self.assertIsNone(c.base.get(location))
        # Vanilla songs: the lullaby still goes anywhere a song can be given.
        self.assertTrue(c.allowed('Zeldas Lullaby', SARIA))
        self.assertTrue(c.allowed('Zeldas Letter', SARIA))

    def test_open_gate_keeps_the_removed_letter_out(self):
        options = dict(rando_options.defaults(), skip_child_zelda=True, tokensanity='all',
                       shuffle_quest_rewards=True, open_kakariko='open')
        c = prepare(self.data, options, {}, [], 'castle-skip', True, extra=sources())
        self.assertNotIn('Zeldas Letter', c.pool)
        self.assertEqual(c.pool.count('Zeldas Lullaby'), 1)
        self.assertEqual(len(c.pool), len(c.shuffled))

    def test_nothing_changes_without_the_option(self):
        options = dict(rando_options.defaults(), tokensanity='all', shuffle_quest_rewards=True)
        c = prepare(self.data, options, {}, [], 'castle-skip', True, extra=sources())
        self.assertEqual(c.castle_junk, [])
        self.assertTrue(c.allowed('Gold Skulltula Token', TREE))
        self.assertNotIn('Zeldas Letter', c.pool)
        self.assertNotIn('Zeldas Lullaby', c.pool)
        self.assertFalse(c.allowed('Zeldas Lullaby', SARIA))
        self.assertEqual(c.base.get('Song from Impa'), 'Zeldas Lullaby')

    def test_native_castle_gift_cannot_give_a_phantom_letter(self):
        extra = sources()
        extra[LETTER] = source('quest', LETTER, 'Npc', 'HC Zeldas Letter', 'Item_ZeldaLetter',
                               'Zeldas Letter', 'Event/EventFlow/Dm_HrlCastle_0050.bfevfl.zs')
        for skip in (False, True):
            with self.subTest(skip=skip):
                options = dict(rando_options.defaults(), skip_child_zelda=skip, tokensanity='all',
                               shuffle_quest_rewards=True)
                c = prepare(self.data, options, {}, [], 'castle-letter', True, extra=extra)
                self.assertEqual(c.base.get(vname(LETTER)), None if skip else 'Zeldas Letter')
                if skip:
                    state, _, _ = c.sweep({})
                    self.assertFalse(state.has('Zeldas Letter'))
                    self.assertFalse(state.has('Zeldas Lullaby'))
                    self.assertTrue(state.has('Met Zelda'))

    def test_ranch_without_the_letter(self):
        # The ranch reads the castle quest ('Met Zelda'), never the letter item: with or
        # without the castle skip, Malon and Talon's cuccos need no Zelda's Letter.
        for skip, expected in ((True, True), (False, True)):
            options = dict(rando_options.defaults(), skip_child_zelda=skip)
            logic = Logic(self.data, ap_settings(options, True))
            items = Counter({item: 9 for item in logic.referenced if item not in ('Zeldas Letter', 'Met Zelda')})
            _, found, _ = logic.sweep({'Song from Malon': None, 'LLR Talons Chickens': None},
                                      logic.new_state(items))
            for location in ('Song from Malon', 'LLR Talons Chickens'):
                self.assertEqual(location in found, expected, (skip, location))


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class CastleFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.patching.quest_guard import CHALLENGES, challenge_steps
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)
        cls.steps = challenge_steps(cls.read(cls, CHALLENGES))

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        return self.decompress(self.nup.read(self.nup.latest('romfs/' + path)), self.d)

    def test_kokiri_wait_for_the_deku_tree(self):
        # 19/11: Zelda met from the start put every Kokiri in its after-death state.
        from oot_rando.formats import byml_codec
        from oot_rando.game.world_maps import effective_members
        members = effective_members(self.nup)
        schedules, flows = cs.kokiri_paths(members)
        self.assertIn('Component/AIScheduleParam/Npc_Kokiri_Mido_Child.game__component__AIScheduleParam.bgyml',
                      schedules)
        changed = 0
        for path in schedules:
            new, count = cs.kokiri_schedule(self.nup.read(members[path]))   # stored uncompressed
            changed += count
            flags = [e.get('ConditionFlag') for e in byml_codec.load(new)['root'].get('ConditionalSchedule', [])]
            self.assertNotIn(cs.CASTLE_DONE_STATE, flags, path)
        self.assertGreaterEqual(changed, 10)
        talks = 0
        for path in flows:
            new, events = cs.kokiri_talk(self.decompress(self.nup.read(members[path]), self.d))
            talks += len(events)
            names = [e.data.params.data.get('GameDataName') for e in parse_flow(new).flowchart.events
                     if getattr(e.data, 'params', None) is not None]
            self.assertNotIn(cs.CASTLE_DONE_STATE, names, path)
        self.assertGreater(talks, 5)

    def test_village_saria_waits_for_the_deku_tree(self):
        # 20/11: with Zelda met from the start the village Saria was deleted at once.
        import ainb
        raw = self.nup.read(self.nup.latest('romfs/' + cs.SARIA_MODULE))    # stored uncompressed
        new, report = cs.saria_waits_for_deku_tree(raw)
        before = ainb.AINB.from_binary(raw).as_dict()
        after = ainb.AINB.from_binary(new).as_dict()
        strings = lambda doc: [s['Default Value'] for n in doc['Nodes']
                               for s in n.get('Parameters', {}).get('Inputs', {}).get('String', [])]
        self.assertNotIn(cs.CASTLE_DONE_STATE, strings(after))
        self.assertEqual(after['Nodes'][15]['Parameters']['Inputs']['String'][0]['Default Value'],
                         cs.DEKU_TREE_DONE_STATE)
        after['Nodes'][15]['Parameters']['Inputs']['String'][0]['Default Value'] = cs.CASTLE_DONE_STATE
        self.assertEqual(after, before)    # nothing else changed
        self.assertEqual(report['after'], cs.DEKU_TREE_DONE_STATE)
        with self.assertRaises(ValueError):
            cs.saria_waits_for_deku_tree(new)    # never twice

    def test_start_requests_copy_the_native_ones(self):
        steps = cs.start_step_params(self.read)
        self.assertEqual([(p['ChallengeName'], p['StepName']) for _, p in steps],
                         [(c, s) for _, _, c, s in cs.START_STEPS])
        self.assertTrue(all(p['IsIgnoreChallengeProgressUI'] for _, p in steps))
        from oot_rando.patching.event_patch import add_collection_markers
        opening, _ = add_collection_markers(self.read(cs.OPENING_FLOW), {'Event3': 'RandoSeed.test'})
        raw, names = cs.add_start_steps(opening, steps)
        self.assertEqual(names, cs.step_event_names())
        before, after = params_by_event(parse_flow(opening)), params_by_event(parse_flow(raw))
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)
        self.assertEqual({k: v for k, v in after.items() if k not in before}, dict(steps))
        with self.assertRaises(ValueError):
            cs.add_start_steps(raw, steps)    # never twice

    def test_start_requests_run_once_the_forest_is_shown(self):
        # Black screen at a new game: the requests ran in Opening_LoadingKokiriForest,
        # before its loading screen closes. They belong to Opening_Introduction, right
        # after its own quest request.
        from oot_rando.patching.event_patch import add_collection_markers
        opening, _ = add_collection_markers(self.read(cs.OPENING_FLOW), {'Event3': 'RandoSeed.test'})
        raw, names = cs.add_start_steps(opening, cs.start_step_params(self.read))
        chart = parse_flow(raw).flowchart
        entries = {e.name: e.main_event.v for e in chart.entry_points}

        def chain(event):
            seen = []
            while event is not None and getattr(event.data, 'nxt', None) is not None:
                seen.append(event.name)
                event = event.data.nxt.v
            return seen + ([event.name] if event is not None else [])
        loading = chain(entries['Opening_LoadingKokiriForest'])
        self.assertFalse(set(names) & set(loading))
        intro = chain(entries['Opening_Introduction'])
        start = intro.index('Event8')
        self.assertEqual(intro[start + 1:start + 1 + len(names)], names)
        self.assertEqual(intro[start + 1 + len(names)], 'Event31')

    def test_castle_requests_wait_for_the_quest(self):
        for path in cs.GUARDED_FLOWS:
            raw, guarded = cs.guard_flow(path, self.read(path), self.steps)
            self.assertTrue(guarded, path)
            for _, step, expression in guarded:
                if expression == cs.CASTLE_DONE:
                    self.assertIn(step, ('Step02', 'Step03', 'Step03_02', 'Step04'))
                else:
                    self.assertEqual((step, expression), ('Step01', cs.DOOR_PAST_STEP01))
            self.assertNotIn('Complete', [step for _, step, _ in guarded])

    def test_start_values_are_saved_flags(self):
        from oot_rando.patching.key_adapter import check_start_values
        from oot_rando.patching.quest_guard import check_expressions
        gamedata = self.read('GameData/GameDataList.Product.110.byml.zs')
        check_start_values(gamedata, cs.START_VALUES)
        check_expressions(gamedata, [cs.CASTLE_DONE, cs.DOOR_PAST_STEP01])


if __name__ == '__main__':
    unittest.main()
