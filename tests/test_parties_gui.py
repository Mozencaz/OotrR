"""Tk integration tests with an isolated library (never touch installed games)."""
import _src_path  # noqa: F401
import json
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from test_parties import artifact
from oot_rando.parties import PartyLibrary
from oot_rando.patching.randomize_kokiri import TITLE
from oot_rando.gui.randomizer_gui import Application
from oot_rando.randomizer.randomizer_core import Settings


class PartiesGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.addCleanup(self.root.destroy)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.patches = []
        def mock(target, **kwargs):
            manager = patch(target, **kwargs)
            self.patches.append(manager)
            result = manager.start()
            self.addCleanup(manager.stop)
            return result
        mock('oot_rando.parties.running_game', return_value=None)
        self.library = PartyLibrary(self.base / 'Parties')
        mock('oot_rando.gui.parties_page.PartyLibrary', return_value=self.library)
        mock('oot_rando.gui.randomizer_gui.STATE', new=self.base / 'state')
        mock('oot_rando.gui.randomizer_gui.Application.read_app_state', return_value={'parties_enabled': True})
        mock('oot_rando.gui.randomizer_gui.Application.register_hotkey')
        mock('oot_rando.gui.randomizer_gui.Application.start_turbo')
        mock('oot_rando.gui.randomizer_gui.Application.restore_last_artifact')
        mock('oot_rando.gui.randomizer_gui.updater.cleanup')
        mock('oot_rando.gui.randomizer_gui.Application.check_for_updates')
        self.errors = []
        mock('oot_rando.gui.randomizer_gui.Application.error', side_effect=lambda error: self.errors.append(str(error)))
        self.app = Application(self.root)
        self.addCleanup(lambda: setattr(self.app, 'closed', True))
        self.mods = self.base / 'load' / TITLE
        self.mods.mkdir(parents=True)
        self.saves = self.base / 'save' / 'account'
        self.a = self.library.create('Aventure tranquille', artifact(self.base / 'seeds', 'A'), self.mods, self.saves)
        self.b = self.library.create('Défi des amis', artifact(self.base / 'seeds', 'B'), self.mods, self.saves)
        self.app.render_parties()
        self.app.show_page('parties')
        self.root.update()

    def finish_job(self):
        deadline = time.monotonic() + 10
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.root.update()
        self.assertFalse(self.app.busy)
        self.assertFalse(self.errors, self.errors)

    def test_real_job_activates_and_restores_named_party(self):
        self.app.activate_party(self.a['id'])
        self.finish_job()
        self.assertEqual(self.app.party_context['id'], self.a['id'])
        self.assertEqual(self.app.home_seed.get(), 'Aventure tranquille')
        self.assertEqual(self.app.seed_chip.get(), 'Aventure tranquille')
        self.assertEqual(self.app.tracker.manual.path.parent, self.library.tracker_dir(self.a['id']))
        self.assertEqual(self.app.save_path.get(), '')
        save = self.saves / 'slot_00/progress.sav'
        save.parent.mkdir(parents=True)
        save.write_bytes(b'progress')
        # A much newer save outside the party must never become its tracker source.
        unrelated = self.base / 'other-account/slot_02/progress.sav'
        unrelated.parent.mkdir(parents=True)
        unrelated.write_bytes(b'other')
        os.utime(unrelated, (9999999999, 9999999999))
        self.app.follow_newest_save()
        self.assertEqual(Path(self.app.save_path.get()), save)
        self.app.ap_address.set('example.invalid:12345')
        self.app.ap_password.set('do-not-carry')
        self.app.activate_party(self.b['id'])
        self.finish_job()
        self.assertEqual(self.app.ap_password.get(), '')
        self.assertEqual(self.app.save_path.get(), '')
        self.app.activate_party(self.a['id'])
        self.finish_job()
        self.assertEqual(self.app.ap_address.get(), 'example.invalid:12345')
        self.assertEqual(save.read_bytes(), b'progress')

    def test_busy_clicks_cannot_create_an_orphan_or_switch_context(self):
        self.app.busy = True
        self.app.activate_party(self.a['id'])
        self.app.new_party()
        self.assertIsNone(self.library.active_id)
        self.assertIsNone(self.app.party_context)
        self.app.busy = False

    def test_existing_manual_checks_import_once_into_independent_party_profile(self):
        self.library.activate(self.a['id'])
        imported = self.library.folder(self.a['id']) / 'imported-tracker.json'
        imported.write_text(json.dumps({'seed_id': self.a['seed_id'], 'completed': []}))
        self.app.party_opened(self.library.get(self.a['id']))
        self.assertFalse(imported.exists())
        self.assertTrue(imported.with_suffix('.imported').exists())

    def test_filter_and_minimum_window_layout(self):
        self.root.geometry('1040x720')
        self.app.party_search.set('AMIS')
        self.root.update()
        self.assertEqual(len(self.app.parties_rows.winfo_children()), 1)
        self.assertLessEqual(self.app.parties_rows.winfo_reqwidth(), self.root.winfo_width())
        self.app.party_search.set('absent')
        self.root.update()
        self.assertEqual(len(self.app.parties_rows.winfo_children()), 1)

    def test_generation_stages_the_seed_before_installing_a_named_party(self):
        self.app.party_name.set('Nouvelle aventure')
        targets = []
        def generate(nup, mods, settings, archive, progress):
            targets.append(Path(mods))
            self.assertNotEqual(Path(mods), self.mods)
            self.assertEqual(Path(mods).name, TITLE)
            self.assertIsNone(self.library.active_id)
            return artifact(Path(mods), settings.seed)
        with patch.object(self.app, 'party_destination', return_value=self.saves), \
                patch('oot_rando.gui.parties_page.generate_isolated', side_effect=generate), \
                patch.object(self.app, 'notify'):
            self.app.generate_party(self.base / 'game.nup', self.mods, Settings('Generated'))
            self.finish_job()
        self.assertEqual(self.app.party_context['name'], 'Nouvelle aventure')
        self.assertEqual(len(targets), 1)
        self.assertFalse(targets[0].exists())
        self.assertTrue((self.app.artifact / 'manifest.json').exists())

    def test_regeneration_keeps_the_original_party_and_copies_its_save(self):
        self.library.activate(self.a['id'])
        self.app.party_opened(self.library.get(self.a['id']))
        save = self.saves / 'slot_00/progress.sav'
        save.parent.mkdir(parents=True)
        save.write_bytes(b'original-progress')
        def generate(nup, mods, settings, archive, progress):
            import shutil
            # The original mod is staged here so the existing generation service
            # can preserve save_seed_id and saves_from during regeneration.
            self.assertTrue((Path(mods) / self.a['mod_name'] / 'manifest.json').exists())
            shutil.rmtree(Path(mods) / self.a['mod_name'])
            return artifact(Path(mods), settings.seed)
        with patch.object(self.app, 'party_display_name', return_value='Aventure mise à jour'),                 patch.object(self.app, 'party_destination', return_value=self.saves), \
                patch('oot_rando.gui.parties_page.generate_isolated', side_effect=generate), \
                patch.object(self.app, 'notify'), \
                patch.object(self.app, 'offer_save_migration'):
            self.app.generate_party(self.base / 'game.nup', self.mods, Settings('A'), continuing=self.app.party_context)
            self.finish_job()
        self.assertNotEqual(self.library.active_id, self.a['id'])
        self.assertEqual(save.read_bytes(), b'original-progress')
        self.assertTrue(self.library.get(self.a['id']))


class PartiesOptInTests(unittest.TestCase):
    def test_disabled_by_default(self):
        import tkinter as tk
        from oot_rando.gui.parties_page import PartiesPage

        class Fake(PartiesPage):
            app_state = {}
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('Tk is not available')
        try:
            fake = Fake()
            fake.parties_enabled = tk.BooleanVar(value=fake.app_state.get('parties_enabled') is True)
            self.assertFalse(fake.parties_enabled.get())
            self.assertFalse(fake.restore_party())
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
