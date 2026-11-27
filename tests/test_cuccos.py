"""Cuccos to bring back: the cucco lady's pen, its logic module and her lines."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import struct
import unittest
from collections import Counter
from unittest import mock

from oot_rando.formats import byml_codec, msbt
from oot_rando.formats.inspect_resources import sarc
from oot_rando.logic import rando_options
from oot_rando.patching import cuccos
from oot_rando.formats.evfl_tools import params_by_event, parse_flow

NUP = os.environ.get('OOT_NUP')
FLOW_PATH = f'Event/EventFlow/{cuccos.FLOW}.bfevfl.zs'
ARCHIVE = 'Mals/USen.Product.110.sarc.zs'


def span(text):
    return cuccos.SPAN_ON + text + cuccos.SPAN_OFF


def message_file(texts):
    """Small UTF-8 MSBT holding ``{label: raw text}``."""
    buckets = 7
    slots = [[] for _ in range(buckets)]
    for index, name in enumerate(texts):
        slots[msbt.label_hash(name, buckets)].append((name, index))
    head, body = bytearray(struct.pack('<I', buckets)), bytearray()
    for slot in slots:
        head += struct.pack('<II', len(slot), 4 + 8 * buckets + len(body))
        for name, index in slot:
            body += bytes([len(name)]) + name.encode() + struct.pack('<I', index)
    raw_texts = [text + b'\0' for text in texts.values()]
    offsets, position = [], 4 + 4 * len(raw_texts)
    for text in raw_texts:
        offsets.append(position)
        position += len(text)
    txt = struct.pack(f'<{1 + len(offsets)}I', len(raw_texts), *offsets) + b''.join(raw_texts)
    out = bytearray(b'MsgStdBn' + bytes([0xff, 0xfe, 0, 0, 0, 3, 2, 0, 0, 0]) + bytes(14))
    for magic, raw in ((b'LBL1', bytes(head + body)), (b'TXT2', txt)):
        out += magic + struct.pack('<I', len(raw)) + bytes(8) + raw
        out += bytes([0xab]) * (-len(out) % 16)
    struct.pack_into('<I', out, 0x12, len(out))
    return bytes(out)


def her_lines(number=b'seven', extra=b''):
    return {
        'Talk_01': b'Only ' + span(b'\x0e\x02\x00\x01\x00&\x00!\x00Counter') + b' left!',
        'Talk_19': b'There should be ' + span(number) + b' cuccos here.',
        'Talk_21': b'Return all ' + span(number) + b' cuccos for a nice ' + span(b'empty bottle') + extra,
        'Talk_21_1': b'I have a total of ' + span(number) + b' cuccos.',
        'Talk_40': b'All ' + span(number) + b' of my cuccos are back!',
    }


def archive(texts):
    return byml_codec.build_sarc({cuccos.MESSAGE_FILE: message_file(texts), 'EventFlowMsg/Other.msbt': b'other'})


class OptionTests(unittest.TestCase):
    def test_range(self):
        option = rando_options.BY_NAME['chicken_count']
        self.assertEqual(option.default, cuccos.VANILLA_COUNT)
        self.assertEqual(option.supported_ints, tuple(range(1, 8)))
        self.assertEqual(option.experimental, tuple(range(1, 7)))      # 7 is the vanilla game
        self.assertEqual(rando_options.validate({'chicken_count': 3}, supported_only=True)['chicken_count'], 3)
        rando_options.validate({'chicken_count': 0})                   # AP range (0-7) still reads
        with self.assertRaises(ValueError):
            rando_options.validate({'chicken_count': 0}, supported_only=True)   # no reward without a cucco
        for bad in (8, -1, '3', True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rando_options.validate({'chicken_count': bad})
        for bad in (0, 8, '3', True, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cuccos.check_count(bad)

    def test_archipelago_option(self):
        from oot_rando.archipelago.bridge import ap_option_specs
        spec = next(s for s in ap_option_specs() if s['name'] == 'chicken_count')
        self.assertEqual((spec['kind'], spec['default'], spec['values']), ('int', 7, list(range(1, 8))))

    def test_settings_page(self):
        from oot_rando.gui import randomizer_gui as g
        self.assertIn('chicken_count', dict((title, names) for title, _, names in g.SETTING_GROUPS)['Minigames'])
        self.assertTrue(g.OPTION_TIPS['chicken_count'])


class MessageTests(unittest.TestCase):
    def test_numbers_become_the_count(self):
        patched, replaced = cuccos.patch_messages(archive(her_lines()), 3)
        self.assertEqual(replaced, 4)
        message = msbt.load(dict(sarc(patched))[cuccos.MESSAGE_FILE])
        expected = her_lines(b'3')
        for label, text in expected.items():
            self.assertEqual(message.get(label), text + b'\0', label)
        self.assertEqual(dict(sarc(patched))['EventFlowMsg/Other.msbt'], b'other')
        self.assertEqual(cuccos.patch_messages(archive(her_lines()), 7), (archive(her_lines()), 0))

    def test_language_forms(self):
        cases = ((b'sept ', b'3 '), ('7只'.encode(), '3只'.encode()), (b'7 cucos', b'3 cucos'),
                 ('семерых'.encode(), b'3'), ('siódemkę'.encode(), b'3'),
                 (b'7\x0e\x00\x00\x00\x00\x07\x00\x01\x00\x03\x00' + 'わ羽'.encode(),
                  b'3\x0e\x00\x00\x00\x00\x07\x00\x01\x00\x03\x00' + 'わ羽'.encode()))
        for before, after in cases:
            with self.subTest(before=before):
                patched, _ = cuccos.patch_message_file(message_file(her_lines(before)), 3)
                self.assertEqual(msbt.load(patched).get('Talk_40'), her_lines(after)['Talk_40'] + b'\0')
        # Not the count: other words, longer numbers, spans without a number.
        for other in (b'Todas ', b'77', b'seventy', b'all'):
            with self.subTest(other=other), self.assertRaises(ValueError):
                cuccos.patch_message_file(message_file(her_lines(other)), 3)

    def test_two_numbers_in_one_line(self):
        # Polish: "siedem" and "siódemkę" in the same request.
        texts = her_lines(extra=b' ' + span('siódemkę'.encode()) + b'?')
        patched, replaced = cuccos.patch_message_file(message_file(texts), 5)
        self.assertEqual(replaced, 5)
        self.assertTrue(msbt.load(patched).get('Talk_21').endswith(span(b'5') + b'?\0'))

    def test_missing_lines_are_refused(self):
        texts = her_lines()
        del texts['Talk_40']
        with self.assertRaises(ValueError):
            cuccos.patch_message_file(message_file(texts), 3)
        with self.assertRaises(ValueError):
            cuccos.patch_messages(byml_codec.build_sarc({'EventFlowMsg/Other.msbt': b'other'}), 3)


class SeedCheckTests(unittest.TestCase):
    """Verification (verify.py) of the files a seed holds for its count."""

    def seed(self, count, skip=None, files=None, lines=None):
        vanilla = {cuccos.LOGIC_MODULE: b'logic', FLOW_PATH: b'flow', ARCHIVE: archive(her_lines())}
        produced = {cuccos.LOGIC_MODULE: b'logic' + bytes([count]), FLOW_PATH: b'flow',
                    ARCHIVE: archive(her_lines(lines if lines is not None else str(count).encode()))}
        manifest = {'settings': {'full': {'chicken_count': count}}, 'skips': {} if skip is None else {'cuccos': skip},
                    'files': dict.fromkeys(produced if files is None else files)}
        return manifest, list(vanilla), vanilla.__getitem__, produced.__getitem__

    def check(self, manifest, members, original, produced):
        with mock.patch.object(cuccos, 'patch_logic', lambda raw, count: raw + bytes([count])), \
                mock.patch.object(cuccos, 'flow_values', lambda raw: dict.fromkeys(cuccos.FLOW_EVENTS, 3)):
            return cuccos.check_seed(manifest, members, original, produced)

    def test_count_and_lines(self):
        self.assertEqual(self.check(*self.seed(3, skip=3)), {'cuccos': 3, 'cucco_lines': 4})

    def test_vanilla_seed_has_nothing_to_check(self):
        self.assertEqual(self.check(*self.seed(7, files=())), {})

    def test_differences_are_refused(self):
        for name, seed in (('skip missing', self.seed(3)), ('skip differs', self.seed(3, skip=4)),
                           ('file missing', self.seed(3, skip=3, files=(FLOW_PATH, ARCHIVE))),
                           ('vanilla lines', self.seed(3, skip=3, lines=b'seven')),
                           ('flow count', self.seed(4, skip=4))):
            with self.subTest(name), self.assertRaises(ValueError):
                self.check(*seed)


class LogicRuleTests(unittest.TestCase):
    """AP's rule: "is_child and at_day and (can_break_crate or chicken_count < 7)"."""

    def test_fewer_cuccos_do_not_need_the_crate(self):
        from oot_rando.logic.rules import Logic
        from oot_rando.logic.world import World

        class Day:
            tod = {'adult': True, 'child': True}
        data = World()
        # One-hit bonks: rolling into the crate is no longer a way to break it.
        rules = {count: dict(Logic(data, {'open_forest': 'closed_deku', 'deadly_bonks': 'ohko',
                                          'chicken_count': count}).location_rules)['Kak Anju as Child'][0][1]
                 for count in (7, 6, 1)}
        self.assertFalse(rules[7](Day, {}, 'child'))
        self.assertTrue(rules[7](Day, {'Bomb Bag': 1}, 'child'))
        self.assertTrue(rules[6](Day, {}, 'child'))
        self.assertTrue(rules[1](Day, {}, 'child'))
        self.assertFalse(rules[1](Day, {}, 'adult'))


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.extra_sources import event_paths
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        try:
            d, m = dictionaries(nup), effective_members(nup)
            cls.flows = {p: decompress(nup.read(m[p]), d) for p in event_paths(m, cuccos.FLOW)}
            cls.logic = nup.read(m[cuccos.LOGIC_MODULE])
            cls.archives = {p: decompress(nup.read(m[p]), d) for p in cuccos.message_paths(m)}
        finally:
            nup.stream.close()

    def test_flow(self):
        self.assertEqual(list(self.flows), [FLOW_PATH])
        raw = self.flows[FLOW_PATH]
        self.assertIs(cuccos.patch_flow(raw, 7), raw)
        self.assertEqual(cuccos.flow_values(raw), {'Event3': 7, 'Event82': 7})
        before = params_by_event(parse_flow(raw))
        for count in range(1, 7):
            patched = cuccos.patch_flow(raw, count)
            after = params_by_event(parse_flow(patched))
            self.assertEqual({k for k in before if before[k] != after[k]}, {'Event3', 'Event82'})
            self.assertEqual(cuccos.flow_values(patched), {'Event3': count, 'Event82': count})
            with self.assertRaises(ValueError):
                cuccos.patch_flow(patched, count)

    def test_logic_module(self):
        import ainb
        raw = self.logic
        self.assertIs(cuccos.patch_logic(raw, 7), raw)
        for count in range(1, 7):
            patched = cuccos.patch_logic(raw, count)
            self.assertEqual(len(patched), len(raw))
            # Int_A, the multi-source output index and two output flags.
            self.assertEqual(sum(a != b for a, b in zip(raw, patched)), 4)
            nodes = ainb.AINB.from_binary(patched).as_dict()['Nodes']
            self.assertEqual(nodes[17]['Parameters']['Inputs']['Int'][0]['Default Value'], count - 1)
            self.assertEqual([(s['Node Index'], s['Output Index'])
                              for s in nodes[18]['Parameters']['Inputs']['Bool'][0]['Sources']], [(73, 1), (17, 1)])
            self.assertEqual([(s['Node Index'], s['Output Index'])
                              for s in nodes[19]['Parameters']['Inputs']['Bool'][0]['Sources']], [(73, 1), (17, 0)])
            with self.assertRaises(ValueError):
                cuccos.patch_logic(patched, count)

    def test_lines_in_every_language(self):
        self.assertEqual(len(self.archives), 16)
        replaced = Counter()
        for path, raw in self.archives.items():
            message = msbt.load(dict(sarc(raw))[cuccos.MESSAGE_FILE])
            self.assertEqual(msbt.dump(message), dict(sarc(raw))[cuccos.MESSAGE_FILE])
            patched, replaced[path.split('/')[1][:4]] = cuccos.patch_messages(raw, 3)
            before, after = dict(sarc(raw)), dict(sarc(patched))
            self.assertEqual({k for k in before if before[k] != after[k]}, {cuccos.MESSAGE_FILE})
            old, new = msbt.load(before[cuccos.MESSAGE_FILE]), msbt.load(after[cuccos.MESSAGE_FILE])
            # Portuguese's reward line (Talk_40) says "Todas" (all): no number to replace.
            expected = set(cuccos.LINES) - ({'Talk_40'} if path.split('/')[1].startswith('USpt') else set())
            self.assertEqual({label for label in old.labels if old.get(label) != new.get(label)}, expected)
        # Every request and reward line; Polish names the count twice in two requests,
        # Portuguese says "Todas" (all) in the reward line.
        self.assertEqual(replaced, Counter({lang: 4 for lang in (
            'CNzh', 'EUde', 'EUen', 'EUes', 'EUfr', 'EUit', 'EUnl', 'EUru', 'JPja', 'KRko', 'TWzh', 'USen', 'USes',
            'USfr')}) + Counter({'EUpl': 6, 'USpt': 3}))

    def test_seed_check(self):
        files = {cuccos.LOGIC_MODULE: cuccos.patch_logic(self.logic, 4),
                 **{p: cuccos.patch_flow(r, 4) for p, r in self.flows.items()},
                 **{p: cuccos.patch_messages(r, 4)[0] for p, r in self.archives.items()}}
        vanilla = {cuccos.LOGIC_MODULE: self.logic, **self.flows, **self.archives}
        manifest = {'settings': {'full': {'chicken_count': 4}}, 'skips': {'cuccos': 4}, 'files': dict.fromkeys(files)}
        self.assertEqual(cuccos.check_seed(manifest, list(vanilla), vanilla.__getitem__, files.__getitem__),
                         {'cuccos': 4, 'cucco_lines': 65})
        with self.assertRaises(ValueError):
            cuccos.check_seed(manifest, list(vanilla), vanilla.__getitem__, dict(files, **{
                cuccos.LOGIC_MODULE: self.logic}).__getitem__)


if __name__ == '__main__':
    unittest.main()
