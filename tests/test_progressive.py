"""Progressive items: every copy gives the level above the one Link holds (issue #23).

Unit tests run everywhere; the flow tests need OOT_NUP (the game's own flows, played
by a small interpreter of the events the converter and the mailbox write).
"""
import _src_path  # noqa: F401  (src on sys.path)
import copy
import os
import unittest
from collections import Counter

from oot_rando.game.remake_world import PROGRESSIVE, STATIC_TIER_SOURCES, actor_item
from oot_rando.patching import progressive

NUP = os.environ.get('OOT_NUP')


class Units(unittest.TestCase):
    def test_token_names(self):
        from oot_rando.patching.soul_adapter import MAX_ACTOR_NAME
        self.assertEqual(set(progressive.FAMILIES), set(PROGRESSIVE))
        self.assertEqual(len(progressive.FAMILY_OF_CODE), len(PROGRESSIVE))
        for family in PROGRESSIVE:
            for number in (1, 2, 9):
                token = progressive.token_actor(family, number)
                self.assertLessEqual(len(token), MAX_ACTOR_NAME, token)   # longer names crash the get
                self.assertEqual(progressive.token_family(token), family)
                self.assertEqual(actor_item(token, 'KokiriForest'), family)
        for actor in ('Item_Hookshot', 'Item_Prog_Unknown_1', 'Item_Prog_Bow_x', 'Item_KeyRing_Well'):
            self.assertFalse(progressive.is_token(actor), actor)

    def test_tokens_numbered_per_family(self):
        tokens = progressive.assign_tokens([('a', 'Bow'), ('b', 'Bow'), ('c', 'Slingshot'), ('d', 'Bow')])
        self.assertEqual(tokens, {'a': 'Item_Prog_Bow_1', 'b': 'Item_Prog_Bow_2', 'c': 'Item_Prog_Slingshot_1',
                                  'd': 'Item_Prog_Bow_3'})
        with self.assertRaises(ValueError):
            progressive.assign_tokens([('a', 'Bow'), ('a', 'Bow')])

    def test_levels_tested_on_their_pouch_names(self):
        # Issue #23 follow-up: the pouch holds Weapon_Range_Bow, never Item_Range_Bow.
        self.assertEqual(progressive.held_query('Item_Range_Bow'),
                         ('PouchSystemActor', 'EventQueryIsExistInPouch', {'Actor': 'Weapon_Range_Bow', 'Num': 1}))
        self.assertEqual(progressive.held_query('Item_Hookshot')[2]['Actor'], 'Item_Hookshot')
        self.assertEqual(progressive.held_query('Item_FairyBless_MP'),
                         ('GameDataActor', 'EventQueryIsGameDataBool',
                          {'GameDataName': 'IsGet.Item_FairyBless_MP', 'Index': -1}))

    def test_tier_events_highest_first(self):
        self.assertEqual(progressive.tier_events('X', 3), [('X', 2, 2), ('X_Has1', 1, 2), ('X_Has0', 0, 1)])

    def test_native_fixed_levels(self):
        from oot_rando.randomizer.full_randomizer import native_sources, progressive_plan
        variant = {'resource': 'Banc/x.bcett.byml.zs', 'index': 4, 'before': 'Item_BombBag_Small'}
        chest = {'id': 'c', 'source': 'chest', 'form': 'chest', 'folder': 'DodongoCavern', 'vanilla': 'Bomb Bag',
                 'before': 'Item_BombBag_Small', 'variants': [variant], 'kind': 'exact'}
        goron = {'id': 'g', 'source': 'npc', 'form': 'event', 'folder': 'GoronCity', 'vanilla': 'Bomb Bag',
                 'before': 'Item_BombBag_Medium', 'kind': 'exact',
                 'variants': [{'resource': 'Event/EventFlow/Goron.bfevfl.zs', 'event': 'E1',
                               'param': 'ActorName', 'before': 'Item_BombBag_Medium'}]}
        location = next(iter(STATIC_TIER_SOURCES))
        family, tier = STATIC_TIER_SOURCES[location]
        darunia = {'id': 'npc#' + location, 'source': 'npc', 'form': 'event', 'folder': 'GoronCity',
                   'vanilla': family, 'before': PROGRESSIVE[family][tier], 'kind': 'exact',
                   'variants': [{'resource': 'Event/EventFlow/D.bfevfl.zs', 'event': 'E2', 'param': 'ActorName',
                                 'before': PROGRESSIVE[family][tier]}]}
        extra = {darunia['id']: darunia}
        matches = {'c': chest, 'g': goron}
        # An unshuffled chest keeps a fixed level: a token. The NPC upgrade already gives the next level.
        self.assertEqual(set(native_sources(matches, {}, extra)), {'c', darunia['id']})
        self.assertEqual(set(native_sources(matches, {'c': chest, darunia['id']: darunia}, extra)), set())
        junk = dict(darunia, kind='junk')
        self.assertEqual(set(native_sources({}, {}, {darunia['id']: junk})), set())   # no reliable event
        with self.assertRaises(ValueError):
            native_sources({}, {}, {darunia['id']: dict(darunia, before='Item_Gauntlet_Gold')})
        plan = progressive_plan({'s1': 'Bomb Bag', 's0': 'Bomb Bag', 'x': 'Hover Boots'},
                                native_sources(matches, {}, extra))
        self.assertEqual(plan['tokens'], {'s0': 'Item_Prog_BombBag_1', 's1': 'Item_Prog_BombBag_2'})
        by_id = {n['id']: n for n in plan['natives']}
        self.assertEqual(by_id['c']['after'], 'Item_Prog_BombBag_3')
        self.assertEqual(by_id['c']['patches'], [{'resource': variant['resource'], 'before': variant['before'],
                                                  'path': ['Actors', 4, 'Dynamic', 'Drop__DropActor']}])
        self.assertEqual(by_id[darunia['id']]['after'], progressive.token_actor(family, 1))
        self.assertEqual(by_id[darunia['id']]['patches'][0]['event'], 'E2')

    def test_starting_copies_take_the_lowest_levels(self):
        from oot_rando.randomizer.full_randomizer import FillError, starting_actors
        self.assertEqual(starting_actors(['Progressive Hookshot', 'Hover Boots', 'Progressive Hookshot']),
                         ['Item_Hookshot', 'Item_HoverBoot', 'Item_Longshot'])
        with self.assertRaises(FillError):
            starting_actors(['Progressive Hookshot'] * 3)


