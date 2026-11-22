"""Evaluate the actual native barrier modules after the seed's patch composition."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.patching import game_defaults, quest_guard, story_fixes, world_openings as w


def created(raw, flag=False, quest=False):
    import ainb
    nodes = ainb.AINB.from_binary(raw).as_dict()['Nodes']

    def value(entry):
        if entry.get('Node Index', -1) < 0:
            return entry['Default Value']
        return output(entry['Node Index'], entry['Output Index'])

    def output(index, position):
        node = nodes[index]
        field = node['Parameters']['Outputs']['Bool'][position]
        if not field['Is Output']:
            return False
        if node['Name'] == 'HoldGameDataGetBoolSimple':
            return flag
        if node['Name'] in ('HoldGameDataGetBoolExpSimple', 'HoldChallengeCurrentStepCheckOrder'):
            return quest
        if node['Name'] == 'OperateAND':
            entry = node['Parameters']['Inputs']['Bool'][0]
            result = all(value(s) for s in entry['Sources']) if 'Sources' in entry else value(entry)
            return result if field['Name'] == 'True' else not result
        raise AssertionError(node['Name'])

    return {node['Properties']['String'][0]['Default Value']: value(next(
        i for i in node['Parameters']['Inputs']['Bool'] if i['Name'] == 'Logic_Create'))
        for node in nodes if node['Name'] in ('ActorLogicSimpleActor', 'ActorLogicAttackBootUpActor')}


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class NativeBarriers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.raw = staticmethod(lambda p: cls.nup.read(cls.nup.latest('romfs/' + p)))
        d = dictionaries(cls.nup)
        cls.read = staticmethod(lambda p: decompress(cls.raw(p), d))

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def test_bridge_option_repairs_the_actor_without_saved_quest_progress(self):
        for enabled in (False, True):
            gamedata = self.read(game_defaults.GAMEDATA)
            _, files, _ = w.apply_openings({'open_gerudo_valley_bridge': enabled}, self.read,
                                           gamedata, self.read(quest_guard.CHALLENGES), self.raw)
            raw = files.get(w.BRIDGE_MODULE) or self.raw(w.BRIDGE_MODULE)
            if enabled:
                self.assertEqual(set(files), {w.BRIDGE_MODULE})
            # An existing save can still have the quest before its repair stage.
            for quest in (False, True):
                actors = created(raw, quest=quest)
                repaired = enabled or quest
                self.assertEqual(actors['Obj_GerudoValley_Bridge_A_02_e280'], repaired)
                for name in ('Obj_GerudoValley_Bridge_A_01_3ac8',
                             'Obj_HorseJumpEvent_GerudoValley_75b9',
                             'Obj_HorseJumpEvent_GerudoValley_9f9b'):
                    self.assertEqual(actors[name], not repaired)

    def test_child_gate_follows_letter_delivery_despite_later_fire_quest(self):
        fixes = {path: fix for path, _, fix in story_fixes.scene_module_fixes()}
        modules = {
            'Logic/KakarikoVillage_Child_OpenGate_Prefab_1fcc.logic.module.ainb':
                ('Obj_Kakariko_SwitchShutter_A_01_4aa2', False),
            'Logic/KakarikoVillage_Child_GateClose_Prefab_6b8b.logic.module.ainb':
                ('Obj_Kakariko_SwitchShutter_A_01_dfe1', True),
        }
        for path, (actor, opened_position) in modules.items():
            raw = fixes[path](self.raw(path))[0] if path in fixes else self.raw(path)
            from test_world_openings import unflagged_links
            import ainb
            self.assertEqual(unflagged_links(ainb.AINB.from_binary(raw).as_dict()['Nodes']), [])
            for flag in (False, True):
                for quest in (False, True):
                    with self.subTest(path=path, delivered=flag, quest=quest):
                        self.assertEqual(created(raw, flag, quest)[actor], flag == opened_position)

    def test_gate_option_initializes_delivery_flag_only_when_open(self):
        source = self.read(game_defaults.GAMEDATA)
        challenges = self.read(quest_guard.CHALLENGES)
        for option in ('closed', 'open'):
            raw, _, _ = w.apply_openings({'open_kakariko': option}, self.read,
                                         source, challenges, self.raw)
            self.assertEqual(game_defaults.read_defaults(raw, [w.KAKARIKO_GATE]),
                             {w.KAKARIKO_GATE: option == 'open'})

    def test_open_fountain_removes_the_native_wall_as_well_as_moving_the_king(self):
        from oot_rando.formats import byml_codec
        path = 'Banc/ZoraDomain/ZoraDomain_Child_Dynamic.bcett.byml.zs'
        actors = byml_codec.load(self.read(path))['root']['Actors']
        wall = next(a for a in actors if int(a['Hash']) == 14853753789178157158)
        self.assertEqual(wall['Gyaml'], 'FldObj_AirWall_Player')
        presence = wall['Presence']
        self.assertEqual(presence, {'FlagName': 'HavePlayedEvent.Dm_Zora_0010',
                                    'IsNegation': True, 'IsCheckLazy': False})
        source = self.read(game_defaults.GAMEDATA)
        challenges = self.read(quest_guard.CHALLENGES)
        for option in ('closed', 'open'):
            raw, _, reports = w.apply_openings({'zora_fountain': option}, self.read,
                                               source, challenges, self.raw)
            values = game_defaults.read_defaults(raw, [presence['FlagName'], w.ZORA_STEP])
            present = values[presence['FlagName']] != presence['IsNegation']
            with self.subTest(option=option):
                self.assertEqual(present, option != 'open')
                if option == 'open':
                    self.assertEqual(values[w.ZORA_STEP], w.ZORA_FLOOR)
                    self.assertTrue(reports['zora_fountain']['defaults'][presence['FlagName']])
                    # This check rejects unsaved or map-reset flags: the passage
                    # must remain open after changing areas and reloading.
                    game_defaults.check_defaults(source, {presence['FlagName']: True})

    def test_gate_rewrite_preserves_movement_and_roundtrips(self):
        import ainb
        for path, opened in ((w.KAKARIKO_CLOSED_MODULE, False), (w.KAKARIKO_OPEN_MODULE, True)):
            original = ainb.AINB.from_binary(self.raw(path)).as_dict()
            raw, _ = w.kakariko_gate_on_letter(self.raw(path), opened)
            document = ainb.AINB.from_binary(raw).as_dict()
            self.assertEqual(document['Nodes'][0], original['Nodes'][0])
            actor = document['Nodes'][1]
            before_actor = original['Nodes'][1]
            old = next(i for i in before_actor['Parameters']['Inputs']['Bool'] if i['Name'] == 'Logic_Create')
            old['Output Index'] = 1 if opened else 0
            self.assertEqual(actor, before_actor)
            with self.assertRaises(ValueError):
                w.kakariko_gate_on_letter(raw, opened)


if __name__ == '__main__':
    unittest.main()
