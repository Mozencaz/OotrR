"""QoL controls survive imports and control the generated settings independently."""
import itertools
import tempfile
from pathlib import Path
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import _src_path  # noqa: F401
from oot_rando.archipelago.bridge import to_ap_yaml
from oot_rando.gui.randomizer_gui import Application, OPTIONS, SKIP_OPTIONS
from oot_rando.logic import rando_options
from oot_rando.randomizer.randomizer_core import Settings
from oot_rando.randomizer import settings_string
from oot_rando.tracker.turbo_a import ATurbo


class QolOptionsTests(unittest.TestCase):
    def setUp(self):
        self.tcl = tk.Tcl()
        self.app = Application.__new__(Application)
        self.app.seed = tk.StringVar(self.tcl, 'qol-options')
        self.app.options = {name: tk.BooleanVar(self.tcl, True) for name, _ in OPTIONS}
        self.app.options['randomize_chests'].set(False)
        self.app.full_enabled = tk.BooleanVar(self.tcl, False)
        self.app.full_vars = {option.name: tk.BooleanVar(self.tcl, option.default)
                              for option in rando_options.OPTIONS if option.kind == 'bool'}
        self.app.pool, self.app.excluded, self.app.categories = {}, {}, {}
        self.app.update_category_states = Mock()

    def test_each_skip_combination_round_trips_without_forcing_on(self):
        for flags in itertools.product((False, True), repeat=len(SKIP_OPTIONS)):
            for (name, _), flag in zip(SKIP_OPTIONS, flags):
                self.app.options[name].set(flag)
            settings = self.app.get_settings()
            restored, _ = settings_string.decode(settings_string.encode(settings))
            self.app.apply_settings(restored)
            for (name, _), flag in zip(SKIP_OPTIONS, flags):
                self.assertEqual(self.app.options[name].get(), flag)
                self.assertEqual(getattr(self.app.get_settings(), name), flag)

    def test_old_fast_chests_import_can_be_turned_off(self):
        self.app.apply_full = Mock()
        self.app.apply_settings(Settings('legacy', randomize_chests=False,
                                         full=rando_options.validate({'fast_chests': True})))
        self.assertTrue(self.app.options['skip_chest_cutscenes'].get())
        for enabled in (False, True):
            self.app.options['skip_chest_cutscenes'].set(enabled)
            self.assertEqual(self.app.full_values()['fast_chests'], enabled)

    def test_turbo_toggle_persists_without_stopping_input_forwarding(self):
        self.app.turbo_enabled = tk.BooleanVar(self.tcl, False)
        self.app.turbo_status = tk.StringVar(self.tcl)
        self.app.turbo = SimpleNamespace(enabled=True, running=True, stop=Mock())
        self.app.write_app_state = Mock()
        self.app.turbo_toggled()
        self.app.write_app_state.assert_called_once_with(turbo_a=False)
        self.assertFalse(self.app.turbo.enabled)
        self.assertTrue(self.app.turbo.status.startswith('Turbo A off'))
        self.app.turbo.stop.assert_not_called()

    def test_yaml_import_updates_shared_chest_control_both_ways(self):
        self.app.apply_full = Mock()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'options.yaml'
            for enabled in (False, True):
                self.app.options['skip_chest_cutscenes'].set(not enabled)
                path.write_text(to_ap_yaml({'fast_chests': enabled}), encoding='utf-8')
                with patch('oot_rando.gui.randomizer_gui.filedialog.askopenfilename', return_value=str(path)), \
                     patch.object(self.app, 'notify'), patch.object(self.app, 'show_notice'):
                    self.app.import_ap_yaml()
                self.assertEqual(self.app.options['skip_chest_cutscenes'].get(), enabled)
                self.assertEqual(self.app.full_values()['fast_chests'], enabled)

    def test_disabling_turbo_during_hold_preserves_held_a_and_release(self):
        turbo = ATurbo()
        turbo.step(True, False, 0.0, event=True)
        # At 0.36 repetition normally releases A between taps.
        self.assertFalse(turbo.step(True, False, 0.36, event=True))
        self.assertTrue(turbo.step(True, False, 0.37, event=True, enabled=False))
        self.assertTrue(turbo.step(True, False, 0.46, event=True, enabled=False))
        self.assertFalse(turbo.step(False, False, 0.47, event=True, enabled=False))


if __name__ == '__main__':
    unittest.main()
