"""The New seed form keeps its own settings when a seed is opened or reloaded."""
import unittest
from unittest.mock import Mock, patch

import _src_path  # noqa: F401
from oot_rando.gui.randomizer_gui import Application


class OpenedSeedLeavesTheFormTests(unittest.TestCase):
    def test_opening_a_seed_does_not_fill_the_new_seed_form(self):
        app = Application.__new__(Application)
        app.busy, app.party_context = False, None
        for name in ('match_party', 'write_app_state', 'follow_newest_save', 'load_tracker',
                     'set_archipelago_seed', 'reset_spoiler', 'apply_settings', 'apply_full'):
            setattr(app, name, Mock())
        app.result, app.seed_chip, app.status = Mock(), Mock(), Mock()
        app.result.get.return_value = ''
        app.auto_save = Mock(get=Mock(return_value=False))
        manifest = {'settings': {'seed': 'old-seed', 'full': {'starting_age': 'adult'}},
                    'seed_id': 'f' * 64, 'files': []}
        with patch('oot_rando.gui.randomizer_gui.read_artifact', return_value=(manifest, None)), \
                patch('oot_rando.gui.randomizer_gui.regeneration_settings', return_value=None):
            app.use_artifact('seed-folder')
        app.apply_settings.assert_not_called()
        app.apply_full.assert_not_called()
        self.assertEqual(app.seed_name, 'old-seed')


if __name__ == '__main__':
    unittest.main()
