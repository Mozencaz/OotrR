import _src_path  # noqa: F401  (src on sys.path)
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oot_rando.tracker.auto_tracker import TrackerSession
from oot_rando.randomizer.randomizer_core import Settings, settings_identity, GENERATOR_VERSION, ADAPTER_VERSION
from oot_rando.patching.randomize_kokiri import TITLE, BUILD


class AutoTrackerTests(unittest.TestCase):
    def make_session(self, base):
        root = base / 'seed'
        (root / 'romfs').mkdir(parents=True)
        (root / 'romfs' / 'resource').write_bytes(b'unchanged')
        settings = Settings('auto-test')
        ident = settings_identity(settings)
        checks = [{'id': 'chest', 'name': 'Chest', 'region': 'Kokiri'},
                  {'id': 'future', 'name': 'Other chest', 'region': 'Kokiri'}]
        metadata = {'schema_version': 1, 'seed_id': ident, 'seed_marker': '100', 'inventory': [],
                    'known_bool64': ['10', '11'], 'checks': {
                        'chest': {'collection': {'type': 'bool64', 'hash': '10'}, 'reward': 'Hookshot',
                                  'item': 'Progressive Hookshot', 'logic': 'exact', 'location': 'Remake|chest'},
                        'future': {'collection': {'type': 'bool64', 'hash': '11'}, 'reward': 'SECRET',
                                   'item': 'Bow', 'logic': 'exact', 'location': 'Remake|future'}}}
        tracking = json.dumps(metadata).encode()
        (root / 'tracking.json').write_bytes(tracking)
        manifest = {'schema_version': 1, 'title_id': TITLE, 'build_id': BUILD,
                    'generator_version': GENERATOR_VERSION, 'adapter_version': ADAPTER_VERSION,
                    'seed_id': ident, 'settings': settings.to_dict(),
                    'files': {'resource': {'size': 9, 'sha256': hashlib.sha256(b'unchanged').hexdigest()}},
                    'tracking': {'sha256': hashlib.sha256(tracking).hexdigest()}}
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (root / 'checks.json').write_text(json.dumps({'seed_id': ident, 'checks': checks}), encoding='utf-8')
        return TrackerSession(root, 'test', save_path=str(base / 'progress.sav'))

    def snapshot(self, flags=(10,), marker=True, fingerprint='one'):
        return {'bool': {100: marker}, 'bool64': dict.fromkeys(flags, True), 'bool64_complete': True,
                'int': {}, 'strings': {}, 'sha256': fingerprint, 'mtime_ns': 1_700_000_000_000_000_000}

    def test_reward_is_revealed_only_after_observed_collection_and_rollback_removes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(Path(directory))
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot()):
                self.assertEqual(session.refresh()['automatic'], 1)
            self.assertEqual(session.check_state('chest')['reward'], 'Hookshot')
            self.assertEqual(session.check_state('future')['reward'], '')
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot(flags=(), fingerprint='older')):
                session.refresh()
            self.assertFalse(session.completed)
            self.assertEqual(session.check_state('chest')['reward'], '')

    def test_foreign_seed_does_not_inherit_previous_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(Path(directory))
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot()):
                session.refresh()
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot(marker=False)):
                status = session.refresh()
            self.assertFalse(session.completed)
            self.assertIn('not linked', status['status'])

    def test_transient_error_keeps_last_good_state_and_recovers_even_without_new_save(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(Path(directory))
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot()):
                good = session.refresh()
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', side_effect=OSError('busy')):
                self.assertIn('last state kept', session.refresh()['status'])
            self.assertIn('chest', session.completed)
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot()):
                self.assertEqual(session.refresh(), good)

    def test_archipelago_goal_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(Path(directory))
            session.metadata['goal_marker'] = '200'
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot()):
                session.refresh()
            self.assertFalse(session.goal_reached)
            won = self.snapshot(fingerprint='won')
            won['bool'][200] = True
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=won):
                session.refresh()
            self.assertTrue(session.goal_reached)
            # Back at the title (flag unsaved): the goal stays reached for this save.
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot(fingerprint='x')):
                session.refresh()
            self.assertTrue(session.goal_reached)

    def test_unknown_sparse_key_is_not_treated_as_uncollected(self):
        self.assertIsNone(TrackerSession._collected({'type': 'bool64', 'hash': '123'},
                          self.snapshot(), {'known_bool64': ['10']}))

    def test_access_search_never_receives_future_rewards(self):
        class Logic:
            referenced = set()
            virtual = {'Remake|chest': [], 'Remake|future': []}
            def location_names(self):
                return []
            def new_state(self, counts):
                return counts
            def sweep(self, placements, state):
                self_test.assertTrue(all(value is None for value in placements.values()))
                self_test.assertNotIn('Bow', state)
                return state, {'Remake|chest'}, []
        self_test = self
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(Path(directory))
            session._logic = Logic()
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot()):
                session.refresh()
            self.assertEqual(session.check_state('chest')['access'], 'available')
            self.assertEqual(session.check_state('future')['access'], 'blocked')


    def test_vanilla_and_area_checks_get_an_access_state(self):
        class Logic:
            referenced = set()
            virtual = {'Remake|area': ['Near', 'Far'], 'Remake|far': ['Far']}
            def location_names(self):
                return ['Near', 'Far', 'Vanilla Spot', 'Vanilla Far']
            def new_state(self, counts):
                return counts
            def sweep(self, placements, state):
                return state, {'Near', 'Vanilla Spot'}, []
            def accessible(self, state, member):
                return member == 'Near'
        with tempfile.TemporaryDirectory() as directory:
            session = self.make_session(Path(directory))
            session.metadata['checks'].update({
                'ap#Vanilla Spot': {'collection': None, 'logic': 'vanilla', 'location': None},
                'ap#Vanilla Far': {'collection': None, 'logic': 'vanilla', 'location': None},
                'area': {'collection': None, 'logic': 'area', 'location': 'Remake|area'},
                'far': {'collection': None, 'logic': 'area', 'location': 'Remake|far'}})
            session._logic = Logic()
            with patch('oot_rando.tracker.auto_tracker.load_snapshot', return_value=self.snapshot()):
                session.refresh()
            self.assertEqual(session.check_state('ap#Vanilla Spot')['access'], 'available')
            self.assertEqual(session.check_state('ap#Vanilla Far')['access'], 'blocked')
            self.assertEqual(session.check_state('area')['access'], 'partial')
            self.assertEqual(session.check_state('far')['access'], 'blocked')

if __name__ == '__main__':
    unittest.main()
