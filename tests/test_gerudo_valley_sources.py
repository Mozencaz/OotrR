"""Child-only fortress bank actors must never become shuffle locations."""
import _src_path  # noqa: F401
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from oot_rando.game.extra_sources import scan_map_sources
from oot_rando.game.remake_world import scan_maps


class GerudoValleySources(unittest.TestCase):
    def test_child_fortress_bank_is_filtered_without_changing_maps_or_indices(self):
        actors = [
            {'Gyaml': 'Obj_TBox_A_01', 'Hash': 1, 'Translate': [-47, 84, -46],
             'Dynamic': {'Drop__DropActor': 'TBox_Rupee_Green'}},
            {'Gyaml': 'Obj_Pot_A_05', 'Hash': 2, 'Translate': [-46, 84, -46],
             'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Green'}},
            {'Gyaml': 'Obj_LiftRock_A_01', 'Hash': 3, 'Translate': [-28, 101, -28]},
            {'Gyaml': 'Enemy_Skulltula_Gold', 'Hash': 4, 'Translate': [-30, 101, 0]},
            # The lower river ledge and the near bank remain accessible to child Link.
            {'Gyaml': 'Obj_Pot_A_05', 'Hash': 5, 'Translate': [-18, 48, -59],
             'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Green'}},
            {'Gyaml': 'Obj_Pot_A_05', 'Hash': 6, 'Translate': [50, 95, 6],
             'Dynamic': {'Drop__DropActor': 'Obj_Rupee_Green'}},
        ]
        maps = {f'Banc/{folder}/{folder}_{age}_Dynamic.bcett.byml.zs':
                {'root': {'Actors': actors}}
                for folder, age in [('GerudoValley', 'Child'), ('GerudoValley', 'Adult'),
                                    ('KokiriForest', 'Child')]}
        sources = scan_map_sources(maps, lambda *_: True)
        for source in ('GerudoValley#pots#2', 'GerudoValley#rocks#3', 'GerudoValley#gs#4'):
            self.assertEqual(len(sources[source]['variants']), 1)
            self.assertIn('_Adult_', sources[source]['variants'][0]['resource'])
        for ident in (5, 6):
            self.assertEqual(len(sources[f'GerudoValley#pots#{ident}']['variants']), 2)
        self.assertIn('KokiriForest#pots#2', sources)
        with patch('oot_rando.formats.inspect_resources.decompress', side_effect=lambda raw, _: raw), \
                patch('oot_rando.formats.inspect_resources.Byml',
                      side_effect=lambda path: SimpleNamespace(root=maps[path]['root'])):
            decoded, groups, enemies = scan_maps(SimpleNamespace(read=lambda path: path), {},
                                                 {p: p for p in maps})
        self.assertEqual(len(groups['GerudoValley#1']), 1)
        self.assertIn('_Adult_', groups['GerudoValley#1'][0]['resource'])
        self.assertFalse(any(e['folder'] == 'GerudoValley' and '_Child_' in e['resource']
                             for e in enemies))
        child = 'Banc/GerudoValley/GerudoValley_Child_Dynamic.bcett.byml.zs'
        self.assertEqual(decoded[child]['root']['Actors'], actors)
        self.assertEqual(sources['GerudoValley#pots#6']['variants'][0]['index'], 5)

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_native_child_grotto_and_plateau_are_excluded(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(os.environ['OOT_NUP'])
        try:
            members = {p: v for p, v in effective_members(nup).items()
                       if p.startswith(('Banc/GerudoValley/', 'Logic/'))}
            maps, groups, _ = scan_maps(nup, dictionaries(nup), members)
            sources = scan_map_sources(maps, lambda *_: True)
        finally:
            nup.stream.close()
        for ident in ('9231973890535833762', '13179280208744162657',
                      '946934829814115422', '14928885472468269852'):
            self.assertNotIn('GerudoValley#pots#' + ident, sources)
        for ident in ('17750686910716887133', '6205043616869463865'):
            self.assertFalse(any('_Child_' in v['resource']
                                 for v in groups.get('GerudoValley#' + ident, [])))
        # The child chest on the lower ledge is still part of the shuffle.
        self.assertTrue(any('_Child_' in v['resource']
                            for v in groups['GerudoValley#15856256242099990922']))
        self.assertIn('GerudoValley#gs#8326970197618554626', sources)

    @unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP absent')
    def test_prudent_environment_shuffle_also_excludes_child_fortress_bank(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, Byml
        from oot_rando.game.world_maps import build_world
        from oot_rando.game.remake_world import inaccessible_child_actor
        nup = Nup(os.environ['OOT_NUP'])
        try:
            result = build_world(nup, dictionaries(nup), {'pots': True, 'world_chests': True},
                                 'gerudo-child-bank-regression')
        finally:
            nup.stream.close()
        self.assertTrue(result['placements'])
        for path, raw in result['raw_maps'].items():
            if not path.startswith('Banc/GerudoValley/'):
                continue
            actors = {str(a['Hash']): a for a in Byml(raw).root['Actors'] if 'Hash' in a}
            for placement in result['placements']:
                if path in placement['resources']:
                    self.assertFalse(inaccessible_child_actor(path, actors[placement['hash']]))
        self.assertTrue(any('GerudoValley_Adult_' in path
                            for p in result['placements'] for path in p['resources']))
