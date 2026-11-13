"""Night-only gold skulltulas present day and night. NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.formats import byml_codec
from oot_rando.formats.byml_writer import patch_strings
from oot_rando.formats.inspect_resources import Byml
from oot_rando.patching.qol_patches import (NOCTURNAL_FIELD, NOCTURNAL_SKULLTULA_MAPS, is_nocturnal_skulltula,
                                            nocturnal_skulltula_edits)
from oot_rando.randomizer.randomizer_core import Settings, settings_identity

NUP = os.environ.get('OOT_NUP')


def _map(actors):
    return byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': actors}})


class PatchTests(unittest.TestCase):
    def test_existing_boolean_replaced(self):
        raw = _map([{'Gyaml': 'A', 'Dynamic': {'Flag': True, 'Name': 'x'}}])
        patched = patch_strings(raw, [{'path': ('Actors', 0, 'Dynamic', 'Flag'), 'before': True, 'after': False}])
        self.assertEqual(Byml(patched).root, {'Actors': [{'Gyaml': 'A', 'Dynamic': {'Flag': False, 'Name': 'x'}}]})
        self.assertEqual(patched[16:len(raw)], raw[16:])   # append-only after the header

    def test_boolean_edit_preconditions(self):
        raw = _map([{'Gyaml': 'A', 'Dynamic': {'Flag': False, 'Name': 'x'}}])
        for before, after, key in ((True, False, 'Flag'),    # wrong current value
                                   (True, False, 'Name'),    # not a boolean
                                   ('x', True, 'Name'),      # string to boolean
                                   (False, 'y', 'Flag')):    # boolean to string
            with self.subTest(before=before, after=after, key=key), self.assertRaises(ValueError):
                patch_strings(raw, [{'path': ('Actors', 0, 'Dynamic', key), 'before': before, 'after': after}])

    def test_only_nocturnal_gold_skulltulas_edited(self):
        actors = [{'Gyaml': 'Enemy_Skulltula_Gold', 'Dynamic': {NOCTURNAL_FIELD: True}},
                  {'Gyaml': 'Enemy_Skulltula_Gold', 'Dynamic': {'Enemy_Skulltula_Gold_AppearPopOut': True}},
                  {'Gyaml': 'Enemy_Skulltula', 'Dynamic': {NOCTURNAL_FIELD: True}},
                  {'Gyaml': 'Enemy_Skulltula_Gold'},
                  {'Gyaml': 'Enemy_Skulltula_Gold', 'Dynamic': {NOCTURNAL_FIELD: True, 'Drop__DropActor': 'X'}}]
        edits = nocturnal_skulltula_edits({'Actors': actors})
        self.assertEqual([e['path'][1] for e in edits], [0, 4])
        root = Byml(patch_strings(_map(actors), edits)).root
        self.assertFalse(any(is_nocturnal_skulltula(a) for a in root['Actors']))
        self.assertEqual(root['Actors'][4]['Dynamic'], {NOCTURNAL_FIELD: False, 'Drop__DropActor': 'X'})
        self.assertEqual(root['Actors'][2], actors[2])


class SettingsTests(unittest.TestCase):
    def test_off_by_default_and_identity_kept(self):
        settings = Settings('identity')
        self.assertFalse(settings.skulltulas_always_present)
        self.assertNotIn('skulltulas_always_present', settings.to_dict())
        enabled = Settings('identity', skulltulas_always_present=True)
        self.assertTrue(Settings.from_dict(enabled.to_dict()).skulltulas_always_present)
        self.assertNotEqual(settings_identity(settings), settings_identity(enabled))
        with self.assertRaises(ValueError):
            Settings('identity', skulltulas_always_present=1).validate()

    def test_alone_is_a_valid_seed(self):
        Settings('night', randomize_chests=False, open_forest=False, skulltulas_always_present=True).validate_supported()

    def test_archipelago_patch_keeps_it_local(self):
        from oot_rando.archipelago import bridge
        self.assertIn('skulltulas_always_present', bridge.settings_from_patch.__code__.co_varnames)


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class NupTests(unittest.TestCase):
    def test_every_nocturnal_skulltula_map_is_listed(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        try:
            d, members = dictionaries(nup), effective_members(nup)
            found, total = set(), 0
            for path in sorted(p for p in members if p.startswith('Banc/') and p.endswith('.bcett.byml.zs')):
                raw = decompress(nup.read(members[path]), d)
                if NOCTURNAL_FIELD.encode() not in raw:
                    continue
                root = Byml(raw).root
                edits = nocturnal_skulltula_edits(root)
                if not edits:
                    continue
                found.add(path)
                total += len(edits)
                after = Byml(patch_strings(raw, edits)).root
                self.assertFalse(any(is_nocturnal_skulltula(a) for a in after['Actors']))
                for index, (a, b) in enumerate(zip(root['Actors'], after['Actors'])):
                    if is_nocturnal_skulltula(a):
                        a = dict(a, Dynamic=dict(a['Dynamic'], **{NOCTURNAL_FIELD: False}))
                    self.assertEqual(a, b)
            self.assertEqual(found, set(NOCTURNAL_SKULLTULA_MAPS))
            self.assertEqual(total, 30)
        finally:
            nup.stream.close()


if __name__ == '__main__':
    unittest.main()
