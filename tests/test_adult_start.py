"""Adult start (``starting_age`` = ``adult``). NUP-dependent tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest
from collections import Counter

from oot_rando.archipelago.bridge import to_ap_yaml
from oot_rando.logic import rando_options
from oot_rando.logic.rules import Logic
from oot_rando.logic.world import World
from oot_rando.patching import adult_start
from oot_rando.formats.evfl_tools import params_by_event, parse_flow

NUP = os.environ.get('OOT_NUP')
OPENING = 'Event/EventFlow/OpeningEvent.bfevfl.zs'


class AdultStartOptionTests(unittest.TestCase):
    def test_adult_is_supported_and_experimental(self):
        values = rando_options.validate({'starting_age': 'adult'}, supported_only=True)
        self.assertEqual(values['starting_age'], 'adult')
        self.assertIn('Starting age = adult', rando_options.experimental_choices(values))
        with self.assertRaises(ValueError):
            rando_options.validate({'starting_age': 'random'}, supported_only=True)

    def test_adult_start_opens_the_door_of_time(self):
        self.assertFalse(rando_options.validate({})['open_door_of_time'])
        values = rando_options.validate({'starting_age': 'adult', 'open_door_of_time': False}, supported_only=True)
        self.assertTrue(values['open_door_of_time'])

    def test_child_start_is_unchanged(self):
        self.assertEqual(rando_options.validate({})['starting_age'], 'child')
        self.assertFalse(rando_options.validate({'starting_age': 'child'})['open_door_of_time'])

    def test_enabled(self):
        self.assertTrue(adult_start.enabled({'starting_age': 'adult'}))
        self.assertFalse(adult_start.enabled({'starting_age': 'child'}))
        self.assertFalse(adult_start.enabled(None))

    def test_opening_waits_before_leaving(self):
        params = adult_start.event_params()
        self.assertEqual(next(iter(params)), adult_start.WAIT_EVENT)
        self.assertEqual(params[adult_start.WAIT_EVENT], {'IsWaitEnd': True, 'Frames': 30})

    def test_ap_yaml_round_trip(self):
        values = rando_options.validate({'starting_age': 'adult'}, supported_only=True)
        imported, ignored = rando_options.from_ap_yaml(to_ap_yaml(values))
        self.assertEqual(imported['starting_age'], 'adult')
        self.assertEqual(ignored, [])


class AdultStartLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logic = Logic(World(), {'open_forest': 'closed_deku', 'starting_age': 'adult',
                                    'open_door_of_time': True})

    def test_adult_reaches_the_temple_and_travels_back(self):
        state, _, _ = self.logic.sweep({'Master Sword Pedestal': 'Time Travel'}, self.logic.new_state(Counter()))
        self.assertIn('Temple of Time', state.reached['adult'])
        self.assertIn('Beyond Door of Time', state.reached['adult'])
        # The pedestal gives the child its way in: Link can be a child again.
        self.assertIn('KF Links House', state.reached['child'])

    def test_no_child_before_the_pedestal(self):
        state, _, _ = self.logic.sweep({}, self.logic.new_state(Counter()))
        self.assertIn('Beyond Door of Time', state.reached['adult'])
        self.assertNotIn('KF Links House', state.reached['child'])

    def test_child_start_cannot_be_adult_without_the_pedestal(self):
        logic = Logic(World(), {'open_forest': 'closed_deku'})
        state, _, _ = logic.sweep({}, logic.new_state(Counter()))
        self.assertIn('KF Links House', state.reached['child'])


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class AdultStartFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.raw = decompress(cls.nup.read(cls.nup.latest('romfs/' + OPENING)), cls.d)

    def test_opening_leaves_for_the_temple_of_time(self):
        raw, report = adult_start.patch_opening(self.raw)
        self.assertEqual(report['events'], list(adult_start.event_params()))
        before, after = params_by_event(parse_flow(self.raw)), params_by_event(parse_flow(raw))
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)
        self.assertEqual({k: v for k, v in after.items() if k not in before}, adult_start.event_params())
        events = {e.name: e for e in parse_flow(raw).flowchart.events}
        self.assertEqual(events[adult_start.ANCHOR].data.nxt.v.name, adult_start.WAIT_EVENT)
        wait = events[adult_start.WAIT_EVENT]
        self.assertEqual(wait.data.actor.v.identifier.name, 'EventSystemActor')
        self.assertEqual(wait.data.actor_action.v.v, 'EventWait')
        self.assertEqual(wait.data.nxt.v.name, adult_start.ARRIVAL_EVENTS[0])
        self.assertIsNone(events[adult_start.WARP_EVENT].data.nxt.v)
        with self.assertRaises(ValueError):
            adult_start.patch_opening(raw)    # never twice

    def test_castle_skip_requests_stay_in_the_chain(self):
        from oot_rando.patching import child_castle_skip as cs
        raw, _ = adult_start.patch_opening(self.raw)
        steps = cs.start_step_params(lambda p: __import__(
            'oot_rando.formats.inspect_resources', fromlist=['decompress']).decompress(
                self.nup.read(self.nup.latest('romfs/' + p)), self.d))
        raw, names = cs.add_start_steps(raw, steps)
        events = {e.name: e for e in parse_flow(raw).flowchart.events}
        chain, event = [], events[adult_start.ANCHOR].data.nxt.v
        while event is not None:
            chain.append(event.name)
            event = getattr(event.data, 'nxt', None) and event.data.nxt.v
        self.assertEqual(chain, names + [adult_start.WAIT_EVENT, *adult_start.ARRIVAL_EVENTS, adult_start.ERA_EVENT, adult_start.WARP_EVENT])


if __name__ == '__main__':
    unittest.main()
