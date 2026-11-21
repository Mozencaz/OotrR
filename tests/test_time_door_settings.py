"""Door requirements agree across the solver, saved settings and exported options."""
import _src_path  # noqa: F401
import itertools
import json
import unittest

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
        self.assertIn('separate', gui.option_tip(option, option.label, option.help))
        spec = next(spec for spec in ap_option_specs() if spec['name'] == NAME)
        self.assertEqual((spec['values'], spec['default']), (['all', 'vanilla', 'song'], 'song'))
        for value in option.allowed():
            values = rando_options.validate({NAME: value}, supported_only=True)
            imported, ignored = rando_options.from_ap_yaml(rando_options.to_ap_yaml(values))
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
