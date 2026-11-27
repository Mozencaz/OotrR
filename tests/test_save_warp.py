"""Save Warp button of the pause menu (patching/save_warp.py), always on."""
import _src_path  # noqa: F401  (src on sys.path)
import copy
import os
import struct
import unittest

NUP = os.environ.get('OOT_NUP')


def walk(nodes, override, name, found, always):
    """Leaf reached by OnLoadBancParam's start position selectors.

    ``override``: the caller's IsOverrideTraverseBasePos; ``name``: its start name;
    ``found``: a StartPos of that name exists; ``always``: the banc's IsAlwaysStartFromStartPos."""
    inputs = {12: False, 43: always, 124: override, 75: found}
    node = 14
    while True:
        entry = nodes[node]
        kind = entry['Name'] or entry['Node Type']
        children = entry['Plugs'].get('Child', [])
        if kind == 'Element_BoolSelector':
            source = next(p['Node Index'] for p in entry['Plugs']['Generic'] if p.get('Name') == 'Input')
            node = next(p['Node Index'] for p in children if p['Name'] == ('True' if inputs[source] else 'False'))
        elif kind == 'Element_StringSelector':
            case = next((p for p in children if not p.get('Is Default') and p.get('Condition') == name), None)
            node = (case or next(p for p in children if p.get('Is Default')))['Node Index']
        else:
            return node


def choose(nodes, node, value):
    """Child of a Bool/String selector for ``value``."""
    children = nodes[node]['Plugs']['Child']
    if nodes[node]['Node Type'] == 'Element_BoolSelector':
        return next(p['Node Index'] for p in children if p['Name'] == ('True' if value else 'False'))
    case = next((p for p in children if not p.get('Is Default') and p.get('Condition') == value), None)
    return (case or children[-1])['Node Index']


def strings(node):
    return {p['Name']: p['Default Value'] for p in node['Parameters']['Inputs'].get('String', [])}


def bools(node):
    return {p['Name']: p['Default Value'] for p in node['Parameters']['Inputs'].get('Bool', [])}


SAVED, BANC_START, NAMED = 11, 28, 73
DUNGEON_START = 44   # the same banc start position as 28, with its rotation


