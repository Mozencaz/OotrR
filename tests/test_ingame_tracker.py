"""In-game tracker: the seed file format, its export from a seed and its installation. NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import hashlib
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oot_rando.randomizer.randomizer_core import Settings, generate
from oot_rando.randomizer.randomizer_services import generate_in_mods, read_artifact
from oot_rando.paths import resource
from oot_rando.tracker import ingame_bundle, ingame_format as fmt
from test_randomizer_services import ServiceTests

NUP = os.environ.get('OOT_NUP')
REAL_SEED = Path(r'C:\switch 2 roms\Ryuchii - latest\user\load\0400486024DEC000\OoT_Randomizer_76069ecc4740cec6')
FAKE_MODULE = b'NSO0 fake module'


def sample_file():
    return fmt.build('0123456789abcdef', 1220450581, 3488204275,
                     [('Kokiri Forest', [(fmt.KIND_BOOL, 1740986978), (fmt.KIND_BOOL64, 2056926167552020049)]),
                      ('Deku Tree', [(fmt.KIND_BOOL, 7)])],
                     [('Bomb Bag', [(2525649529, 3), (2999220442, 2)]), ('Ice Arrows', [(1552887961, 1)])],
                     [{'name': 'Forest Temple', 'flags': fmt.KEY_SMALL | fmt.KEY_BOSS, 'total': 5,
                       'found': 11, 'held': 12, 'ring': 13, 'boss': 14}])


class FormatTests(unittest.TestCase):
    def test_roundtrip(self):
        parsed = fmt.parse(sample_file())
        self.assertEqual(parsed['seed_id'], '0123456789abcdef')
        self.assertEqual((parsed['seed_marker'], parsed['goal_marker']), (1220450581, 3488204275))
        self.assertEqual(parsed['regions'], [('Kokiri Forest', [(1, 1740986978), (2, 2056926167552020049)]),
                                             ('Deku Tree', [(1, 7)])])
        self.assertEqual(parsed['items'], [('Bomb Bag', [(2525649529, 3), (2999220442, 2)]),
                                           ('Ice Arrows', [(1552887961, 1)])])
        self.assertEqual(parsed['keys'][0]['name'], 'Forest Temple')
        self.assertEqual(fmt.build(**parsed), sample_file())

    def test_empty_seed_roundtrips(self):
        data = fmt.build('', 0, 0, [], [], [])
        self.assertEqual(len(data), fmt.HEADER.size + 4)
        self.assertEqual(fmt.parse(data)['regions'], [])

    def test_header_layout_is_the_documented_one(self):
        data = sample_file()
        self.assertEqual(data[:4], b'RTRK')
        self.assertEqual(struct.unpack_from('<HHIII', data, 4), (1, 72, len(data), 1220450581, 3488204275))

    def test_malformed_files_are_refused(self):
        data = bytearray(sample_file())

        def changed(offset, fmt_, value):
            copy = bytearray(data)
            struct.pack_into(fmt_, copy, offset, value)
            return bytes(copy)
        broken = {
            'magic': b'XXXX' + bytes(data[4:]),
            'version': changed(4, '<H', 2),
            'header size': changed(6, '<H', 64),
            'truncated': bytes(data[:-1]),
            'longer': bytes(data) + b'\0',
            'empty': b'',
            'region table outside': changed(32, '<I', len(data) - 4),
            'check table outside': changed(44, '<I', 1 << 20),
            'string table outside': changed(28, '<I', 1 << 20),
            'seed id offset outside strings': changed(20, '<I', 1 << 16),
        }
        for name, content in broken.items():
            with self.subTest(name), self.assertRaises(ValueError):
                fmt.parse(content)

    def test_more_regions_or_dungeons_than_the_module_shows_are_refused(self):
        with self.assertRaises(ValueError):
            fmt.build('x', 0, 0, [(f'r{i}', []) for i in range(fmt.MAX_REGIONS + 1)], [], [])
        with self.assertRaises(ValueError):
            fmt.build('x', 0, 0, [], [], [{'name': 'd', 'flags': 0, 'total': 0, 'found': 0, 'held': 0, 'ring': 0,
                                           'boss': 0}] * (fmt.MAX_KEY_ROWS + 1))
        fmt.build('x', 0, 0, [(f'r{i}', []) for i in range(fmt.MAX_REGIONS)], [], [])

    def test_a_region_pointing_past_the_checks_is_refused(self):
        data = bytearray(sample_file())
        regions_offset = struct.unpack_from('<I', data, 32)[0]
        struct.pack_into('<I', data, regions_offset + 8, 99)
        with self.assertRaises(ValueError):
            fmt.parse(bytes(data))

    def test_unterminated_string_is_refused(self):
        data = bytearray(sample_file())
        size = struct.unpack_from('<I', data, 28)[0]
        data[fmt.HEADER.size + size - 1] = ord('x')
        with self.assertRaises(ValueError):
            fmt.parse(bytes(data))

    def test_values_that_do_not_fit_are_refused(self):
        with self.assertRaises(ValueError):
            fmt.build('x', 1 << 32, 0, [], [], [])
        with self.assertRaises(ValueError):
            fmt.build('x', 0, 0, [('r', [(fmt.KIND_BOOL, 1 << 64)])], [], [])
        with self.assertRaises(ValueError):
            fmt.build('x', 0, 0, [], [('Bow', [(1, 1 << 16)])], [])


def synthetic_seed():
    checks = [{'id': 'a', 'region': 'Kokiri Forest'}, {'id': 'b', 'region': 'Deku Tree'},
              {'id': 'c', 'region': 'Kokiri Forest'}, {'id': 'd', 'region': 'Lost Woods'},
              {'id': 'e', 'region': 'Deku Tree'}]
    secret = 'Ice Arrows'
    rows = {'a': {'collection': {'type': 'bool', 'hash': '100'}, 'reward': secret, 'item': secret, 'actor': 'Item_X'},
            'b': {'collection': {'type': 'bool64', 'hash': '18446744073709551615'}, 'reward': 'Bomb Bag'},
            'c': {'collection': None, 'reward': 'Boss Key (Forest Temple)'},
            'd': {'collection': None},
            'e': {'collection': {'type': 'bool', 'hash': '200'}}}
    tracking = {'seed_marker': '4000000000', 'checks': rows,
                'inventory': [{'item': 'Bow', 'hash': '11', 'count': 1}, {'item': 'Bow', 'hash': '12', 'count': 2},
                              {'item': 'Boomerang', 'hash': '13', 'count': 1}],
                'keys': [{'folder': 'ForestTemple', 'dungeon': 'Forest Temple',
                          'small': {'total': 5, 'found': '21', 'held': '22', 'ring': '23', 'all': False},
                          'boss': {'hash': '24', 'all': True}},
                         {'folder': 'Well', 'dungeon': 'Bottom of the Well',
                          'small': {'total': 3, 'found': '31', 'held': '32', 'ring': None, 'all': True}, 'boss': None}]}
    return {'seed_id': 'f' * 64}, checks, tracking


class ExportTests(unittest.TestCase):
    def test_groups_observable_checks_by_region_in_catalogue_order(self):
        manifest, checks, tracking = synthetic_seed()
        parsed = fmt.parse(ingame_bundle.seed_file(manifest, checks, tracking))
        self.assertEqual(parsed['seed_id'], 'f' * 16)
        self.assertEqual(parsed['seed_marker'], 4000000000)
        self.assertEqual(parsed['goal_marker'], 0)
        self.assertEqual(parsed['regions'], [('Kokiri Forest', [(fmt.KIND_BOOL, 100)]),
                                             ('Deku Tree', [(fmt.KIND_BOOL64, (1 << 64) - 1), (fmt.KIND_BOOL, 200)])])

    def test_goal_marker_is_written_when_the_seed_has_one(self):
        manifest, checks, tracking = synthetic_seed()
        tracking['goal_marker'] = '77'
        self.assertEqual(fmt.parse(ingame_bundle.seed_file(manifest, checks, tracking))['goal_marker'], 77)

    def test_items_keep_every_rule_of_an_item(self):
        parsed = fmt.parse(ingame_bundle.seed_file(*synthetic_seed()))
        self.assertEqual(parsed['items'], [('Bow', [(11, 1), (12, 2)]), ('Boomerang', [(13, 1)])])

    def test_dungeon_keys(self):
        keys = fmt.parse(ingame_bundle.seed_file(*synthetic_seed()))['keys']
        self.assertEqual(keys[0], {'name': 'Forest Temple', 'flags': fmt.KEY_SMALL | fmt.KEY_BOSS | fmt.KEY_BOSS_ALL,
                                   'total': 5, 'found': 21, 'held': 22, 'ring': 23, 'boss': 24})
        self.assertEqual(keys[1], {'name': 'Bottom of the Well', 'flags': fmt.KEY_SMALL | fmt.KEY_SMALL_ALL,
                                   'total': 3, 'found': 31, 'held': 32, 'ring': 0, 'boss': 0})

    def test_a_seed_without_keys_data_still_exports(self):
        manifest, checks, tracking = synthetic_seed()
        del tracking['keys']
        self.assertEqual(fmt.parse(ingame_bundle.seed_file(manifest, checks, tracking))['keys'], [])

    def test_no_reward_or_placement_reaches_the_file(self):
        manifest, checks, tracking = synthetic_seed()
        data = ingame_bundle.seed_file(manifest, checks, tracking)
        for secret in (b'Ice Arrows', b'Boss Key', b'Item_X', b'reward', b'Bomb Bag'):
            self.assertNotIn(secret, data)

    @unittest.skipUnless(REAL_SEED.is_dir(), 'real seed absent')
    def test_real_seed_matches_what_the_desktop_tracker_observes(self):
        manifest = json.loads((REAL_SEED / 'manifest.json').read_text(encoding='utf-8'))
        checks = json.loads((REAL_SEED / 'checks.json').read_text(encoding='utf-8'))['checks']
        tracking = json.loads((REAL_SEED / 'tracking.json').read_text(encoding='utf-8'))
        parsed = fmt.parse(ingame_bundle.seed_file(manifest, checks, tracking))
        observable = [t for t in tracking['checks'].values() if t['collection']]
        self.assertEqual(sum(len(c) for _, c in parsed['regions']), len(observable))
        by_region = {}
        for check in checks:
            if tracking['checks'][check['id']]['collection']:
                by_region[check['region']] = by_region.get(check['region'], 0) + 1
        self.assertEqual({name: len(c) for name, c in parsed['regions']}, by_region)
        self.assertEqual(parsed['seed_marker'], int(tracking['seed_marker']))
        self.assertEqual(parsed['goal_marker'], int(tracking['goal_marker']))
        self.assertEqual(sum(len(rules) for _, rules in parsed['items']), len(tracking['inventory']))
        self.assertEqual({kind for _, c in parsed['regions'] for kind, _ in c}, {fmt.KIND_BOOL, fmt.KIND_BOOL64})
        data = ingame_bundle.seed_file(manifest, checks, tracking)
        rewards = {r['reward'] for r in tracking['checks'].values() if r['reward']} - {name for name, _ in parsed['items']}
        self.assertTrue(rewards)
        stored = set(data.split(b'\0'))
        self.assertFalse([r for r in rewards if r.encode() in stored])


class ShippedModuleTests(unittest.TestCase):
    def test_the_module_is_an_nso_with_the_checksum_its_source_note_gives(self):
        module = ingame_bundle.module_binary()
        self.assertEqual(module[:4], b'NSO0')
        note = resource('resources', 'ingame_tracker', 'SOURCE.md').read_text(encoding='utf-8')
        self.assertIn(hashlib.sha256(module).hexdigest(), note)
        self.assertIn(f'{len(module):,} bytes', note)

    def test_the_module_comes_with_its_licence_and_source(self):
        folder = resource('resources', 'ingame_tracker')
        self.assertIn('GNU GENERAL PUBLIC LICENSE', (folder / 'LICENSE').read_text(encoding='utf-8'))
        self.assertIn('https://github.com/waze3174/ootr-ingame-tracker', (folder / 'SOURCE.md').read_text(encoding='utf-8'))


class InstallTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(ingame_bundle, 'module_binary', return_value=FAKE_MODULE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def attached_artifact(self, root):
        helper = ServiceTests('make_artifact')
        helper.make_artifact(root, 'tracked')
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        _, checks, tracking = synthetic_seed()
        files, exefs = {}, {}
        ingame_bundle.attach(manifest, files, exefs, checks, tracking)
        for path, data in files.items():
            (root / 'romfs' / path).parent.mkdir(parents=True, exist_ok=True)
            (root / 'romfs' / path).write_bytes(data)
        (root / 'exefs').mkdir()
        for path, data in exefs.items():
            (root / 'exefs' / path).write_bytes(data)
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return manifest

    def test_attach_lists_both_files_in_the_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.attached_artifact(Path(directory) / 'seed')
            data = (Path(directory) / 'seed' / 'romfs' / ingame_bundle.SEED_FILE).read_bytes()
            self.assertEqual(manifest['files'][ingame_bundle.SEED_FILE],
                             {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            self.assertEqual(list(manifest['files']), sorted(manifest['files']))
            self.assertEqual(manifest['exefs'], {'subsdk7': {'size': len(FAKE_MODULE),
                                                              'sha256': hashlib.sha256(FAKE_MODULE).hexdigest()}})
            read_artifact(Path(directory) / 'seed')

    def test_verification_catches_a_modified_seed_file_or_module(self):
        for relative in (Path('romfs') / ingame_bundle.SEED_FILE, Path('exefs') / 'subsdk7'):
            with self.subTest(relative.as_posix()), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'seed'
                self.attached_artifact(root)
                (root / relative).write_bytes((root / relative).read_bytes() + b'!')
                with self.assertRaisesRegex(ValueError, 'Modified or incomplete'):
                    read_artifact(root)

    def test_verification_refuses_an_unknown_code_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'seed'
            manifest = self.attached_artifact(root)
            manifest['exefs']['main'] = manifest['exefs']['subsdk7']
            (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unknown code module'):
                read_artifact(root)

    def test_seeds_without_the_tracker_still_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'seed'
            ServiceTests('make_artifact').make_artifact(root, 'plain')
            self.assertNotIn('exefs', read_artifact(root)[0])

    def test_install_passes_the_option_to_the_generator(self):
        received = []

        def fake_generate(nup, output, settings, progress, **options):
            received.append(options)
            ServiceTests('make_artifact').make_artifact(output, settings.seed)
        with tempfile.TemporaryDirectory() as directory:
            title = Path(directory) / '0400486024DEC000'
            title.mkdir()
            generate_in_mods('game.nup', title, Settings('on'), archive=Path(directory) / 'a', generate=fake_generate)
            generate_in_mods('game.nup', title, Settings('off'), archive=Path(directory) / 'a', generate=fake_generate,
                             ingame_tracker=False)
        self.assertEqual(received, [{}, {'ingame_tracker': False}])


@unittest.skipUnless(NUP, 'OOT_NUP absent')
class GenerateTests(unittest.TestCase):
    def generate_seed(self, **options):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        output = Path(directory.name) / 'seed'
        manifest = generate(NUP, output, Settings('tracker-test', randomize_chests=False, pool=[]), **options)
        return output, manifest

    def test_generated_seed_carries_the_tracker(self):
        output, manifest = self.generate_seed()
        read_artifact(output)
        data = (output / 'romfs' / ingame_bundle.SEED_FILE).read_bytes()
        self.assertIn(ingame_bundle.SEED_FILE, manifest['files'])
        parsed = fmt.parse(data)
        tracking = json.loads((output / 'tracking.json').read_text(encoding='utf-8'))
        self.assertEqual(parsed['seed_marker'], int(tracking['seed_marker']))
        module = (output / 'exefs' / 'subsdk7').read_bytes()
        self.assertEqual(module, ingame_bundle.module_binary())
        self.assertEqual(manifest['exefs']['subsdk7']['sha256'], hashlib.sha256(module).hexdigest())

    def test_option_leaves_the_tracker_out(self):
        output, manifest = self.generate_seed(ingame_tracker=False)
        read_artifact(output)
        self.assertNotIn(ingame_bundle.SEED_FILE, manifest['files'])
        self.assertNotIn('exefs', manifest)
        self.assertFalse((output / 'exefs').exists())
        self.assertFalse((output / 'romfs' / 'RandoTracker').exists())


if __name__ == '__main__':
    unittest.main()
