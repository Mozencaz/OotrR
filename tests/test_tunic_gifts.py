"""Native tunic gifts enter NPC shuffle and share receipts across talk routes."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.game.extra_sources import NPC_GIFTS, scan_event_sources
from oot_rando.game.item_forms import can_take, form_actor
from oot_rando.game.remake_world import item_actor
from oot_rando.patching import story_fixes as s
from oot_rando.patching.event_patch import patch_event_params, add_collection_markers
from oot_rando.formats.evfl_tools import parse_flow

NUP = os.environ.get('OOT_NUP')
GIFTS = {'goron': ('GC Rolling Goron as Adult', 'SageOfFire', 'Event18', 'Obj_Armor_Goron'),
         'zora': ('ZD King Zora Thawed', 'SageOfWater', 'Event242', 'Obj_Armor_Zora')}


class Registration(unittest.TestCase):
    def test_both_tunics_are_npc_gifts_and_can_move_to_other_forms(self):
        for location, stem, event, actor in GIFTS.values():
            self.assertIn(((location,), (), stem, ((event, actor),)), NPC_GIFTS)
            item = 'Goron Tunic' if 'Goron' in actor else 'Zora Tunic'
            self.assertEqual(item_actor(item, ''), actor)
            for form in ('event', 'chest', 'world', 'shop'):
                self.assertTrue(can_take(actor, form))
                self.assertTrue(form_actor(actor, form))


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class NativeGifts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries, decompress
        cls.nup = Nup(NUP)
        d = dictionaries(cls.nup)
        paths = [s.LINK_GORON_FLOW, s.SAGE_OF_WATER_FLOW, s.KING_ZORA_FLOW,
                 'Event/EventFlow/SageOfFire.bfevfl.zs']
        cls.raw = {p: decompress(cls.nup.read(cls.nup.latest('romfs/' + p)), d) for p in paths}

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def patched(self, actor='Item_Hookshot'):
        raw = dict(self.raw)
        config = {}
        for key, (location, stem, event, before) in GIFTS.items():
            path = 'Event/EventFlow/' + stem + '.bfevfl.zs'
            flag = 'RandoCheck.test.npc#' + location
            config[key] = {'actor': actor, 'flag': flag}
            raw[path] = patch_event_params(raw[path], [(event, 'ActorName', before, actor)])
            raw[path], _ = add_collection_markers(raw[path], {event: flag})
        for path, _, fix in s.flow_fixes(s.STONE_SETS['all'], config):
            if path in raw:
                raw[path] = fix(raw[path])[0]
        return {p: parse_flow(b).flowchart for p, b in raw.items()}, config

    def test_native_scanner_matches_both_reward_sites(self):
        gifts = [('npc', (loc,), (), ((stem, event, actor),))
                 for loc, stem, event, actor in GIFTS.values()]
        entries = scan_event_sources(self.raw, lambda p: parse_flow(self.raw[p]), gifts)
        for location, _, _, actor in GIFTS.values():
            entry = entries['npc#' + location]
            self.assertIsNone(entry['reason'])
            self.assertEqual(entry['kind'], 'exact')
            self.assertEqual(entry['before'], actor)

    def test_goron_both_talks_use_same_reward_and_saved_receipt(self):
        charts, config = self.patched()
        npc = {e.name: e for e in charts[s.LINK_GORON_FLOW].events}
        native = {e.name: e for e in charts['Event/EventFlow/SageOfFire.bfevfl.zs'].events}
        self.assertEqual(npc['RandoGoronTunicGive'].data.params.data['ActorName'], 'Item_Hookshot')
        self.assertEqual(native['Event18'].data.params.data['ActorName'], 'Item_Hookshot')
        flag = config['goron']['flag']
        for events, name in ((npc, 'RandoGoronTunicHas'), (native, 'RandoGoronGiftCollected')):
            gate = events[name]
            self.assertEqual(str(gate.data.actor_query.v), 'EventQueryIsGameDataBool')
            self.assertEqual(gate.data.params.data['GameDataName'], flag)
        self.assertEqual(native['Event36'].data.nxt.v.name, 'RandoGoronGiftCollected')
        self.assertEqual(native['RandoGoronGiftCollected'].data.cases[1].v.name, 'Event18')
        for events, gift in ((npc, 'RandoGoronTunicGive'), (native, 'Event18')):
            marker = events[gift].data.nxt.v
            self.assertEqual(marker.data.params.data['GameDataName'], flag)
            self.assertIs(marker.data.params.data['Value'], True)
            self.assertIsNot(events['RandoGoronTunicHas' if events is npc else 'RandoGoronGiftCollected'].data.cases[0].v, events[gift])

    def test_goron_collection_is_once_in_either_order_including_foreign_ap_reward(self):
        for actor in ('Item_Hookshot', 'Item_AP_123'):
            charts, config = self.patched(actor)
            native = {e.name: e for e in charts['Event/EventFlow/SageOfFire.bfevfl.zs'].events}
            npc = {e.name: e for e in charts[s.LINK_GORON_FLOW].events}
            starts = (native['RandoGoronGiftCollected'], npc['RandoGoronTunicHas'])
            for order in (starts, starts[::-1]):
                flags, rewards = {}, []
                for root in (*order, *order):
                    event = root
                    for _ in range(10):
                        if event.name in ('Event314', 'Event99'):
                            break
                        data = event.data
                        params = getattr(getattr(data, 'params', None), 'data', {}) or {}
                        if type(data).__name__ == 'SwitchEvent':
                            event = data.cases[0 if flags.get(params['GameDataName']) else 1].v
                            continue
                        if type(data).__name__ == 'SubFlowEvent':
                            rewards.append(params['ActorName'])
                        elif type(data).__name__ == 'ActionEvent':
                            flags[params['GameDataName']] = params['Value']
                        else:
                            self.fail('Unexpected gift event: ' + event.name)
                        event = data.nxt.v
                    else:
                        self.fail('Gift route did not terminate')
                self.assertEqual(rewards, [actor])
                self.assertTrue(flags[config['goron']['flag']])

    def test_zora_unclaimed_routes_ignore_tunic_ownership(self):
        charts, _ = self.patched()
        events = {e.name: e for e in charts[s.SAGE_OF_WATER_FLOW].events}
        self.assertEqual(events['Event137'].data.cases[1].v.name, 'Event271')
        self.assertEqual(events['Event127'].data.cases[1].v.name, 'Event286')
        entry = next(e for e in charts[s.SAGE_OF_WATER_FLOW].entry_points if e.name == s.KING_ZORA_GIFT_ENTRY)
        self.assertEqual(entry.main_event.v.data.nxt.v.name, 'Event242')
        self.assertEqual(events['Event242'].data.params.data['ActorName'], 'Item_Hookshot')
        self.assertEqual(events['Event242'].data.nxt.v.name, 'RandoCollected_Event242')

    def test_goron_progressive_fallback_runs_converter_before_receipt(self):
        from oot_rando.patching.progressive import token_actor
        charts, config = self.patched(token_actor('Progressive Hookshot', 0))
        events = {e.name: e for e in charts[s.LINK_GORON_FLOW].events}
        converter = events['RandoGoronTunicGive'].data.nxt.v
        self.assertEqual((converter.data.res_flowchart_name, converter.data.entry_point_name),
                         ('ActionGuide', 'RandoProgressive'))
        self.assertEqual(converter.data.nxt.v.data.params.data['GameDataName'], config['goron']['flag'])
