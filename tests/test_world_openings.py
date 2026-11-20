"""World openings (patching/world_openings.py). Needs OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import game_defaults, quest_guard, world_openings as w

NUP = os.environ.get('OOT_NUP')


def unflagged_links(nodes):
    """Links reading an output its node does not compute (not flagged ``Is Output``).

    Every link of the vanilla logic modules reads a flagged output (5376 of 5376 links
    in 600 modules, 20/11): the others are never computed and stay false."""
    by_index, found = {n['Node Index']: n for n in nodes}, []
    for node in nodes:
        for kind, inputs in node.get('Parameters', {}).get('Inputs', {}).items():
            for entry in inputs:
                sources = entry.get('Sources') or ([entry] if entry.get('Node Index', -1) >= 0 else [])
                for source in sources:
                    outputs = by_index.get(source['Node Index'], {}).get('Parameters', {}).get('Outputs', {}).get(kind, [])
                    if source['Output Index'] < len(outputs) and not outputs[source['Output Index']].get('Is Output'):
                        found.append((node['Node Index'], entry['Name'], source['Node Index'], source['Output Index']))
    return found


class Option(unittest.TestCase):
    def test_openings_are_offered(self):
        from oot_rando.logic import rando_options
        for option, value in (('zora_fountain', 'open'), ('open_kakariko', 'open'), ('open_door_of_time', True),
                              ('gerudo_fortress', 'fast'), ('open_gerudo_valley_bridge', True)):
            with self.subTest(option=option):
                self.assertEqual(rando_options.validate({option: value}, supported_only=True)[option], value)
                self.assertIn(value, next(o for o in rando_options.OPTIONS if o.name == option).experimental)
        with self.assertRaises(ValueError):    # the card check would be lost
            rando_options.validate({'gerudo_fortress': 'open'}, supported_only=True)

    def test_open_door_lets_the_sword_be_pulled_at_once(self):
        from collections import Counter
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        data = World()
        for door, expected in ((False, False), (True, True)):
            logic = Logic(data, {'open_forest': 'closed_deku', 'open_door_of_time': door})
            _, collected, _ = logic.sweep({'Master Sword Pedestal': None}, logic.new_state(Counter()))
            self.assertEqual('Master Sword Pedestal' in collected, expected)

    def test_repaired_bridge_logic(self):
        from collections import Counter
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        data = World()
        for bridge, expected in ((False, False), (True, True)):
            logic = Logic(data, {'open_forest': 'closed_deku', 'open_door_of_time': True,
                                 'open_gerudo_valley_bridge': bridge})
            _, collected, _ = logic.sweep({'Master Sword Pedestal': 'Time Travel', 'GV Chest': None,
                                           'Hideout Gerudo Membership Card': None},
                                          logic.new_state(Counter({'Progressive Hookshot': 1, 'Megaton Hammer': 1})))
            with self.subTest(bridge=bridge):
                self.assertEqual('GV Chest' in collected, expected)
                self.assertNotIn('Hideout Gerudo Membership Card', collected)   # still the carpenters

    def test_open_fountain_logic(self):
        from collections import Counter
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World
        data = World()
        logic = Logic(data, {'open_forest': 'closed_deku', 'zora_fountain': 'open'})
        _, collected, _ = logic.sweep({'Deliver Rutos Letter': None, 'ZF Great Fairy Reward': None},
                                      logic.new_state(Counter({'Rutos Letter': 1, 'Ocarina': 1,
                                                               'Zeldas Lullaby': 1, 'Bomb Bag': 1,
                                                               'Progressive Scale': 1})))
        self.assertNotIn('Deliver Rutos Letter', collected)   # the letter is never a bottle


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class ZoraFountain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        nup = cls.nup = Nup(NUP)
        d = dictionaries(nup)
        cls.read = staticmethod(lambda path: decompress(nup.read(nup.latest('romfs/' + path)), d))

    def opened(self):
        return w.zora_fountain_open(self.read, self.read(game_defaults.GAMEDATA),
                                    self.read(quest_guard.CHALLENGES))

    def test_quest_starts_after_the_letter(self):
        gamedata, flows, report = self.opened()
        self.assertEqual(game_defaults.read_defaults(gamedata, [w.ZORA_STEP]), {w.ZORA_STEP: w.ZORA_FLOOR})
        self.assertEqual(report['expression'], 'Get_StoneOfWater_IsAfter_Step06_Exp')
        self.assertEqual(set(flows), set(w.ZORA_FLOWS))
        guarded = {step for path in w.ZORA_FLOWS for _, step, _ in report['guarded'][path]}
        self.assertIn('Step03', guarded)            # first arrival in Zora's Domain
        self.assertTrue({'Step05', 'Step06'} <= guarded)
        self.assertFalse(guarded & {'Step07', 'Step08', 'Step09', 'Step10', 'Step14'})

    def test_no_other_flow_requests_the_quests(self):
        # The guarded flows are the only ones that move each opened quest back.
        from oot_rando.formats.inspect_nup import Nup
        nup = Nup(NUP)
        steps = quest_guard.challenge_steps(self.read(quest_guard.CHALLENGES))
        paths = sorted({p.split('/', 2)[2] for p in nup.entries
                        if '/romfs/Event/EventFlow/' in p and p.endswith('.bfevfl.zs')})
        charts = {}
        for path in paths:
            try:
                charts[path] = {q: quest_guard.step_requests(self.read(path), q)
                                for q in (w.ZORA_QUEST, w.KAKARIKO_QUEST, w.DOOR_QUEST)}
            except (ValueError, AttributeError):
                continue    # empty or unreadable flow charts
        for quest, floor, flows in ((w.ZORA_QUEST, w.ZORA_FLOOR, w.ZORA_FLOWS),
                                    (w.KAKARIKO_QUEST, w.KAKARIKO_FLOOR, w.KAKARIKO_FLOWS)):
            order = steps[quest]
            early = set(order[:order.index(floor)])
            found = {p for p, requests in charts.items() if any(s in early for _, s in requests[quest])}
            self.assertEqual(found, set(flows), quest)
        done = {p for p, requests in charts.items() if any(s == 'Complete' for _, s in requests[w.DOOR_QUEST])}
        self.assertEqual(done, {w.DOOR_FLOW})

    def test_no_logic_module_or_forced_step_moves_them_back(self):
        # Logic modules set steps too (TriggerChallengeSetStep…), and a step can be
        # forced by a GameData value (ForceProgressGameData): none lands before a floor.
        import ainb
        from oot_rando.formats import byml_codec
        steps = quest_guard.challenge_steps(self.read(quest_guard.CHALLENGES))
        floors = {w.ZORA_QUEST: w.ZORA_FLOOR, w.KAKARIKO_QUEST: w.KAKARIKO_FLOOR,
                  w.SPIRIT_QUEST: w.BRIDGE_FLOOR}
        written = []
        for path in sorted({p.split('/', 2)[2] for p in self.nup.entries
                            if '/romfs/Logic/' in p and p.endswith('.ainb')}):
            raw = self.nup.read(self.nup.latest('romfs/' + path))
            if b'ChallengeSetStep' not in raw:
                continue
            for node in ainb.AINB.from_binary(raw).as_dict()['Nodes']:
                if node['Name'].startswith('TriggerChallengeSetStep'):
                    values = [i['Default Value'] for i in node['Parameters']['Inputs']['String']]
                    written.append((values[0].split('/')[-1].split('.')[0], values[1]))
        self.assertTrue(written)
        for quest, floor in floors.items():
            order = steps[quest]
            early = [s for q, s in written if q == quest and order.index(s) < order.index(floor)]
            self.assertEqual(early, [], quest)
        self.assertFalse(any(q == w.DOOR_QUEST and s == 'Complete' for q, s in written))
        rows = byml_codec.load(self.read(quest_guard.CHALLENGES))['root']
        for row in rows:
            quest = row['__RowId'].split('/')[-1].split('.')[0]
            if quest in floors:
                forced = [st['Name'] for st in row['Steps'] if st.get('ForceProgressGameData')]
                order = steps[quest]
                self.assertFalse([s for s in forced if order.index(s) < order.index(floors[quest])], quest)

    def test_kakariko_gate_and_fire_quest(self):
        gamedata, flows, report = w.kakariko_gate_open(self.read, self.read(game_defaults.GAMEDATA),
                                                       self.read(quest_guard.CHALLENGES))
        self.assertEqual(game_defaults.read_defaults(gamedata, [w.KAKARIKO_GATE, 'Step_Get_StoneOfFire']),
                         {w.KAKARIKO_GATE: True, 'Step_Get_StoneOfFire': 'KakarikoVillageLetter'})
        self.assertEqual([s for _, s, _ in report['guarded'][w.DOOR_FLOW]], ['KakarikoVillageNpc'])

    def test_gerudo_valley_bridge(self):
        gamedata, flows, report = w.gerudo_valley_bridge(self.read, self.read(game_defaults.GAMEDATA),
                                                         self.read(quest_guard.CHALLENGES))
        self.assertEqual(game_defaults.read_defaults(gamedata, ['Step_SageOfSpirit']), {'Step_SageOfSpirit': 'Step01'})
        self.assertEqual(flows, {})
        # The bridge module shows the repaired bridge from Step01 on.
        import ainb
        nodes = ainb.AINB.from_binary(self.nup.read(self.nup.latest('romfs/' + w.BRIDGE_MODULE))).as_dict()['Nodes']
        self.assertIn('SageOfSpirit_IsAfter_Step01_Exp',
                      [s['Default Value'] for n in nodes for s in n.get('Parameters', {}).get('Inputs', {}).get('String', [])])

    def test_door_of_time_modules(self):
        import ainb
        raw = lambda path: self.nup.read(self.nup.latest('romfs/' + path))
        gamedata, files, report = w.door_of_time_open(self.read, self.read(game_defaults.GAMEDATA),
                                                      self.read(quest_guard.CHALLENGES), raw)
        door = ainb.AINB.from_binary(files[w.DOOR_MODULE]).as_dict()['Nodes'][3]['Parameters']['Inputs']['Bool']
        self.assertEqual({i['Name']: (i['Default Value'], i['Node Index']) for i in door
                          if i['Name'] in ('isOpen', 'IsSkipAnim')}, {'isOpen': (True, -1), 'IsSkipAnim': (True, -1)})
        # The song guard and the first pull are in every seed now (story_fixes, 21/11).
        from oot_rando.patching.story_fixes import DOOR_OPENED
        self.assertEqual(set(files), {w.DOOR_MODULE})
        self.assertEqual(game_defaults.read_defaults(gamedata, [DOOR_OPENED]), {DOOR_OPENED: True})
        # Applied on top of the seed's own door module edit too.
        from oot_rando.patching.story_fixes import door_opens_on_saved_flag
        w.door_always_open(door_opens_on_saved_flag(raw(w.DOOR_MODULE))[0])
        self.assertEqual(report['guarded'], {})

    def test_first_pull_before_sages(self):
        import ainb
        raw = lambda path: self.nup.read(self.nup.latest('romfs/' + path))
        files = {w.PEDESTAL_MODULE: w.pedestal_before_sages(raw(w.PEDESTAL_MODULE))}
        nodes = ainb.AINB.from_binary(files[w.PEDESTAL_MODULE]).as_dict()['Nodes']
        gate = nodes[1]['Parameters']['Inputs']['Bool']
        self.assertEqual([(s['Node Index'], s['Output Index']) for s in gate[0]['Sources']], [(2, 0), (6, 2)])
        # First and later requests use complementary readings of the SAME output.
        self.assertEqual(nodes[2]['Name'], 'InvBool.module')
        self.assertEqual(nodes[2]['Queries'], [5])
        self.assertEqual(nodes[2]['Parameters']['Inputs']['Bool'][0]['Node Index'], 5)
        self.assertEqual(nodes[2]['Parameters']['Inputs']['Bool'][0]['Output Index'], 0)
        self.assertTrue(nodes[2]['Parameters']['Outputs']['Bool'][0]['Is Output'])
        self.assertEqual(nodes[2]['Plugs']['Generic'], [{'Node Index': 5, 'Name': 'BoolMulti'}])
        self.assertEqual(nodes[1]['Queries'], [2, 6])
        self.assertEqual(nodes[1]['Plugs']['Generic'][0]['Node Index'], 2)
        self.assertEqual(unflagged_links(nodes), [])
        with self.assertRaises(ValueError):    # never applied twice
            w.pedestal_before_sages(files[w.PEDESTAL_MODULE])

    def test_child_pedestal_action_has_no_ready_step_gap(self):
        """The prompt may exist while BOTH event requests are disabled at Ready."""
        import ainb
        source = self.nup.read(self.nup.latest('romfs/' + w.PEDESTAL_MODULE))
        document = ainb.AINB.from_binary(w.pedestal_before_sages(source)).as_dict()
        nodes = document['Nodes']
        steps = quest_guard.challenge_steps(self.read(quest_guard.CHALLENGES))
        orders = {name: ('NotReady',) + tuple(steps[name]) for name in ('AllSage', 'DoorOfTime')}
        # The inserted inversion follows the game's own module call schema exactly.
        adult = self.nup.read(self.nup.latest('romfs/Logic/Market_Adult_Prefab_89da.logic.module.ainb'))
        native_inverse = ainb.AINB.from_binary(adult).as_dict()['Nodes'][1]
        for key in ('Name', 'Flags', 'Attachments', 'Properties', 'XLink Actions'):
            self.assertEqual(nodes[2][key], native_inverse[key])
        self.assertEqual(nodes[2]['Parameters']['Outputs'], native_inverse['Parameters']['Outputs'])
        self.assertEqual(document['Modules'], [{'Path': 'InvBool.module.ainb', 'Category': 'Logic', 'Instance Count': 1}])

        def requests(sage_step, door_step, pressed, after=None):
            current = {'AllSage': sage_step, 'DoorOfTime': door_step}
            def output(index, position):
                node = nodes[index]
                field = node['Parameters']['Outputs']['Bool'][position]
                if not field['Is Output']:
                    return False
                if node['Name'] == 'HoldChallengeCurrentStepCheckOrder':
                    if index == 5 and after is not None:
                        return after
                    strings = {x['Name']: x['Default Value'] for x in node['Parameters']['Inputs']['String']}
                    challenge = strings['ChallengeName'].split('/')[-1].split('.')[0]
                    order = orders[challenge]
                    a, b = order.index(current[challenge]), order.index(strings['ChallengeStepName'])
                    return {'IsAfter': a > b, 'IsBefore': a < b, 'IsEqual': a == b}[field['Name']]
                if node['Name'] == 'ActorLogicAttentionActor':
                    self.assertEqual(field['Name'], 'ReceiveDoAction')
                    return pressed
                if node['Name'] == 'InvBool.module':
                    source = node['Parameters']['Inputs']['Bool'][0]
                    return not output(source['Node Index'], source['Output Index'])
                self.assertEqual(node['Name'], 'OperateAND')
                sources = node['Parameters']['Inputs']['Bool'][0]['Sources']
                value = all(output(s['Node Index'], s['Output Index']) for s in sources)
                return value if field['Name'] == 'True' else not value
            triggers = [nodes[i]['Parameters']['Inputs']['Bool'][0] for i in (0, 3)]
            return [output(x['Node Index'], x['Output Index']) for x in triggers]

        # Ready is a real pre-first-arrival state, not "strictly before Ready".
        self.assertEqual(requests('Ready', 'Step05', True), [True, False])
        for step in orders['AllSage']:
            for door in orders['DoorOfTime']:
                with self.subTest(sages=step, door=door):
                    self.assertEqual(sum(requests(step, door, True)), 1)
                    self.assertEqual(requests(step, door, False), [False, False])
        # Partition also holds for either actual engine result, including inactive
        # quests where before/after comparisons need not be complementary.
        for after in (False, True):
            self.assertEqual(requests('NotReady', 'NotReady', True, after), [not after, after])
            self.assertEqual(requests('NotReady', 'NotReady', False, after), [False, False])

    def test_all_openings_together(self):
        raw = lambda path: self.nup.read(self.nup.latest('romfs/' + path))
        options = {'zora_fountain': 'open', 'open_kakariko': 'open', 'open_door_of_time': True,
                   'gerudo_fortress': 'fast', 'open_gerudo_valley_bridge': True}
        gamedata, files, reports = w.apply_openings(options, self.read, self.read(game_defaults.GAMEDATA),
                                                    self.read(quest_guard.CHALLENGES), raw)
        self.assertEqual(set(reports), set(options))
        import ainb
        for path, data in files.items():
            if path.endswith('.ainb'):
                self.assertEqual(unflagged_links(ainb.AINB.from_binary(data).as_dict()['Nodes']), [], path)
        self.assertEqual(game_defaults.read_defaults(gamedata, [w.CARPENTERS_HELPED, w.CARPENTERS_LEFT]),
                         {w.CARPENTERS_HELPED: 3, w.CARPENTERS_LEFT: 1})
        # The Kakariko guard of the Door of Time flow; the completion guard comes from
        # the story fixes (applied first by the seed build).
        from oot_rando.patching.story_fixes import _Chart, door_song_before_escape
        names = {e.name for e in _Chart(files[w.DOOR_FLOW]).chart.events}
        self.assertTrue(any(n.startswith(quest_guard.PREFIX) for n in names))
        self.assertFalse(any(n.startswith(w.DOOR_PREFIX) for n in names))
        fixed = door_song_before_escape(self.read(w.DOOR_FLOW))[0]
        _, both, _ = w.apply_openings(options, lambda p: fixed if p == w.DOOR_FLOW else self.read(p),
                                      self.read(game_defaults.GAMEDATA), self.read(quest_guard.CHALLENGES), raw)
        names = {e.name for e in _Chart(both[w.DOOR_FLOW]).chart.events}
        self.assertTrue(any(n.startswith(quest_guard.PREFIX) for n in names))
        self.assertTrue(any(n.startswith(w.DOOR_PREFIX) for n in names))


if __name__ == '__main__':
    unittest.main()