class WiringTests(unittest.TestCase):
    def test_always_on(self):
        import inspect
        from oot_rando.randomizer import randomizer_core
        source = inspect.getsource(randomizer_core.generate)
        self.assertIn('patch_save_warp', source)
        self.assertIn('SAVE_WARP_FLAG: False', source)


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.randomizer.randomizer_core import Nup, dictionaries, effective_members
        from oot_rando.formats.inspect_resources import decompress
        from oot_rando.patching import save_warp
        nup = Nup(NUP)
        members = effective_members(nup)
        d = dictionaries(nup)
        cls.sw, cls.members, cls.d = save_warp, members, d
        cls.read = staticmethod(lambda path: nup.read(members[path]))
        cls.unpack = staticmethod(lambda path: decompress(nup.read(members[path]), d))
        cls.messages = sorted(m for m in members if m.startswith('Mals/') and '.Product.110.' in m)
        cls.files = save_warp.patch_save_warp(cls.read, cls.messages, cls.unpack)

    def nodes(self, raw):
        import ainb
        return ainb.AINB.from_binary(raw).as_dict()['Nodes']

    def test_write_ainb_round_trip(self):
        # The ainb library alone writes an empty 0x408 blackboard 8 bytes short.
        import ainb
        sw = self.sw
        for path in (sw.ON_LOAD_MODULE, sw.SAVE_MODULE, sw.PLUS_MENU_MODULE, sw.MENU_LOAD_MODULE):
            with self.subTest(path=path):
                document = ainb.AINB.from_binary(self.read(path)).as_dict()
                self.assertEqual(len(sw.write_ainb(document)), len(self.read(path)))

    def test_title_and_load_screens_untouched(self):
        for path in ('Sequence/TitleToMainWithLoadSave.module.ainb', 'Sequence/LoadCheck.module.ainb'):
            self.assertNotIn(path, self.files)

    def test_start_position_choices(self):
        sw = self.sw
        vanilla, patched = self.nodes(self.read(sw.ON_LOAD_MODULE)), self.nodes(self.files[sw.ON_LOAD_MODULE])
        marker = sw.LOAD_MARKER
        cases = [
            # (override, name, found, always): vanilla leaf, patched leaf
            ((True, marker, False, False), BANC_START, SAVED),          # warp in a vanilla-load banc
            ((True, marker, False, True), DUNGEON_START, DUNGEON_START),  # warp in a dungeon, to Link's house
            ((True, 'LightPrelude', True, False), NAMED, NAMED),        # warp to the Temple of Time
            ((True, '', False, False), SAVED, SAVED),                   # plain load, game over retry, event warps
            ((True, '', False, True), DUNGEON_START, SAVED),             # ... in a dungeon: unchanged position
            ((True, 'EntrancePos', True, True), DUNGEON_START, NAMED),   # door: its named start
            ((False, '', False, False), BANC_START, BANC_START),         # new game, plain banc change
            ((False, '', False, True), DUNGEON_START, BANC_START),
        ]
        for args, before, after in cases:
            with self.subTest(args=args):
                self.assertEqual(walk(vanilla, *args), before)
                self.assertEqual(walk(patched, *args), after)
        for name in sw.DUNGEONS + sw.WORLD_ZONES + sw.VANILLA_LOAD:
            self.assertNotIn(b'IsAlwaysStartFromStartPos', self.read(sw.banc_param(name)))

    def test_menu_load_reloads_into_the_warp_destination(self):
        sw = self.sw
        call, sequence, banc_query = sw.MENU_LOAD_CALL
        vanilla, nodes = self.nodes(self.read(sw.MENU_LOAD_MODULE)), self.nodes(self.files[sw.MENU_LOAD_MODULE])
        for index, node in enumerate(vanilla):   # the vanilla nodes are kept
            if index not in (sequence, 6, 10):
                self.assertEqual(nodes[index], node, index)
        position = [p['Node Index'] for p in vanilla[sequence]['Plugs']['Child']].index(call)
        self.assertEqual(nodes[sequence]['Plugs']['Child'],
                         vanilla[sequence]['Plugs']['Child'][:position]
                         + vanilla[sequence]['Plugs']['Child'][position + 1:])
        gate = nodes[sequence]['Plugs']['Transition'][0]['Node Index']
        self.assertIn('Is Root Node', nodes[gate]['Flags'])
        flag = nodes[nodes[gate]['Parameters']['Inputs']['Bool'][0]['Node Index']]
        self.assertEqual(strings(flag)['GameDataFullName'], sw.SAVE_WARP_FLAG)
        normal = nodes[choose(nodes, gate, False)]
        normal_state = nodes[normal['Plugs']['Transition'][0]['Node Index']]
        self.assertIn('Is Root Node', normal_state['Flags'])
        self.assertEqual(normal_state['Plugs']['Child'], [{'Node Index': call, 'Name': ''}])
        self.assertEqual(normal_state['Plugs']['Transition'][0]['Node Index'], 2)
        destination = choose(nodes, gate, True)
        self.assertEqual(nodes[destination]['Parameters']['Inputs']['String'][0]['Node Index'], banc_query)
        path = vanilla[call]['Plugs']['String'][0]['Node Index']
        seen = set()

        def warp(banc, childhood):
            """(banc loaded, start name) of a warp from ``banc``."""
            leaf = choose(nodes, destination, banc)
            if nodes[leaf]['Node Type'] == 'Element_BoolSelector':
                query = nodes[nodes[leaf]['Parameters']['Inputs']['Bool'][0]['Node Index']]
                self.assertEqual(strings(query)['GameDataFullName'], 'Sequence_IsChildhood')
                leaf = choose(nodes, leaf, childhood)
            # Leave the mutable selectors before the save reload clears the
            # request flag and restores Sequence_CurrentBanc.
            self.assertEqual(nodes[leaf]['Name'], 'SeqOneShotEnd')
            state = nodes[nodes[leaf]['Plugs']['Transition'][0]['Node Index']]
            self.assertEqual(state['Node Type'], 'Element_Sequential')
            self.assertIn('Is Root Node', state['Flags'])
            self.assertEqual(state['Plugs']['Transition'][0]['Node Index'], 2)
            self.assertEqual(nodes[2]['Node Type'], 'Element_StateEnd')
            self.assertEqual(len(state['Plugs']['Child']), 1)
            leaf = state['Plugs']['Child'][0]['Node Index']
            seen.add(leaf)
            change = copy.deepcopy(nodes[leaf])
            self.assertEqual(change['Name'], 'ChangeBanc.module')
            self.assertIs(bools(change)['IsLoadFromSaveData'], True)   # the save just written
            self.assertIs(bools(change)['IsEnableFastLoad'], False)
            source = change['Plugs']['String'][0]['Node Index']
            if source != path:   # a fixed banc
                concat = copy.deepcopy(nodes[source])
                banc = concat['Parameters']['Inputs']['String'][1]['Default Value']
                concat['Parameters']['Inputs']['String'][1] = vanilla[path]['Parameters']['Inputs']['String'][1]
                concat.update({k: vanilla[path][k] for k in ('Node Index', 'GUID', 'Queries', 'Plugs')})
                self.assertEqual(concat, vanilla[path])
            after = nodes[change['Plugs']['Child'][0]['Node Index']]   # its own OnLoadGameSaveData
            load = vanilla[vanilla[call]['Plugs']['Child'][0]['Node Index']]
            self.assertEqual(dict(after, **{k: load[k] for k in ('Node Index', 'GUID')}), load)
            # Otherwise the vanilla call.
            change.update({'Node Index': call, 'GUID': vanilla[call]['GUID'], 'Queries': vanilla[call]['Queries']})
            change['Plugs'] = copy.deepcopy(vanilla[call]['Plugs'])
            for param in change['Parameters']['Inputs']['String']:
                if param['Name'] == 'BancParam':
                    param['Node Index'] = path
            for param in change['Parameters']['Inputs']['Bool']:
                if param['Name'] == 'IsEnableFastLoad':
                    param['Default Value'] = True
            start = next(p for p in change['Parameters']['Inputs']['String'] if p['Name'] == sw.START_NAME)
            name, start['Default Value'] = start['Default Value'], ''
            self.assertEqual(change, vanilla[call])
            return banc, name
        for banc in sw.DUNGEONS + sw.VANILLA_LOAD:
            self.assertEqual(warp(banc, True), (banc, sw.LOAD_MARKER))
        for banc in sw.WORLD_ZONES:
            self.assertEqual(warp(banc, True), ('KokiriForest_Child', sw.LOAD_MARKER))
            self.assertEqual(warp(banc, False), ('Market_Adult', 'LightPrelude'))
        calls = [n for n in nodes if n['Name'] == 'ChangeBanc.module']
        self.assertEqual(len(calls), 4)
        for change in calls:
            for param in change['Parameters']['Inputs']['Vector3F']:
                source = nodes[param['Node Index']]
                self.assertTrue(any(p['Node Index'] == change['Node Index']
                                    for p in source['Plugs']['Generic']),
                                (source['Name'], change['Node Index']))
        for index in (6, 10):
            expected = copy.deepcopy(vanilla[index])
            output = next(p for p in expected['Plugs']['Generic'] if p['Node Index'] == call)
            expected['Plugs']['Generic'].extend(dict(output, **{'Node Index': n['Node Index']})
                                                for n in calls if n['Node Index'] != call)
            self.assertEqual(nodes[index], expected)
        self.assertEqual(len({n['Plugs']['Child'][0]['Node Index'] for n in calls}), 4)
        self.assertEqual(len(seen), 3)
        modules = {m['Path']: m['Instance Count'] for m in __import__('ainb').AINB.from_binary(self.files[sw.MENU_LOAD_MODULE]).as_dict()['Modules']}
        self.assertEqual(modules['ChangeBanc.module.ainb'], 4)
        self.assertEqual(modules['OnLoadGameSaveData.module.ainb'], 4)

    def test_save_screen_in_warp_mode(self):
        sw = self.sw
        vanilla, nodes = self.nodes(self.read(sw.SAVE_MODULE)), self.nodes(self.files[sw.SAVE_MODULE])
        self.assertEqual(choose(nodes, 0, 'Pa_CheckButton_01'), 12)     # Cancel, as before
        self.assertEqual(choose(nodes, 0, ''), 12)                      # B
        selector = choose(nodes, 0, 'Pa_CheckButton_00')
        flag = nodes[nodes[selector]['Parameters']['Inputs']['Bool'][0]['Node Index']]
        self.assertEqual(strings(flag)['GameDataFullName'], sw.SAVE_WARP_FLAG)
        self.assertEqual(choose(nodes, selector, False), 1)              # no request: the vanilla save
        start = choose(nodes, selector, True)
        save = nodes[start]['Plugs']['Transition'][0]['Node Index']
        steps = [p['Node Index'] for p in nodes[save]['Plugs']['Child']]
        self.assertEqual(steps[1:3] + steps[4:], [54, 25, 27])  # native save, plus slot capture
        self.assertEqual((strings(nodes[steps[0]])['GameDataFullName'], bools(nodes[steps[0]])['Value']),
                         (sw.SAVE_WARP_FLAG, False))
        # Capture the written slot before the save can advance its manual index.
        select = nodes[steps[3]]
        self.assertEqual(strings(select)['GameDataName'], 'SelectedSavePathIndex')
        self.assertEqual(nodes[select['Parameters']['Inputs']['Int'][1]['Node Index']]['Name'],
                         'SeqQueryGameDataGetManualSaveIndex')
        written_slot = next(p['Node Index'] for p in nodes[5]['Parameters']['Inputs']['Int']
                            if p['Name'] == 'SlotIndex')
        self.assertEqual(select['Parameters']['Inputs']['Int'][1]['Node Index'], written_slot)
        self.assertFalse(any(n['Name'] == 'SeqQueryGetLatestSaveIndex' for n in nodes))
        caption = nodes[select['Parameters']['Inputs']['Pointer'][0]['Node Index']]
        self.assertEqual(strings(caption)['GameDataFullName'], 'CaptionData')
        after = nodes[save]['Plugs']['Transition'][0]['Node Index']
        steps = [p['Node Index'] for p in nodes[after]['Plugs']['Child']]
        self.assertEqual(steps[:3], [35, 23, 56])
        # The save is readable only once the managers are done, as ConfirmationLoad waits.
        wait_auto = [nodes[p['Node Index']] for p in nodes[steps[3]]['Plugs']['Child']]
        self.assertEqual(nodes[steps[3]]['Node Type'], 'Element_Simultaneous')
        self.assertEqual([n['Name'] for n in wait_auto], ['SeqExecuteWaitAutoSave'])
        self.assertEqual(wait_auto[0]['Parameters'], vanilla[26]['Parameters'])
        self.assertEqual(nodes[steps[4]]['Name'], 'SeqExecuteWaitCaptionMgrStable')
        steps = steps[:3] + steps[5:]
        # Leaving the menu, as LoadCheck.module before the menu's load.
        overlay, paused = [p['Node Index'] for p in nodes[steps[3]]['Plugs']['Child']]
        self.assertEqual(strings(nodes[overlay])['ScreenName'], 'SystemOverlay_00')
        query = nodes[nodes[paused]['Parameters']['Inputs']['Bool'][0]['Node Index']]
        self.assertEqual(strings(query)['GameDataFullName'], 'Sequence_IsPreGamePause')
        self.assertEqual(nodes[choose(nodes, paused, False)]['Name'], 'SeqOneShotEnd')
        pause = [nodes[p['Node Index']] for p in nodes[choose(nodes, paused, True)]['Plugs']['Child']]
        self.assertEqual([n['Name'] for n in pause], ['ChangePreGamePause.module',
                                                      'SeqOneShotRequestCancelGameScreenCapture', 'GamePauseOn.module'])
        self.assertIs(bools(pause[0])['IsPause'], False)
        self.assertIs(bools(pause[1])['IsForce'], True)
        self.assertEqual((strings(nodes[steps[4]])['GameDataFullName'], bools(nodes[steps[4]])['Value']),
                         (sw.SAVE_WARP_FLAG, True))
        end = nodes[nodes[after]['Plugs']['Transition'][0]['Node Index']]
        self.assertEqual(end['Properties']['String'][0]['Default Value'], 'Warp')
        cancel = [p['Node Index'] for p in nodes[24]['Plugs']['Child']]
        self.assertEqual(cancel[:2], [15, 31])
        self.assertEqual((strings(nodes[cancel[2]])['GameDataFullName'], bools(nodes[cancel[2]])['Value']),
                         (sw.SAVE_WARP_FLAG, False))
        for index, node in enumerate(vanilla):
            if index not in (0, 24):
                self.assertEqual(nodes[index], node, index)
        import ainb
        modules = {m['Path'] for m in ainb.AINB.from_binary(self.files[sw.SAVE_MODULE]).as_dict()['Modules']}
        self.assertLessEqual({'ChangePreGamePause.module.ainb', 'GamePauseOn.module.ainb'}, modules)

    def test_repeated_warps_load_the_slot_just_written(self):
        """A stale latest/loaded index must never replace the new manual save."""
        sw = self.sw
        nodes = self.nodes(self.files[sw.SAVE_MODULE])
        selector = choose(nodes, 0, 'Pa_CheckButton_00')
        start = choose(nodes, selector, True)
        save = nodes[start]['Plugs']['Transition'][0]['Node Index']
        after = nodes[save]['Plugs']['Transition'][0]['Node Index']
        selected = None
        disk = {i: ('old', i) for i in range(6)}
        latest = 3

        def run(index, state, progress):
            nonlocal selected
            node = nodes[index]
            if node['Name'] == 'SeqOneShotSetGameDataInt' and strings(node).get('GameDataName') == 'SelectedSavePathIndex':
                source = nodes[node['Parameters']['Inputs']['Int'][1]['Node Index']]
                if source['Name'] == 'SeqQueryGameDataGetManualSaveIndex':
                    selected = state['manual']
                else:
                    self.assertEqual(source['Name'], 'SeqQueryGetLatestSaveIndex')
                    selected = latest
            elif node['Name'] == 'SeqExecuteSaveGameData':
                slot_source = next(p['Node Index'] for p in node['Parameters']['Inputs']['Int']
                                   if p['Name'] == 'SlotIndex')
                self.assertEqual(nodes[slot_source]['Name'], 'SeqQueryGameDataGetManualSaveIndex')
                disk[state['manual']] = progress
            elif node['Name'] == 'SeqOneShotManualSsetCaptionData':
                # Also cover engines that advance the writable slot after saving.
                state['manual'] = (state['manual'] + 1) % 3
            else:
                for child in node['Plugs'].get('Child', []):
                    # Story/UI selectors have no bearing on the saved slot.
                    if node['Node Type'] not in ('Element_BoolSelector', 'Element_StringSelector'):
                        run(child['Node Index'], state, progress)

        for slot, progress in [(0, ('warp', 1)), (1, ('warp', 2)), (2, ('warp', 3)), (0, ('warp', 4))]:
            with self.subTest(slot=slot, progress=progress):
                state = {'manual': slot}
                run(save, state, progress)
                run(after, state, progress)
                self.assertEqual(disk[selected], progress)
                latest = selected
                # Another manual/auto save may become latest between warps.
                disk[3] = ('unrelated save', progress)
                latest = 3

    def test_plus_menu_button(self):
        sw = self.sw
        vanilla, nodes = self.nodes(self.read(sw.PLUS_MENU_MODULE)), self.nodes(self.files[sw.PLUS_MENU_MODULE])
        request = nodes[choose(nodes, sw.SYSTEM_BUTTONS, sw.BUTTON_PATH)]
        self.assertEqual((strings(request)['GameDataFullName'], bools(request)['Value']), (sw.SAVE_WARP_FLAG, True))
        self.assertEqual(request['Plugs']['Transition'][0]['Node Index'], sw.SAVE_NODE)   # then the save screen
        self.assertEqual(choose(nodes, sw.SYSTEM_BUTTONS_OTHER, sw.BUTTON_PATH), 52)
        for i in range(5):   # the other buttons are unchanged
            button = f'Pa_System_00/Pa_Button_0{i}'
            self.assertEqual(choose(nodes, sw.SYSTEM_BUTTONS, button), choose(vanilla, sw.SYSTEM_BUTTONS, button))
        ends = {p['Transition Name']: p['Node Index'] for p in nodes[sw.SAVE_NODE]['Plugs']['Transition']}
        self.assertEqual(ends, {'No': 63, 'Yes': 63, 'Warp': sw.MENU_LOAD_NODE})
        loads = {p['Transition Name']: p['Node Index'] for p in nodes[59]['Plugs']['Transition']}
        self.assertEqual(loads['Yes'], sw.MENU_LOAD_NODE)                  # ConfirmationLoad's own load

    def test_layout_button(self):
        from oot_rando.formats.inspect_resources import sarc
        sw = self.sw
        before = dict(sarc(self.unpack(sw.LAYOUT_ARCHIVE)))
        after = dict(sarc(self.files[sw.LAYOUT_ARCHIVE]))
        self.assertEqual({k for k in after if after[k] != before[k]}, {sw.SYSTEM_LAYOUT})
        raw, out = before[sw.SYSTEM_LAYOUT], after[sw.SYSTEM_LAYOUT]
        panes0, parts0 = sw.read_layout_dictionaries(raw)
        panes, parts = sw.read_layout_dictionaries(out)
        self.assertEqual(list(panes), list(panes0) + [sw.NEW_BUTTON])
        self.assertEqual(list(parts), list(parts0) + [sw.NEW_BUTTON])
        new, old = panes[sw.NEW_BUTTON][0], panes['Pa_Button_04'][0]
        y_new, y_old = struct.unpack_from('<f', out, new + 0x20)[0], struct.unpack_from('<f', out, old + 0x20)[0]
        self.assertEqual(y_new, y_old + sw.BUTTON_STEP)
        self.assertEqual(out[new:new + 0x20] + out[new + 0x24:new + 0x34] + out[new + 0x38:new + 0x42],
                         out[old:old + 0x20] + out[old + 0x24:old + 0x34] + out[old + 0x38:old + 0x42])
        self.assertEqual(struct.unpack_from('<I', out, new + 0x34)[0], len(panes))
        self.assertEqual(struct.unpack_from('<H', out, new + 0x42)[0], len(parts) - 1)
        part = parts[sw.NEW_BUTTON][0]
        name = struct.unpack_from('<Q', out, part)[0]
        self.assertEqual(out[name:out.index(b'\0', name)], b'PaCommonBtnThin_00')
        self.assertEqual(struct.unpack_from('<I', out, part + 0x40)[0], len(panes) - 1)
        for root in ('RootPane', 'N_All_00', 'N_InOut_00'):
            self.assertEqual(struct.unpack_from('<I', out, panes[root][0] + 0x34)[0], len(panes))
        # Every old record and string is the same, the hashes kept.
        for key, (offset, digest) in panes0.items():
            self.assertEqual(panes[key][1], digest)
            if key not in ('RootPane', 'N_All_00', 'N_InOut_00'):
                self.assertEqual(out[panes[key][0]:panes[key][0] + 0x44], raw[offset:offset + 0x44], key)
        pool = struct.unpack_from('<I', raw, 0xd4)[0]
        shift = struct.unpack_from('<I', out, 0xd4)[0] - pool
        for at in range(0, pool - 7, 8):
            value = struct.unpack_from('<Q', raw, at)[0]
            if pool <= value < len(raw):
                moved = struct.unpack_from('<Q', out, at)[0]
                self.assertEqual(moved, value + shift)
                self.assertEqual(out[moved:out.index(b'\0', moved)], raw[value:raw.index(b'\0', value)])
        self.assertEqual(struct.unpack_from('<I', out, 8)[0], len(out))

    def test_button_text(self):
        from oot_rando.formats import msbt
        from oot_rando.formats.inspect_resources import sarc
        self.assertEqual(set(self.messages), {p for p in self.files if p.startswith('Mals/')})
        for path in self.messages:
            message = msbt.load(dict(sarc(self.files[path]))[self.sw.MENU_TEXT])
            self.assertEqual(message.get(self.sw.BUTTON_LABEL), b'Save Warp\0', path)   # English everywhere

    def test_every_banc_param(self):
        from oot_rando.formats import byml_codec
        sw = self.sw
        params = {p.split('/')[-1].split('.')[0]: p for p in self.members if p.startswith('Banc/GameBancParam/')}
        self.assertEqual(set(params), set(sw.DUNGEONS) | set(sw.WORLD_ZONES) | set(sw.VANILLA_LOAD))
        self.assertFalse(set(sw.DUNGEONS) & set(sw.WORLD_ZONES) or set(sw.WORLD_ZONES) & set(sw.VANILLA_LOAD)
                         or set(sw.DUNGEONS) & set(sw.VANILLA_LOAD))
        self.assertIn(sw.CHILD_HOME, sw.WORLD_ZONES)
        self.assertIn(sw.ADULT_HOME[0], sw.WORLD_ZONES)
        parents = {}
        for name, path in params.items():
            parent = byml_codec.load(self.read(path))['root'].get('$parent')
            parents[name] = parent.split('/')[-1].split('.')[0] if parent else None

        def inherits(name):
            name = parents.get(name)
            while name:
                if name in sw.ZONES:
                    return True
                name = parents.get(name)
            return False
        for name in sw.ZONES:
            self.assertIs(byml_codec.load(self.files[sw.banc_param(name)])['root'][sw.ALWAYS_START], True, name)
        for name in set(sw.WORLD_ZONES) - set(sw.ZONES):
            self.assertNotIn(sw.banc_param(name), self.files)
        for name in sw.VANILLA_LOAD:
            with self.subTest(name=name):
                if inherits(name):   # stages of a dungeon: set back to false
                    self.assertIs(byml_codec.load(self.files[sw.banc_param(name)])['root'][sw.ALWAYS_START], False)
                else:
                    self.assertNotIn(sw.banc_param(name), self.files)
        self.assertTrue(inherits('MegStage') and not inherits('WolfosStage') and not inherits('CrumblingGanonCastle'))

    def test_start_positions(self):
        """``SavePos`` names no StartPos; ``LightPrelude`` is in the adult market (Temple of Time)."""
        from oot_rando.formats import byml_codec
        temple = []
        for path in self.members:
            if path.startswith('Banc/') and path.endswith('.bcett.byml.zs'):
                raw = self.unpack(path)
                if b'StartPos' not in raw:
                    continue
                for actor in byml_codec.load(raw)['root'].get('Actors', []):
                    if actor.get('Gyaml') == 'StartPos':
                        self.assertNotEqual(actor.get('Name'), self.sw.LOAD_MARKER, path)
                        if actor.get('Name') == self.sw.ADULT_HOME[1] and path.startswith('Banc/Market/Market_Adult_'):
                            temple.append(path)
        self.assertEqual(temple, ['Banc/Market/Market_Adult_Dynamic.bcett.byml.zs'])


if __name__ == '__main__':
    unittest.main()
