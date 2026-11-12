"""Audit of the AP rules against remake clues. NUP tests need OOT_NUP."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from oot_rando.logic import audit_rules as A

NUP = os.environ.get('OOT_NUP')
LW_CHEST = 'LW Near Shortcuts Grotto Chest'


def actor(name, ident, position, links=()):
    return {'Gyaml': name, 'Hash': ident, 'Translate': list(position),
            'Links': [{'Dst': d, 'Name': 'Reference'} for d in links]}


def entry(positions, folder='LostWood', ap=('X',), event=None):
    return {'folder': folder, 'ap': list(ap), 'event': event,
            'variants': [{'resource': r, 'position': list(p)} for r, p in positions]}


class AgeTests(unittest.TestCase):
    def test_resource_and_remake_ages(self):
        self.assertEqual(A.resource_age('Banc/LostWood/LostWood_Child_Dynamic.bcett.byml.zs'), 'child')
        self.assertEqual(A.resource_age('Banc/LostWood/LostWood_Adult_Static.bcett.byml.zs'), 'adult')
        self.assertIsNone(A.resource_age('Banc/FireTemple/FireTemple_Dynamic.bcett.byml.zs'))
        self.assertEqual(A.remake_ages([{'resource': 'a_Adult_b'}]), {'adult'})
        self.assertEqual(A.remake_ages([{'resource': 'a_Adult_b'}, {'resource': 'a_Child_b'}]), {'child', 'adult'})
        self.assertEqual(A.remake_ages([{'resource': 'Dungeon_Dynamic'}]), {'child', 'adult'})


class ClueTests(unittest.TestCase):
    def maps(self):
        adult = {'Actors': [actor('Obj_SmallFarm_A_03', 1, (-33, 100, 31), links=(2, 3)),
                            actor('DestinationAnchor', 2, (-46.6, 104.9, 72.8)),
                            actor('Enemy_Skulltula_Gold', 3, (-49, 104.5, 72)),
                            actor('Obj_WaterTemple_HookShotDecoration_A', 4, (-49, 104.5, 72))]}
        child = {'Actors': [actor('Obj_SmallFarm_A_01', 5, (-49, 104.5, 72)),
                            actor('Obj_HookShotTarget_A_01', 6, (-45, 104.5, 72))]}
        return {'Banc/LostWood/LostWood_Adult_Dynamic.bcett.byml.zs': {'root': adult},
                'Banc/LostWood/LostWood_Child_Dynamic.bcett.byml.zs': {'root': child}}

    def test_links_are_followed_except_enemies_and_child_bean_soils(self):
        points = A.hint_points(self.maps())['LostWood']
        beans = [p for p in points if p['token'] == 'bean']
        self.assertEqual([(p['via'], p['age']) for p in beans], [(None, 'adult'), ('DestinationAnchor', 'adult')])
        self.assertFalse(any(p['actor'].endswith('Decoration_A') for p in points))
        self.assertEqual([p['actor'] for p in points if p['token'] == 'hookshot'], ['Obj_HookShotTarget_A_01'])

    def test_clues_by_radius_and_age(self):
        points = A.hint_points(self.maps())
        adult = A.entry_clues(entry([('LostWood_Adult_Dynamic', (-49.4, 104.5, 71.9))]), points)
        self.assertEqual([(c['token'], c['via'], c['distance']) for c in adult], [('bean', 'DestinationAnchor', 3.0)])
        child = A.entry_clues(entry([('LostWood_Child_Dynamic', (-49.4, 104.5, 71.9))]), points)
        self.assertEqual([c['token'] for c in child], ['hookshot'])
        far = A.entry_clues(entry([('LostWood_Adult_Dynamic', (0, 0, 0))]), points)
        self.assertEqual(far, [])


def oracle(table, default=('child', 'adult')):
    """Fake ``ages_of``: table[(location, frozenset(tokens))] → ages, else ``default``."""
    def ages_of(location, token=None):
        tokens = frozenset((token,) if isinstance(token, str) else (token or ()))
        for (name, removed), ages in table.items():
            if name == location and removed <= tokens:
                return set(ages)
        return set(default)
    return ages_of


def clue(token, confidence='strong', distance=1.0):
    return {'token': token, 'confidence': confidence, 'distance': distance, 'actor': 'Obj_' + token, 'via': None}


class FindingTests(unittest.TestCase):
    def kinds(self, findings):
        return [(f['kind'], f.get('token')) for f in findings]

    def test_obstacle_flagged_only_when_ap_does_not_require_it(self):
        e = entry([('m_Adult_', (0, 0, 0))])
        loose = A.audit_entry(e, [clue('bean')], oracle({}, ('adult',)))
        self.assertEqual(self.kinds(loose), [('obstacle', 'bean')])
        required = A.audit_entry(e, [clue('bean')], oracle({('X', frozenset({'bean'})): ()}, ('adult',)))
        self.assertEqual(required, [])
        # Without beans AP only allows the child, the remake object is adult-only: fine.
        child_only = A.audit_entry(e, [clue('bean')], oracle({('X', frozenset({'bean'})): ('child',)}, ('adult',)))
        self.assertEqual(child_only, [])

    def test_alternatives_are_not_findings(self):
        e = entry([('m', (0, 0, 0))])
        table = {('X', frozenset({'blast_or_smash', 'strength'})): ()}
        self.assertEqual(A.audit_entry(e, [clue('blast_or_smash'), clue('strength')], oracle(table)), [])
        self.assertEqual(len(A.audit_entry(e, [clue('blast_or_smash'), clue('strength')], oracle({}))), 2)

    def test_group_needs_every_member_loose(self):
        e = entry([('m', (0, 0, 0))], ap=('X', 'Y'))
        table = {('Y', frozenset({'hookshot'})): ()}
        self.assertEqual(A.audit_entry(e, [clue('hookshot')], oracle(table)), [])

    def test_age_findings(self):
        adult_only = entry([('m_Adult_', (0, 0, 0))])
        mismatch = A.audit_entry(adult_only, [], oracle({('X', frozenset()): ('child',)}))
        self.assertEqual([(f['kind'], f['confidence']) for f in mismatch], [('age', 'strong')])
        early = A.audit_entry(adult_only, [], oracle({}))
        self.assertEqual([(f['kind'], f['confidence']) for f in early], [('age', 'medium')])
        # In a group, one member of another age only makes the conjunction stricter.
        group = entry([('m_Adult_', (0, 0, 0))], ap=('X', 'Y'))
        self.assertEqual(A.audit_entry(group, [], oracle({('X', frozenset()): ('child',)})), [])

    def test_helper_clues_only_explain_alternatives(self):
        e = entry([('m', (0, 0, 0))])
        helper = dict(clue('strength'), confidence='helper')
        table = {('X', frozenset({'blast_or_smash', 'strength'})): ()}
        self.assertEqual(A.audit_entry(e, [clue('blast_or_smash'), helper], oracle(table)), [])
        self.assertEqual(self.kinds(A.audit_entry(e, [clue('blast_or_smash'), helper], oracle({}))),
                         [('obstacle', 'blast_or_smash')])
        self.assertEqual(A.audit_entry(e, [helper], oracle({})), [])

    def test_guards_and_reviewed_findings(self):
        e = entry([('m', (0, 0, 0))], ap=('Colossus GS Hill',))
        self.assertEqual(self.kinds(A.audit_entry(e, [clue('bean')], oracle({}))), [('reviewed', 'bean')])
        guarded = dict(entry([('m', (0, 0, 0))]), guards=['Souls|Lens of Truth|Magic Meter'])
        self.assertEqual(A.audit_entry(guarded, [clue('lens')], oracle({})), [])

    def test_unreachable_and_event(self):
        e = entry([('m', (0, 0, 0))], event='Get_Something')
        self.assertEqual(self.kinds(A.audit_entry(e, [], oracle({}))), [('event', None)])
        never = A.audit_entry(e, [clue('bean')], oracle({('X', frozenset()): ()}))
        self.assertEqual(self.kinds(never), [('unreachable', None)])


class OracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        cls.data = World()
        cls.with_fixes = A.Oracle(cls.data, Logic(cls.data, {'open_forest': 'closed_deku'}))
        with A._without_remake_fixes(True):
            cls.without_fixes = A.Oracle(cls.data, Logic(cls.data, {'open_forest': 'closed_deku'}))

    def test_tokens_name_real_ap_items(self):
        for token, (_, items) in A.TOKENS.items():
            with self.subTest(token=token):
                self.assertTrue(any(i in self.data.item_table for i in items))

    def test_lost_woods_chest_needs_bean_only_with_remake_fix(self):
        self.assertTrue(self.without_fixes.ages(LW_CHEST, 'bean'))
        self.assertEqual(self.with_fixes.ages(LW_CHEST, 'bean'), set())
        self.assertEqual(self.with_fixes.ages(LW_CHEST), {'adult'})

    def test_here_bean_lets_the_child_plant_for_the_adult(self):
        for location in ('DMC Volcano Freestanding PoH', 'Colossus Freestanding PoH', 'LW GS Above Theater'):
            with self.subTest(location=location):
                self.assertEqual(self.with_fixes.ages(location), {'adult'})
                self.assertEqual(self.with_fixes.ages(location, 'bean'), set())

    def test_removed_items_also_blocked_as_events(self):
        state = self.with_fixes.state(('fire', 'blast_or_smash'))
        for item in ('Deku Stick Drop', 'Dins Fire', 'Bomb Bag', 'Megaton Hammer'):
            self.assertEqual(state.counts.get(item, 0), 0)
        self.assertTrue(self.with_fixes.state().counts.get('Deku Stick Drop'))

    def test_fixes_are_restored(self):
        from oot_rando.logic import world
        self.assertIn(LW_CHEST, world.REMAKE_LOCATION_RULES)


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class RealGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.logic.world import World
        from oot_rando.game.extra_sources import scan_world
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        maps, groups, _, extra = scan_world(nup, dictionaries(nup), effective_members(nup))
        data = World()
        cls.with_fixes = A.run_audit(data, maps, groups, extra)
        cls.without_fixes = A.run_audit(data, maps, groups, extra, without_fixes=True)

    @staticmethod
    def bean_rows(result):
        return [r for r in result['entries'] if LW_CHEST in r['ap']
                and any(f.get('token') == 'bean' for f in r['findings'])]

    def test_audit_finds_known_lost_woods_divergence_again(self):
        rows = self.bean_rows(self.without_fixes)
        self.assertEqual(len(rows), 1)
        self.assertIn('DestinationAnchor', rows[0]['findings'][0]['text'])
        self.assertEqual(self.bean_rows(self.with_fixes), [])

    def test_report_renders(self):
        text = A.to_markdown(self.with_fixes)
        self.assertIn('Check first', text)
        self.assertIn('Chests tied to an event', text)


if __name__ == '__main__':
    unittest.main()
