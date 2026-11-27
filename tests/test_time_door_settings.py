"""Door requirements agree across the solver, saved settings and exported options."""
import _src_path  # noqa: F401
import itertools
import json
import unittest

from oot_rando.archipelago.bridge import to_ap_yaml
from oot_rando.archipelago.bridge import ap_option_specs
from oot_rando.gui import randomizer_gui as gui
from oot_rando.logic import rando_options
from oot_rando.logic.rules import Logic
from oot_rando.logic.world import World
from oot_rando.randomizer import settings_string
from oot_rando.randomizer.full_randomizer import ap_settings
from oot_rando.randomizer.randomizer_core import Settings, settings_identity


NAME = 'door_of_time_requirement'


class DoorRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World()

    def test_door_truth_table_and_open_override(self):
        items = ('Ocarina', 'Song of Time', 'Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire')
        for requirement, opened, escape in itertools.product(('song', 'vanilla', 'all'), (False, True),
                                                             ('all', 'vanilla')):
            options = rando_options.validate({NAME: requirement, 'open_door_of_time': opened,
                                             'spiritual_stones': escape})
            logic = Logic(self.world, ap_settings(options, True))
            rule = dict(logic.regions['Temple of Time']['exits'])['Beyond Door of Time']
            for mask in range(1 << len(items)):
                counts = {item: 1 for bit, item in enumerate(items) if mask >> bit & 1}
                state = logic.new_state(counts)
                stones = (requirement == 'song' or
                          all(item in counts for item in ('Goron Ruby', 'Zora Sapphire')) and
                          (requirement != 'all' or 'Kokiri Emerald' in counts))
                expected = opened or ('Ocarina' in counts and 'Song of Time' in counts and stones)
                self.assertEqual(bool(rule(state, state.counts, 'child')), expected,
                                 (requirement, opened, escape, counts))

    def test_shared_escape_stones_truth_table(self):
        from oot_rando.patching.story_fixes import escape_stones
        items = ('Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire', 'Met Zelda')
        locations = ('HF Ocarina of Time Item', 'Song from Ocarina of Time')
        for requirement in ('song', 'vanilla', 'all'):
            options = rando_options.validate({NAME: requirement, 'spiritual_stones': 'door'})
            self.assertEqual(options['spiritual_stones'], 'door')
            self.assertEqual(len(escape_stones(options)), {'song': 0, 'vanilla': 2, 'all': 3}[requirement])
            logic = Logic(self.world, ap_settings(options, True))
            rules = dict(logic.location_rules)
            for mask in range(1 << len(items)):
                counts = {item: 1 for bit, item in enumerate(items) if mask >> bit & 1}
                stones = (requirement == 'song' or
                          all(item in counts for item in ('Goron Ruby', 'Zora Sapphire')) and
                          (requirement != 'all' or 'Kokiri Emerald' in counts))
                for location in locations:
                    expected = stones and (requirement == 'song' or 'Met Zelda' in counts or
                                            location == 'HF Ocarina of Time Item' and requirement == 'all')
                    for age in ('child', 'adult'):
                        state = logic.new_state(counts)
                        actual = any(rule(state, state.counts, age) for _, rule in rules[location])
                        self.assertEqual(bool(actual), bool(expected and age == 'child'),
                                         (requirement, location, age, counts))
            rebuilt = Logic(self.world, json.loads(json.dumps(logic.settings)))
            self.assertEqual(rebuilt.settings, logic.settings)

    def test_new_escape_choice_is_independent_of_the_door(self):
        from oot_rando.patching.story_fixes import escape_stones, STONE_SETS
        for door, escape, opened in itertools.product(('song', 'vanilla', 'all'),
                                                       ('all', 'vanilla'), (False, True)):
            options = rando_options.validate({NAME: door, 'spiritual_stones': escape,
                                             'open_door_of_time': opened})
            self.assertEqual(escape_stones(options), STONE_SETS[escape])
            logic = Logic(self.world, ap_settings(options, True))
            rules = dict(logic.location_rules)['Song from Ocarina of Time']
            for emerald in (False, True):
                counts = {'Goron Ruby': 1, 'Zora Sapphire': 1, 'Met Zelda': 1}
                if emerald:
                    counts['Kokiri Emerald'] = 1
                state = logic.new_state(counts)
                self.assertEqual(any(rule(state, state.counts, 'child') for _, rule in rules),
                                 escape == 'vanilla' or emerald, (door, escape, opened))
        self.assertEqual(escape_stones(rando_options.defaults()), STONE_SETS['all'])

    def test_saved_tracker_logic_retains_the_choice(self):
        for requirement in ('all', 'vanilla', 'song'):
            options = rando_options.validate({NAME: requirement})
            settings = ap_settings(options, True)
            self.assertEqual(Logic(self.world, json.loads(json.dumps(settings))).settings[NAME], requirement)
        self.assertEqual(Logic(self.world).settings[NAME], 'song')

    def test_option_ui_and_yaml_round_trip(self):
        option = rando_options.BY_NAME[NAME]
        self.assertEqual((option.allowed(), option.default), (('all', 'vanilla', 'song'), 'song'))
        self.assertIn(NAME, next(names for title, _, names in gui.SETTING_GROUPS if title == 'Open world'))
        self.assertIn("escape are a separate setting",
                      gui.option_tip(option, option.label, option.help))
        spec = next(spec for spec in ap_option_specs() if spec['name'] == NAME)
        self.assertEqual((spec['values'], spec['default']), (['all', 'vanilla', 'song'], 'song'))
        for value in option.allowed():
            values = rando_options.validate({NAME: value}, supported_only=True)
            imported, ignored = rando_options.from_ap_yaml(to_ap_yaml(values))
            self.assertEqual((imported[NAME], ignored), (value, []))
        with self.assertRaises(ValueError):
            rando_options.validate({NAME: 'emerald'})

    def test_old_seed_identity_and_strings_keep_song_only(self):
        def full_settings(value='song'):
            settings = Settings('time-door', randomize_chests=False,
                                full=rando_options.validate({NAME: value}))
            settings.categories = dict.fromkeys(settings.categories, False)
            return settings.validate()

        current = full_settings()
        older = current.to_dict()
        self.assertNotIn(NAME, older['full'])
        restored = Settings.from_dict(json.loads(json.dumps(older)))
        self.assertEqual(restored.full[NAME], 'song')
        self.assertEqual(settings_identity(restored), settings_identity(current))
        self.assertEqual(rando_options.stored_value({}, NAME), 'song')
        for value in ('all', 'vanilla', 'song'):
            settings = full_settings(value)
            decoded, _ = settings_string.decode(settings_string.encode(settings))
            self.assertEqual(decoded.full[NAME], value)
            self.assertEqual(settings_identity(decoded), settings_identity(settings))
            if value != 'song':
                self.assertNotEqual(settings_identity(settings), settings_identity(current))


if __name__ == '__main__':
    unittest.main()