class FlowRun:
    """Plays a flow's events on a pouch and saved flags: the events the converter and the
    mailbox write, and their calls of the vanilla get flows (a window, then the add)."""

    GIVE = {('GetPouchContent', 'GetPouchContentByActorName'), ('', 'GetInEvent_NotTurn_NotNpc')}
    SHOW = {('GetPouchContent', 'DisplayGetByActorName')}

    def __init__(self, raw, names):
        from oot_rando.patching.event_patch import _flow
        self.entries = {e.name: e for e in _flow(raw).flowchart.entry_points}
        self.names = names            # the game's ActorInfo.ActorName of each actor
        self.pouch, self.flags, self.windows = Counter(), {}, []

    def add(self, actor, count=1):
        """The native pouch: count by pouch name, ``IsGet.<name>`` once got (IsGet struct)."""
        name = self.names.get(actor, actor)
        self.pouch[name] += count
        if count > 0:
            self.flags['IsGet.' + name] = True

    def level(self, family):
        """Highest level of ``family`` held (-1: none)."""
        held = [i for i, actor in enumerate(PROGRESSIVE[family])
                if self.pouch[self.names.get(actor, actor)] or self.flags.get('IsGet.' + actor)]
        return max(held, default=-1)

    def run(self, entry):
        event = self.entries[entry].main_event.v
        for _ in range(10000):
            if event is None:
                return
            data, kind = event.data, type(event.data).__name__
            params = dict(data.params.data) if data.params is not None else {}
            if kind == 'SwitchEvent':
                query = data.actor_query.v.v
                if query == 'EventQueryIsExistInPouch':
                    value = self.pouch[params['Actor']] >= params['Num']
                elif query == 'EventQueryIsGameDataBool':
                    value = bool(self.flags.get(params['GameDataName']))
                else:
                    raise AssertionError('Unexpected query: ' + query)
                case = data.cases.get(0 if value else 1)
                event = case.v if case is not None else None
                continue
            if kind == 'ActionEvent':
                action = data.actor_action.v.v
                if action == 'EventTriggerSetGameDataBool':
                    self.flags[params['GameDataName']] = params['Value']
                elif action == 'EventTriggerAddOrRemovePouchContent':
                    self.add(params['Actor'], params['Num'])
                else:
                    raise AssertionError('Unexpected action: ' + action)
            elif kind == 'SubFlowEvent':
                call = (data.res_flowchart_name, data.entry_point_name)
                if call in self.GIVE:
                    self.windows.append(params['ActorName'])
                    self.add(params['ActorName'])
                elif call in self.SHOW:
                    self.windows.append(params['ActorName'])
                elif call[0] == '':
                    self.run(call[1])
                else:
                    raise AssertionError(f'Unexpected call: {call}')
            else:
                raise AssertionError('Unexpected event: ' + kind)
            event = data.nxt.v if data.nxt is not None else None
        raise AssertionError('Endless flow')


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats import byml_codec
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        from oot_rando.patching.key_adapter import add_key_hook, key_records
        from oot_rando.patching.qol_patches import ocarina_guide_on_get
        from oot_rando.patching.soul_adapter import RSDB_FILES
        cls.nup = Nup(NUP)
        cls.d, cls.m = dictionaries(cls.nup), effective_members(cls.nup)
        cls.read = lambda self, p: decompress(cls.nup.read(cls.m[p]), cls.d)
        cls.names = {row['__RowId']: row.get('ActorName', row['__RowId'])
                     for row in byml_codec.load(cls.read(cls, RSDB_FILES['ActorInfo']))['root']}
        cls.tokens = sorted(progressive.token_actor(family, n + 1)
                            for family, levels in PROGRESSIVE.items() for n in range(len(levels)))
        # As generated: the ocarina guide and the key hook first, then the converter.
        guide = ocarina_guide_on_get(cls.read(cls, progressive.ACTION_GUIDE_FLOW))[0]
        cls.guide_before = add_key_hook(guide, key_records(['Small Key Ring (Forest Temple)']))[0]
        cls.guide, cls.report = progressive.add_converter(cls.guide_before, cls.tokens)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def current(self, name):
        from oot_rando.patching.event_info import flow_path
        path = flow_path(name)
        return self.read(path) if path in self.m else None

    def game(self):
        return FlowRun(self.guide, self.names)

    def find(self, game, token):
        """A chest or an NPC adds the token to the pouch; the item get then runs ActionGuide."""
        game.add(token)
        game.run(progressive.CONVERTER_ENTRY)

    def test_converter_runs_first_in_both_item_get_entries(self):
        from oot_rando.patching.event_info import entry_calls
        from oot_rando.patching.event_patch import _flow
        before = {e.name: e.main_event.v.name for e in _flow(self.guide_before).flowchart.entry_points}
        written = {e.name: e for e in _flow(self.guide).flowchart.entry_points}
        for name in progressive.GUIDE_ENTRIES:
            run = written[name].main_event.v
            self.assertEqual((run.data.res_flowchart_name, run.data.entry_point_name),
                             ('', progressive.CONVERTER_ENTRY))
            self.assertEqual(run.data.nxt.v.name, before[name])            # then the key hook, the guide…
            self.assertIn(progressive.GIVE_CALL, entry_calls(self.guide, name))
        progressive.check_converter(written[progressive.CONVERTER_ENTRY], self.tokens)
        with self.assertRaises(ValueError):
            progressive.check_converter(written[progressive.CONVERTER_ENTRY], self.tokens[1:])
        with self.assertRaises(ValueError):
            progressive.add_converter(self.guide, self.tokens)                   # only once

    def test_any_order_gives_the_levels_in_order(self):
        # Issue #23: the large bullet bag's copy found before the slingshot's.
        game = self.game()
        for token, level in (('Item_Prog_Slingshot_3', 0), ('Item_Prog_Slingshot_1', 1),
                             ('Item_Prog_Slingshot_2', 2)):
            self.find(game, token)
            self.assertEqual(game.level('Slingshot'), level, token)
        self.assertEqual(game.windows, PROGRESSIVE['Slingshot'])
        self.assertEqual(game.pouch['Weapon_Range_SlingShot'], 1)
        for family in ('Progressive Strength Upgrade', 'Magic Meter', 'Ocarina', 'Bow'):
            levels = PROGRESSIVE[family]
            for number in reversed(range(1, len(levels) + 1)):
                self.find(game, progressive.token_actor(family, number))
            self.assertEqual(game.level(family), len(levels) - 1, family)
            self.assertEqual(game.windows[-len(levels):], levels, family)

    def test_each_token_converts_once(self):
        game = self.game()
        game.add('Item_Prog_Hookshot_2')
        game.add('Item_Prog_Hookshot_1')            # two tokens before one item get
        game.run(progressive.CONVERTER_ENTRY)
        self.assertEqual(game.windows, ['Item_Hookshot', 'Item_Longshot'])
        self.assertEqual((game.pouch['Item_Prog_Hookshot_1'], game.pouch['Item_Prog_Hookshot_2']), (0, 0))
        game.add('Item_Prog_Hookshot_1')            # its take failed: the saved flag still stops it
        game.run(progressive.CONVERTER_ENTRY)
        game.run(progressive.CONVERTER_ENTRY)
        self.assertEqual(game.windows, ['Item_Hookshot', 'Item_Longshot'])
        game.add('Item_Prog_Bow_1', 0)              # never got: nothing
        game.run(progressive.CONVERTER_ENTRY)
        self.assertEqual(game.level('Bow'), -1)

    def test_never_lower_than_held(self):
        # A level held another way (a native NPC upgrade): the token gives the one above it,
        # and the last level again once every level is held (never a loss of capacity).
        game = self.game()
        game.add('Item_BombBag_Medium')
        self.find(game, 'Item_Prog_BombBag_1')
        self.assertEqual(game.windows, ['Item_BombBag_Large'])
        self.find(game, 'Item_Prog_BombBag_2')
        self.assertEqual(game.windows, ['Item_BombBag_Large'] * 2)
        self.assertEqual(game.level('Bomb Bag'), 2)

    def test_mailbox_uses_the_same_levels(self):
        # Copies received from other worlds and tokens found here share one count.
        from oot_rando.patching import ap_mailbox
        items = ap_mailbox.records([{'item': 'Bow', 'location': f'L{i}', 'player': 'Ami'} for i in range(2)]
                                   + [{'item': 'Magic Meter', 'location': 'M', 'player': 'Ami'},
                                      {'item': 'Ocarina', 'location': 'O', 'player': 'Ami'}])
        mailbox = FlowRun(ap_mailbox.add_entries(self.read(ap_mailbox.FLOW_PATH), items), self.names)
        game = self.game()
        mailbox.pouch, mailbox.flags = game.pouch, game.flags
        mailbox.run(items[0]['event'])                        # received: the bow
        self.find(game, 'Item_Prog_Bow_2')                    # found here: the next level
        mailbox.run(items[1]['event'])                        # received: the last level
        self.assertEqual(mailbox.windows, ['Item_Range_Bow', 'Item_Quiver_Large'])
        self.assertEqual(game.windows, ['Item_Quiver_Medium'])
        self.assertEqual(game.level('Bow'), 2)
        self.assertTrue(game.flags[items[1]['got']])
        self.find(game, 'Item_Prog_Magic_1')
        mailbox.run(items[2]['event'])                        # held through IsGet.Item_FairyBless_MP
        self.assertEqual(mailbox.windows[-1], 'Item_FairyBless_MPDouble')
        mailbox.run(items[3]['event'])
        self.assertEqual(mailbox.windows[-1], 'Item_Ocarina_Fairy')   # added, then shown: no pose

    def test_pouch_names_match_the_game(self):
        from oot_rando.formats import byml_codec
        from oot_rando.patching.soul_adapter import GAMEDATA, RSDB_FILES
        actor_info, gamedata = self.read(RSDB_FILES['ActorInfo']), self.read(GAMEDATA)
        progressive.check_pouch_names(actor_info, gamedata)
        document = byml_codec.load(actor_info)
        row = next(r for r in document['root'] if r['__RowId'] == 'Item_Range_Bow')
        row['ActorName'] = 'Item_Range_Bow'
        with self.assertRaises(ValueError):
            progressive.check_pouch_names(byml_codec.dump(document), gamedata)

    def test_token_files(self):
        from oot_rando.formats import byml_codec
        from oot_rando.formats.inspect_resources import sarc
        from oot_rando.patching.soul_adapter import GAMEDATA, RSDB_FILES, murmur3
        messages = sorted(m for m in self.m if m.startswith('Mals/') and '.Product.110.' in m)[:1]
        modified, new = progressive.build_token_files(lambda p: self.read(p), self.tokens, messages)
        flags = {int(e['Hash']) for e in byml_codec.load(modified[GAMEDATA])['root']['Data']['Bool']
                 if e.get('SaveFileIndex') == 0}
        rows = {r['__RowId'] for r in byml_codec.load(modified[RSDB_FILES['ActorInfo']])['root']}
        for token in self.tokens:
            self.assertIn(f'Actor/{token}.engine__actor__ActorParam.bgyml',
                          sarc(new[f'Pack/Actor/{token}.pack.zs'][0]))
            self.assertIn(token, rows)
            self.assertIn(murmur3(progressive.applied_flag(token)), flags)
            self.assertIn(murmur3(progressive.got_flag(token)), flags)
        self.assertEqual(progressive.build_token_files(lambda p: self.read(p), []), ({}, {}))

    def test_gifts_outside_item_gets_call_the_converter(self):
        from oot_rando.game.extra_sources import scan_npc_sources
        from oot_rando.patching.event_info import flow_name
        from oot_rando.patching.event_patch import _flow
        entries = scan_npc_sources(self.m, lambda path: _flow(self.read(path)))
        sites = {gid: [(v['resource'], v['event']) for v in e['variants'] if 'event' in v]
                 for gid, e in entries.items()}
        darunia = 'npc#' + next(iter(STATIC_TIER_SOURCES))
        hooks = progressive.hook_sites([sites[darunia]], self.current)
        self.assertEqual(hooks, {sites[darunia][0][0]: [sites[darunia][0][1]]})   # a cutscene gift
        saria = progressive.hook_sites([sites['quest#LW Gift from Saria']], self.current)
        self.assertEqual(sum(len(v) for v in saria.values()), 1)                  # after the add only
        reaching = [g for g, s in sites.items() if g.startswith('npc#') and s and g != darunia]
        self.assertTrue(reaching)
        self.assertEqual(progressive.hook_sites([sites[g] for g in reaching], self.current), {})
        resource, events = next(iter(hooks.items()))
        self.assertEqual(progressive.hook_sites([sites[darunia]], self.current, covered={resource: {}}), {})
        raw = progressive.add_converter_calls(self.read(resource), events, flow_name(resource))
        chart = _flow(raw).flowchart
        named = {e.name: e for e in chart.events}
        call = named[events[0]].data.nxt.v
        self.assertEqual((call.name, call.data.res_flowchart_name, call.data.entry_point_name),
                         (progressive.AFTER_PREFIX + events[0], 'ActionGuide', progressive.CONVERTER_ENTRY))
        index = chart.events.index(call)
        self.assertTrue(any(index in e._sub_flow_event_indices for e in chart.entry_points))

    def test_new_calls_listed_for_the_events(self):
        # The cutscene now loads ActionGuide, which now loads GetPouchContent.
        from oot_rando.formats.inspect_resources import Byml
        from oot_rando.patching.event_info import (GAME_ANALYZED_EVENT_INFO, add_subflow_dependencies, flow_name,
                                                   new_subflows)
        from oot_rando.patching.qol_patches import EVENT_SETTINGS
        resource, event = 'Event/EventFlow/Dm_Kokiri_0155.bfevfl.zs', 'Event68'   # Saria's add
        changed = {'ActionGuide': self.guide,
                   flow_name(resource): progressive.add_converter_calls(self.read(resource), [event],
                                                                        flow_name(resource))}
        current = lambda name: changed.get(name) or self.current(name)
        added = new_subflows(changed, self.current)
        self.assertEqual(added[(flow_name(resource), 'EntryPoint0')], {('ActionGuide', 'RandoProgressive')})
        _, rows = add_subflow_dependencies(self.read(GAME_ANALYZED_EVENT_INFO), Byml(self.read(EVENT_SETTINGS)).root,
                                           added, current)
        self.assertEqual(rows[flow_name(resource)], ['ActionGuide'])
        self.assertIn(['GetPouchContent'], rows.values())     # the rows already listing ActionGuide


if __name__ == '__main__':
    unittest.main()
