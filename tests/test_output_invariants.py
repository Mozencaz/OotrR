"""verify.output_invariants: checks read from the produced files only (no game needed here)."""
import _src_path  # noqa: F401
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zlib

from oot_rando.catalog.hashing import murmur3
from oot_rando.patching.randomize_kokiri import RESTBL
from oot_rando.randomizer import verify
from oot_rando.randomizer.verify import output_invariants

GAMEDATA = verify.GAMEDATA
FLOW = 'Event/EventFlow/Test.bfevfl.zs'
MAP = 'Banc/Test/Test.bcett.byml.zs'
NEW = 'Pack/Actor/Item_Soul_Test.pack.zs'


def restbl(sizes):
    entries = sorted((zlib.crc32(path.removesuffix('.zs').encode()), size) for path, size in sizes.items())
    return (b'RESTBL' + struct.pack('<IIII', 1, 160, len(entries), 0)
            + b''.join(struct.pack('<II', crc, size) for crc, size in entries))


def flow(*names):
    """Stand-in flow bytes: the GameData names its events use."""
    return json.dumps(sorted(names)).encode()


def parse(raw):
    events = [SimpleNamespace(data=SimpleNamespace(params=SimpleNamespace(data={'GameDataName': name})))
              for name in json.loads(raw)]
    return SimpleNamespace(flowchart=SimpleNamespace(events=events))


class FakeNup:
    def __init__(self, files):
        self.files = files

    def read(self, member):
        return self.files[member]


class OutputInvariantTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.seed = Path(self.temporary.name)
        game = {MAP: b'm' * 100, FLOW: flow('Known.Vanilla'), RESTBL: restbl({MAP: 4096, FLOW: 4096}),
                GAMEDATA: b'gamedata'}
        self.nup, self.members = FakeNup(game), {path: path for path in game}
        self.seed_files = {MAP: b'm' * 150, NEW: b'n' * 10, FLOW: flow('Known.Vanilla', 'RandoCheck.new'),
                           GAMEDATA: b'gamedata',
                           RESTBL: restbl({MAP: 4096 + 50, FLOW: 8192, NEW: 64})}
        self.flags = {'Known.Vanilla', 'RandoCheck.new'}
        for module, replacement in (('decompress', lambda raw, d: raw), ('parse_flow', parse)):
            patcher = mock.patch.object(verify, module, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        loader = mock.patch.object(verify.byml_codec, 'load', lambda raw: {'root': {'Data': {
            'Bool': [{'Hash': murmur3(name)} for name in self.flags]}}})
        loader.start()
        self.addCleanup(loader.stop)

    def run_checks(self):
        (self.seed / 'romfs').mkdir(exist_ok=True)
        for path, data in self.seed_files.items():
            (self.seed / 'romfs' / path).parent.mkdir(parents=True, exist_ok=True)
            (self.seed / 'romfs' / path).write_bytes(data)
        (self.seed / 'manifest.json').write_text(json.dumps({'files': {p: {} for p in self.seed_files}}),
                                                 encoding='utf-8')
        return output_invariants(self.nup, self.members, self.seed, {})

    def test_consistent_seed(self):
        self.assertEqual(self.run_checks(), {'grown_resources': 2, 'new_resources': 1, 'new_flag_references': 1})

    def test_short_allocation_is_refused(self):
        self.seed_files[RESTBL] = restbl({MAP: 4096 + 49, FLOW: 8192, NEW: 64})
        with self.assertRaisesRegex(ValueError, 'RESTBL allocation too small'):
            self.run_checks()

    def test_new_resource_without_entry_is_refused(self):
        self.seed_files[RESTBL] = restbl({MAP: 8192, FLOW: 8192})
        with self.assertRaisesRegex(ValueError, 'without a RESTBL entry'):
            self.run_checks()

    def test_undeclared_flag_is_refused(self):
        self.flags = {'Known.Vanilla'}
        with self.assertRaisesRegex(ValueError, 'does not declare: RandoCheck.new'):
            self.run_checks()

    def test_flags_already_used_by_the_game_are_not_checked(self):
        self.flags = {'RandoCheck.new'}   # the vanilla name may be missing (dead flow branch)
        self.assertEqual(self.run_checks()['new_flag_references'], 1)


if __name__ == '__main__':
    unittest.main()
