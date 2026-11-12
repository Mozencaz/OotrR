"""Every generated item actor name fits the length the game handles (soul_adapter.MAX_ACTOR_NAME)."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.patching import soul_adapter
from oot_rando.patching.key_adapter import (BOSS_KEY_DUNGEONS, MAP_DUNGEONS, RING_DUNGEONS, boss_actor,
                                           compass_actor, map_actor, ring_actor)


class ActorNamesTest(unittest.TestCase):
    def test_souls(self):
        names = [soul_adapter.soul_actor(soul_adapter.soul_item('Region:' + f)) for f in soul_adapter.REGION_LABELS]
        names += [soul_adapter.soul_actor(soul_adapter.soul_item(k)) for k in soul_adapter.BY_ID]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual([n for n in names if len(n) > soul_adapter.MAX_ACTOR_NAME], [])

    def test_keys(self):
        names = [ring_actor(f) for f in RING_DUNGEONS] + [boss_actor(f) for f in BOSS_KEY_DUNGEONS]
        names += [map_actor(f) for f in MAP_DUNGEONS] + [compass_actor(f) for f in MAP_DUNGEONS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual([n for n in names if len(n) > soul_adapter.MAX_ACTOR_NAME], [])


if __name__ == '__main__':
    unittest.main()
