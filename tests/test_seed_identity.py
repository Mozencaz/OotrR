"""Frozen seed identities (no game needed).

``settings_identity`` hashes ``Settings.to_dict()``: the seed id of every installed seed,
party and Archipelago slot depends on its exact shape (omitted defaults, legacy names,
sorted lists). A refactor of ``Settings`` or ``rando_options`` must keep these values.

If one changes on purpose (a new option recorded in every seed, a preset changed), bump
``GENERATOR_VERSION`` in randomizer_core.py and update the value here in the same commit.
"""
import _src_path  # noqa: F401
import unittest

from oot_rando.logic import rando_options
from oot_rando.randomizer.randomizer_core import Settings, settings_identity

EXPECTED = {
    'prudent_default': 'a280da56243598d2469066cba429ca2a95b01e61a30e25257be7ba28d3191787',
    'no_chests': 'bbd0ec1f72cc2708fb351baef03e79c6be9b6e1d09805bf8a553584bfbbe9cff',
    'skips': '0275deda9945d927524541c6168306b8cdba519f9b600ae149966f679fc6bbea',
    'legacy_skip_intro': '2ef2d6c2eddc8f97631e186127694c7e3c33f8d7c583615093d22ca54aed69dd',
    'full_ap_defaults': '3a885cc92851f1309bd110281820631da628714af0cf8fa066c6de0cc600978d',
    'full_everything': '567d59f414cf25c5113fc8c5e71ebbd704fd51ec35fa050448fddd73d2b22f0f',
    'full_prudent': '8632b101e0c42192e5e4b2264a37e0d50ee300cc26375b5ffe5f54db9afa91fc',
}


def cases():
    found = {
        'prudent_default': Settings('identity'),
        'no_chests': Settings('identity', randomize_chests=False),
        'skips': Settings('identity', skip_locked_cutscenes=True, skip_chest_cutscenes=True,
                          skulltulas_always_present=True),
        'legacy_skip_intro': Settings.from_dict({'seed': 'identity', 'skip_intro': True}),
    }
    for preset in ('ap_defaults', 'everything', 'prudent'):
        found['full_' + preset] = Settings('identity', randomize_chests=False, full=rando_options.preset(preset))
    return found


class SeedIdentityTest(unittest.TestCase):
    def test_identities_are_frozen(self):
        for name, settings in cases().items():
            with self.subTest(name):
                # Fixed generator/adapter versions: only the settings serialization is frozen here.
                self.assertEqual(settings_identity(settings, 'frozen', 'frozen'), EXPECTED[name])

    def test_round_trip_keeps_the_identity(self):
        for name, settings in cases().items():
            with self.subTest(name):
                again = Settings.from_dict(settings.to_dict())
                self.assertEqual(settings_identity(again), settings_identity(settings))

    def test_serialization_does_not_change_the_settings(self):
        for name, settings in cases().items():
            with self.subTest(name):
                before = settings.to_dict()
                settings.to_dict()
                settings.validate()
                self.assertEqual(settings.to_dict(), before)


if __name__ == '__main__':
    unittest.main()
