"""Sources found only on the child maps or only on the adult maps need that age in logic."""
import _src_path  # noqa: F401  (src on sys.path)
from collections import Counter
import unittest

from oot_rando.game.extra_sources import scan_map_sources
from oot_rando.game.remake_world import source_age
from oot_rando.logic import rando_options
from oot_rando.logic.world import World
from oot_rando.randomizer.full_randomizer import prepare, tracker_checks, vname

KF = 'Banc/KokiriForest/KokiriForest_{}_Static.bcett.byml.zs'
HF = 'Banc/HyruleField/HyruleField_{}_Static.bcett.byml.zs'
VILLAGE = [6.0, 110.0, 21.0]          # Kokiri Forest, next to Link's house
KF_CHILD, KF_ADULT, KF_BOTH = 'KokiriForest#rocks#1', 'KokiriForest#rocks#2', 'KokiriForest#rocks#3'
HF_CHILD, HF_ADULT = 'HyruleField#rocks#4', 'HyruleField#rocks#5'
# The Door of Time opens with the Song of Time, which (with the Ocarina of Time) the child
# gets in Hyrule Field for the stones Zelda's escape asks for: vanilla songs and ocarinas.
# "Require all" (the default) asks for the three; "Vanilla" for the Goron Ruby and the Zora
# Sapphire (the remake's own check never looks at the Kokiri Emerald).
STONES = {'all': {'Kokiri Emerald': 1, 'Goron Ruby': 1, 'Zora Sapphire': 1},
          'vanilla': {'Goron Ruby': 1, 'Zora Sapphire': 1}}
# Remake: the Door of Time also waits for Zelda (DoorOfTime starts after her).
DOOR_EVENTS = {'Met Zelda': 1}


def rock(ident, position=VILLAGE):
    return {'Gyaml': 'Obj_LiftRock_A_01', 'Hash': ident, 'Translate': list(position)}


def map_sources():
    """A village rock per age map, one on both maps, and a Hyrule Field rock per age map."""
    maps = {KF.format('Child'): {'root': {'Actors': [rock(1), rock(3)]}},
            KF.format('Adult'): {'root': {'Actors': [rock(2), rock(3)]}},
            HF.format('Child'): {'root': {'Actors': [rock(4, (0.0, 0.0, 0.0))]}},
            HF.format('Adult'): {'root': {'Actors': [rock(5, (0.0, 0.0, 0.0))]}}}
    return scan_map_sources(maps, lambda actor, field: True, lambda actor: False)


class MapAgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = World()
        cls.c = cls.prepared()
        cls.vanilla = cls.prepared(spiritual_stones='vanilla')

    @classmethod
    def prepared(cls, **options):
        options = dict(rando_options.defaults(), shuffle_rocks=True, **options)
        return prepare(cls.data, options, {}, [], 'map-ages', True, extra=map_sources())

    def collected(self, counts, time_travel=True, c=None):
        """Remake sources collected with ``counts``; without ``time_travel`` Link never becomes adult."""
        c = c or self.c
        placements = dict(c.base)
        if not time_travel:
            placements['Master Sword Pedestal'] = None
        for gid in c.logic_locations:
            placements.setdefault(vname(gid), None)
        _, found, _ = c.logic.sweep(placements, c.logic.new_state(Counter(counts) + c.starting))
        return {name[len('Remake|'):] for name in found if name.startswith('Remake|')}

    def everything(self):
        return {item: 9 for item in self.c.relevant if item != 'Time Travel'}

    def test_members_carry_the_age_of_the_maps(self):
        virtual = self.c.logic.virtual
        self.assertEqual(virtual[vname(KF_CHILD)], ['Child|KF Links House Pot'])
        self.assertEqual(virtual[vname(KF_ADULT)], ['Adult|KF Links House Pot'])
        self.assertEqual(virtual[vname(KF_BOTH)], ['KF Links House Pot'])
        self.assertTrue(any(m.startswith('Adult|') for m in virtual[vname(HF_ADULT)]))
        self.assertFalse(any(m.startswith('Child|') for m in virtual[vname(HF_ADULT)]))

    def test_child_map_source_is_reachable_at_the_start(self):
        found = self.collected({})
        self.assertIn(KF_CHILD, found)
        self.assertIn(KF_BOTH, found)
        self.assertNotIn(KF_ADULT, found)

    def test_adult_map_sources_need_adult_access(self):
        found = self.collected(self.everything(), time_travel=False)
        self.assertIn(KF_CHILD, found)
        self.assertNotIn(KF_ADULT, found)
        self.assertNotIn(HF_ADULT, found)
        self.assertTrue({KF_CHILD, KF_ADULT, KF_BOTH, HF_CHILD, HF_ADULT} <= self.collected(self.everything()))

    def test_adult_access_is_the_door_of_time(self):
        for value, c in (('all', self.c), ('vanilla', self.vanilla)):
            door = dict(STONES[value], **DOOR_EVENTS)
            with self.subTest(spiritual_stones=value):
                self.assertIn(KF_ADULT, self.collected(door, c=c))
                # (Zelda can be met with what the sweep finds: not a missing item here.)
                for missing in [m for m in door if m != 'Met Zelda']:
                    with self.subTest(missing=missing):
                        counts = {item: n for item, n in door.items() if item != missing}
                        self.assertNotIn(KF_ADULT, self.collected(counts, c=c))
                        self.assertIn(KF_CHILD, self.collected(counts, c=c))

    def test_the_emerald_only_opens_the_door_when_required(self):
        counts = dict(STONES['vanilla'], **DOOR_EVENTS)
        self.assertIn(KF_ADULT, self.collected(counts, c=self.vanilla))
        self.assertNotIn(KF_ADULT, self.collected(counts, c=self.c))

    def test_tracker_names_show_the_age(self):
        names = {c['id']: c['name'] for c in tracker_checks(self.data, self.c.matches, self.c.shuffled)}
        self.assertEqual(names[KF_CHILD], 'Kokiri Forest rock 1 (child)')
        self.assertEqual(names[KF_ADULT], 'Kokiri Forest rock 2 (adult)')
        self.assertEqual(names[KF_BOTH], 'Kokiri Forest rock 3')
        self.assertEqual(names[HF_ADULT], 'Hyrule Field rock 5 (adult)')

    def test_event_flows_have_no_age(self):
        # NPC gifts: an event flow named after a child NPC is not a child map.
        self.assertIsNone(source_age([{'resource': 'Event/EventFlow/Npc_SkullKid_Child_02.bfevfl.zs'}]))
        self.assertEqual(source_age([{'resource': KF.format('Child')}]), 'child')


if __name__ == '__main__':
    unittest.main()
