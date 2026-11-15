"""World openings (patching/world_openings.py). Needs OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest

from oot_rando.patching import game_defaults, quest_guard, world_openings as w

NUP = os.environ.get('OOT_NUP')


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
        gate = ainb.AINB.from_binary(files[w.PEDESTAL_MODULE]).as_dict()['Nodes'][1]['Parameters']['Inputs']['Bool']
        self.assertEqual([(s['Node Index'], s['Output Index']) for s in gate[0]['Sources']], [(5, 1), (6, 2)])
        self.assertEqual([s for _, s, _ in report['guarded'][w.DOOR_FLOW]], ['Complete'])
        self.assertEqual(report['expression'], w.DOOR_COMPLETE_ONLY_AFTER)
        with self.assertRaises(ValueError):    # never applied twice
            w.pedestal_before_sages(files[w.PEDESTAL_MODULE])

    def test_all_openings_together(self):
        raw = lambda path: self.nup.read(self.nup.latest('romfs/' + path))
        options = {'zora_fountain': 'open', 'open_kakariko': 'open', 'open_door_of_time': True,
                   'gerudo_fortress': 'fast', 'open_gerudo_valley_bridge': True}
        gamedata, files, reports = w.apply_openings(options, self.read, self.read(game_defaults.GAMEDATA),
                                                    self.read(quest_guard.CHALLENGES), raw)
        self.assertEqual(set(reports), set(options))
        self.assertEqual(game_defaults.read_defaults(gamedata, [w.CARPENTERS_HELPED, w.CARPENTERS_LEFT]),
                         {w.CARPENTERS_HELPED: 3, w.CARPENTERS_LEFT: 1})
        # Both guards of the Door of Time flow are kept.
        from oot_rando.patching.story_fixes import _Chart
        names = {e.name for e in _Chart(files[w.DOOR_FLOW]).chart.events}
        self.assertTrue(any(n.startswith(quest_guard.PREFIX) for n in names))
        self.assertTrue(any(n.startswith(w.DOOR_PREFIX) for n in names))


if __name__ == '__main__':
    unittest.main()
