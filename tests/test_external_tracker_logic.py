"""External trackers must not inherit AP's default always-true location rule."""
import _src_path  # noqa: F401
import ast
from collections import Counter
from types import SimpleNamespace
import unittest

from oot_rando.paths import resource
from oot_rando.archipelago.bridge import PlayerWorld
from oot_rando.logic import rando_options
from oot_rando.logic.world import World
from oot_rando.randomizer.full_randomizer import prepare, vname


def create_regions(world):
    # Execute the actual template method without importing an installed Archipelago.
    source = ast.parse(resource('archipelago/ap_world.py.in').read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'OoTRemakeWorld')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'create_regions')

    class Region:
        def __init__(self, *args):
            self.locations = []

    class Location:
        access_rule = staticmethod(lambda state: True)

        def __init__(self, player, name, address, parent):
            self.name = name

    namespace = {'Region': Region, 'RemakeLocation': Location,
                 'LocationProgressType': SimpleNamespace(EXCLUDED='excluded')}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<apworld create_regions>', 'exec'), namespace)
    namespace['create_regions'](world)


class ExternalTrackerRules(unittest.TestCase):
    def test_excluded_checks_use_reachability_and_remain_excluded(self):
        remake = SimpleNamespace(
            names={'mapped': 'Mapped', 'shadow': 'Shadow', 'spirit': 'Spirit'},
            in_logic={'mapped': True, 'shadow': False, 'spirit': False},
            reachable=lambda gid, counts: bool(counts.get(gid)),
            can_hold=lambda gid, item: True)
        world = SimpleNamespace(remake=remake, player=1,
                                location_name_to_id={'Mapped': 1, 'Shadow': 2, 'Spirit': 3},
                                multiworld=SimpleNamespace(regions=[]))
        create_regions(world)
        checks = {loc.name: loc for loc in world.multiworld.regions[0].locations}
        empty = SimpleNamespace(prog_items={1: {}})
        for name in checks:
            with self.subTest(name=name):
                self.assertFalse(checks[name].access_rule(empty))
        for gid, name in remake.names.items():
            with self.subTest(gid=gid):
                state = SimpleNamespace(prog_items={1: {gid: 1}})
                self.assertTrue(checks[name].access_rule(state))
                for other in checks.keys() - {name}:
                    self.assertFalse(checks[other].access_rule(state))
        self.assertEqual(checks['Shadow'].progress_type, 'excluded')
        self.assertEqual(checks['Spirit'].progress_type, 'excluded')


class AreaEstimates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        groups = {}
        for folder, age in [('ShadowTemple', 'Dynamic'), ('SpiritTemple', 'Dynamic'),
                            ('DreamWorld', 'Dynamic'), ('KokiriForest', 'Adult')]:
            gid = folder + '#1'
            groups[gid] = [dict(resource=f'Banc/{folder}/{folder}_{age}_Static.bcett.byml.zs',
                                index=0, actor='Obj_TBox_A_01', folder=folder, hash='1',
                                before='TBox_Rupee_Green', dynamic={}, position=[0, 0, 0])]
        cls.c = prepare(World(), rando_options.defaults(), groups, [], 'external-tracker', True)

    def player(self):
        # Isolate reachability from pool construction: the inventory can contain
        # any referenced item. The compiled rules and sweep are the real ones.
        world = PlayerWorld.__new__(PlayerWorld)
        world.c = self.c
        world.vnames = {gid: vname(gid) for gid in self.c.shuffled}
        world.in_logic = {gid: vname(gid) in self.c.logic.virtual for gid in self.c.shuffled}
        world.progression = set(self.c.relevant)
        world.pool = list(self.c.relevant) * 99
        world.tracker_members = world._tracker_members()
        world._cache = {}
        return world

    def test_dungeon_estimates_require_the_whole_area(self):
        world = self.player()
        full = Counter({i: 99 for i in self.c.relevant})
        before = dict(self.c.logic.virtual)
        for gid in ('ShadowTemple#1', 'SpiritTemple#1'):
            with self.subTest(gid=gid):
                self.assertFalse(world.in_logic[gid])
                self.assertIn(gid, world.tracker_members)
                self.assertFalse(world.reachable(gid, Counter()))
                self.assertTrue(world.reachable(gid, full))
                # Cache rollback cannot keep a previously reachable chest open.
                self.assertFalse(world.reachable(gid, Counter()))
        self.assertEqual(self.c.logic.virtual, before)

    def test_partial_area_is_not_enough(self):
        world = self.player()
        counts = Counter({i: 99 for i in self.c.relevant if i != 'Mirror Shield'})
        state, _, _ = self.c.sweep({}, counts)
        members = world.tracker_members['SpiritTemple#1']
        accessible = [self.c.logic.accessible(state, m) for m in members]
        self.assertTrue(any(accessible))
        self.assertFalse(all(accessible))
        self.assertFalse(world.reachable('SpiritTemple#1', counts))

    def test_unmapped_area_never_defaults_to_reachable(self):
        world = self.player()
        self.assertNotIn('DreamWorld#1', world.tracker_members)
        self.assertFalse(world.reachable('DreamWorld#1', Counter()))
        self.assertFalse(world.reachable('DreamWorld#1', Counter({i: 99 for i in self.c.relevant})))

    def test_area_guards_and_source_age_are_preserved(self):
        # Force the adult-only source through the fallback (as for an unmapped chest).
        world = self.player()
        world.in_logic['KokiriForest#1'] = False
        entry = self.c.shuffled['KokiriForest#1']
        original = entry.get('guards', [])
        try:
            entry['guards'] = ['Souls|Lens of Truth|Magic Meter']
            members = world._tracker_members()['KokiriForest#1']
        finally:
            entry['guards'] = original
        self.assertTrue(any(m.startswith('Adult|') for m in members))
        self.assertIn('Souls|Lens of Truth|Magic Meter', members)
        state, _, _ = self.c.sweep({})
        self.assertFalse(all(self.c.logic.accessible(state, m) for m in members))
        full = Counter({i: 99 for i in self.c.relevant})
        state, _, _ = self.c.sweep({}, full)
        self.assertTrue(all(self.c.logic.accessible(state, m) for m in members))
        state, _, _ = self.c.sweep({}, full, before_adult=True)
        self.assertFalse(all(self.c.logic.accessible(state, m) for m in members))
        full.pop('Lens of Truth')
        state, _, _ = self.c.sweep({}, full)
        self.assertFalse(all(self.c.logic.accessible(state, m) for m in members))

    def test_dream_interval_uses_a_late_estimate_not_lobby_access(self):
        world = self.player()
        entry = self.c.shuffled['DreamWorld#1']
        original = entry['variants']
        try:
            entry['variants'] = [dict(original[0],
                                      resource='Banc/DreamWorld/BossRushIntervalRoom_Static.bcett.byml.zs')]
            world.tracker_members = world._tracker_members()
        finally:
            entry['variants'] = original
        members = world.tracker_members['DreamWorld#1']
        self.assertIn('Spirit Temple Mirror Shield Chest', members)
        self.assertFalse(world.reachable('DreamWorld#1', Counter()))
        self.assertTrue(world.reachable('DreamWorld#1', Counter({i: 99 for i in self.c.relevant})))


if __name__ == '__main__':
    unittest.main()
