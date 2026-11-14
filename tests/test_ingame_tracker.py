"""In-game tracker: the seed file format, its export from a seed and its installation. NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import contextlib
import hashlib
import io
import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oot_rando.randomizer.randomizer_core import Settings, generate
from oot_rando.randomizer.randomizer_services import (generate_in_mods, read_artifact, update_ingame_tracker,
                                                      update_ingame_trackers)
from oot_rando.__main__ import main as command_line
from oot_rando.paths import resource
from oot_rando.tracker import ingame_bundle, ingame_format as fmt, ingame_icons
from oot_rando.tracker.check_labels import check_labels
from test_randomizer_services import ServiceTests

NUP = os.environ.get('OOT_NUP')
REAL_SEED = Path(r'C:\switch 2 roms\Ryuchii - latest\user\load\0400486024DEC000\OoT_Randomizer_76069ecc4740cec6')
FAKE_MODULE = b'NSO0 fake module'
FAKE_ICONS = b'RTIC fake icons'
REPOSITORY = Path(__file__).resolve().parents[1]
LAYOUT, SWIZZLE = bytes([4, 0, 0, 0, 0, 0, 0, 0]), bytes([2, 3, 4, 5])


def sample_file():
    return fmt.build('0123456789abcdef', 1220450581, 3488204275,
                     [('Kokiri Forest', [(fmt.KIND_BOOL, 1740986978, "Mido's House Chest"),
                                         (fmt.KIND_BOOL64, 2056926167552020049, 'GS Kokiri Bean Patch')]),
                      ('Deku Tree', [(fmt.KIND_BOOL, 7, 'Deku Tree Map Chest')])],
                     [('Bomb Bag', [(2525649529, 3), (2999220442, 2)]), ('Ice Arrows', [(1552887961, 1)])],
                     [{'name': 'Forest Temple', 'flags': fmt.KEY_SMALL | fmt.KEY_BOSS, 'total': 5,
                       'found': 11, 'held': 12, 'ring': 13, 'boss': 14}])


class FormatTests(unittest.TestCase):
    def test_roundtrip(self):
        parsed = fmt.parse(sample_file())
        self.assertEqual(parsed['seed_id'], '0123456789abcdef')
        self.assertEqual((parsed['seed_marker'], parsed['goal_marker']), (1220450581, 3488204275))
        self.assertEqual(parsed['regions'], [('Kokiri Forest', [(1, 1740986978, "Mido's House Chest"),
                                                               (2, 2056926167552020049, 'GS Kokiri Bean Patch')]),
                                             ('Deku Tree', [(1, 7, 'Deku Tree Map Chest')])])
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
        self.assertEqual(struct.unpack_from('<HHIII', data, 4), (2, 72, len(data), 1220450581, 3488204275))

    def test_version_1_files_still_read_with_unnamed_checks(self):
        data = bytearray(sample_file())
        struct.pack_into('<H', data, 4, 1)
        checks_offset, check_count = struct.unpack_from('<II', data, 40)
        for index in range(check_count):
            struct.pack_into('<I', data, checks_offset + index * fmt.CHECK.size + 12, 0)   # reserved in version 1
        parsed = fmt.parse(bytes(data))
        self.assertEqual(parsed['regions'][0][1], [(1, 1740986978, ''), (2, 2056926167552020049, '')])

    def test_a_check_name_outside_the_strings_is_refused(self):
        data = bytearray(sample_file())
        checks_offset, strings_size = struct.unpack_from('<I', data, 40)[0], struct.unpack_from('<I', data, 28)[0]
        struct.pack_into('<I', data, checks_offset + 12, strings_size)
        with self.assertRaises(ValueError):
            fmt.parse(bytes(data))

    def test_malformed_files_are_refused(self):
        data = bytearray(sample_file())

        def changed(offset, fmt_, value):
            copy = bytearray(data)
            struct.pack_into(fmt_, copy, offset, value)
            return bytes(copy)
        broken = {
            'magic': b'XXXX' + bytes(data[4:]),
            'version': changed(4, '<H', 3),
            'version 0': changed(4, '<H', 0),
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
            fmt.build('x', 0, 0, [('r', [(fmt.KIND_BOOL, 1 << 64, 'c')])], [], [])
        with self.assertRaises(ValueError):
            fmt.build('x', 0, 0, [], [('Bow', [(1, 1 << 16)])], [])


def synthetic_seed():
    checks = [{'id': 'a', 'region': 'Kokiri Forest', 'name': 'Mido Chest'},
              {'id': 'b', 'region': 'Deku Tree', 'name': 'DekuTree#123', 'category': 'world_chests'},
              {'id': 'c', 'region': 'Kokiri Forest', 'name': 'Shop Item 1'},
              {'id': 'd', 'region': 'Lost Woods', 'name': 'Skull Kid'},
              {'id': 'e', 'region': 'Deku Tree', 'name': 'Slingshot Chest'}]
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
        self.assertEqual(parsed['regions'], [('Kokiri Forest', [(fmt.KIND_BOOL, 100, 'Mido Chest')]),
                                             ('Deku Tree', [(fmt.KIND_BOOL64, (1 << 64) - 1, 'Chest 1'),
                                                            (fmt.KIND_BOOL, 200, 'Slingshot Chest')])])

    def test_check_names_are_the_ones_the_window_tracker_shows(self):
        manifest, checks, tracking = synthetic_seed()
        parsed = fmt.parse(ingame_bundle.seed_file(manifest, checks, tracking))
        labels = check_labels(checks)
        exported = [name for _, region in parsed['regions'] for _, _, name in region]
        self.assertEqual(exported, [labels[c['id']] for c in checks if tracking['checks'][c['id']]['collection']])
        self.assertEqual(labels['b'], 'Chest 1')   # a world chest: numbered in its region, as in the window
        self.assertEqual(labels['e'], 'Slingshot Chest')

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
        self.assertEqual({kind for _, c in parsed['regions'] for kind, _, _ in c}, {fmt.KIND_BOOL, fmt.KIND_BOOL64})
        data = ingame_bundle.seed_file(manifest, checks, tracking)
        rewards = {r['reward'] for r in tracking['checks'].values() if r['reward']} - {name for name, _ in parsed['items']}
        self.assertTrue(rewards)
        stored = set(data.split(b'\0'))
        self.assertFalse([r for r in rewards if r.encode() in stored])


def synthetic_bntx(width=8, height=8, texture_format=0x2D01, tile_mode=0, levels=1, data=None):
    """A BNTX of one texture, made here (no game data): its BRTI at 0x20, the levels' table at 0x100, the
    levels from 0x200, each as long as the first (``data``)."""
    data = bytes(7 * i % 256 for i in range(-(-width // 4) * -(-height // 4) * 16)) if data is None else data
    out = bytearray(0x200 + len(data) * levels)
    out[0:4], out[0x20:0x24] = b'BNTX', b'BRTI'
    struct.pack_into('<H', out, 0x20 + 0x12, tile_mode)
    struct.pack_into('<H', out, 0x20 + 0x16, levels)
    struct.pack_into('<I', out, 0x20 + 0x1C, texture_format)
    struct.pack_into('<II', out, 0x20 + 0x24, width, height)
    out[0x20 + 0x34:0x20 + 0x3C] = LAYOUT
    struct.pack_into('<I', out, 0x20 + 0x50, len(data) * levels)
    out[0x20 + 0x58:0x20 + 0x5C] = SWIZZLE
    struct.pack_into('<Q', out, 0x20 + 0x70, 0x100)
    for level in range(levels):
        at = 0x200 + level * len(data)
        struct.pack_into('<Q', out, 0x100 + 8 * level, at)
        out[at:at + len(data)] = data if level == 0 else b'\xEE' * len(data)
    return bytes(out)


def missing_picture(name):
    raise KeyError(name)


class IconTests(unittest.TestCase):
    """icons.bin: the game's pictures as their BNTX stores them, checked as the module checks them."""
    @staticmethod
    def icons():
        return [('Bow', ingame_icons.texture(synthetic_bntx())),
                ('Progressive Hookshot', ingame_icons.texture(synthetic_bntx(12, 4, 0x2D06, data=bytes(range(56)))))]

    def test_a_picture_is_copied_as_the_game_stores_it(self):
        data = bytes(range(64))
        for levels in (1, 3):
            with self.subTest(levels=levels):
                self.assertEqual(ingame_icons.texture(synthetic_bntx(data=data, levels=levels)),
                                 {'width': 8, 'height': 8, 'format': 0x2D01, 'layout': LAYOUT, 'swizzle': SWIZZLE,
                                  'data': data})

    def test_pictures_other_than_astc_in_block_linear_layout_are_refused(self):
        good = synthetic_bntx()
        for what, bntx in [('magic', b'XNTX' + good[4:]), ('two textures', good + b'BRTI'),
                           ('RGBA8', synthetic_bntx(texture_format=0x0B01)), ('linear', synthetic_bntx(tile_mode=1)),
                           ('truncated', good[:-1])]:
            with self.subTest(what), self.assertRaises(ValueError):
                ingame_icons.texture(bntx)

    def test_the_file_reads_back_with_its_pictures_aligned(self):
        data = ingame_icons.build(self.icons())
        self.assertEqual(data, ingame_icons.build(self.icons()))
        self.assertEqual(ingame_icons.parse(data), self.icons())
        self.assertEqual(ingame_icons.HEADER.unpack_from(data), (b'RTIC', 1, 32, 288, 2, 32, 64, 160, 0))
        self.assertEqual([ingame_icons.ENTRY.unpack_from(data, 32 + 64 * i)[3] for i in range(2)], [160, 224])
        with self.assertRaises(ValueError):
            ingame_icons.build([('An item whose name is much too long', self.icons()[0][1])])
        with self.assertRaises(ValueError):
            ingame_icons.build(self.icons()[:1] * 31)

    def test_damaged_files_are_refused(self):
        good = ingame_icons.build(self.icons())

        def changed(offset, value, layout='<I'):
            data = bytearray(good)
            struct.pack_into(layout, data, offset, value)
            return bytes(data)
        for what, data in [('magic', b'XTIC' + good[4:]), ('version', changed(4, 2, '<H')), ('size', good + bytes(16)),
                           ('count', changed(12, 31)), ('misaligned', changed(32 + 40, 168)),
                           ('past the end', changed(96 + 40, 272)), ('swizzle', changed(32 + 56, 6, '<B')),
                           ('format', changed(32 + 60, 0x2D02)), ('one item twice', good[:96] + good[32:64] + good[128:]),
                           ('truncated', good[:100])]:
            with self.subTest(what), self.assertRaises(ValueError):
                ingame_icons.parse(data)

    def test_the_grids_icons_carry_the_names_the_module_knows(self):
        grid = (REPOSITORY / 'ingame_tracker' / 'src' / 'grid.c').read_text(encoding='utf-8')
        icons = ingame_icons.grid_icons()
        self.assertLessEqual(len(icons), ingame_icons.MAX_ICONS)
        for item, _ in icons:
            self.assertIn('{ "%s",' % item, grid)
        self.assertIn(('Megaton Hammer', 'Item_Hammer_PouchIcon'), icons)

    def test_the_icons_the_game_has_in_the_grids_order(self):
        asked = []

        def read_picture(name):
            asked.append(name)
            if name == 'Weapon_Range_Bow':
                raise KeyError(name)
            return synthetic_bntx(tile_mode=1 if name == 'Item_Hookshot' else 0)
        icons = ingame_icons.parse(ingame_icons.icons_file(read_picture))
        self.assertEqual([item for item, _ in icons],
                         [item for item, _ in ingame_icons.grid_icons() if item not in ('Bow', 'Progressive Hookshot')])
        self.assertEqual(asked, [name for _, name in ingame_icons.grid_icons()])
        self.assertIsNone(ingame_icons.icons_file(missing_picture))


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
        self.assertIn('`ingame_tracker/` folder of this repository', (folder / 'SOURCE.md').read_text(encoding='utf-8'))


class InstallTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(ingame_bundle, 'module_binary', return_value=FAKE_MODULE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def attached_artifact(self, root, icons=None):
        helper = ServiceTests('make_artifact')
        helper.make_artifact(root, 'tracked')
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        _, checks, tracking = synthetic_seed()
        files, exefs = {}, {}
        ingame_bundle.attach(manifest, files, exefs, checks, tracking, icons)
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
            self.assertNotIn(ingame_icons.ICON_FILE, manifest['files'])
            read_artifact(Path(directory) / 'seed')

    def test_attach_lists_the_icons_when_given(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.attached_artifact(Path(directory) / 'seed', FAKE_ICONS)
            self.assertEqual(manifest['files'][ingame_icons.ICON_FILE], ingame_bundle.describe(FAKE_ICONS))
            self.assertEqual(list(manifest['files']), sorted(manifest['files']))
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


class UpdateTests(unittest.TestCase):
    """update-tracker: a seed's seed.trk and subsdk7 brought to this version, nothing else touched."""
    TRACKER_PATHS = {'romfs/' + ingame_bundle.SEED_FILE, 'exefs/subsdk7'}

    def setUp(self):
        patcher = patch.object(ingame_bundle, 'module_binary', return_value=FAKE_MODULE)
        patcher.start()
        self.addCleanup(patcher.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.mods = Path(directory.name) / '0400486024DEC000'
        self.mods.mkdir()

    def installed_seed(self, tracker=True):
        """A seed as generate writes it, whose tracker (if any) came from an older version."""
        root = self.mods / 'seed'
        ServiceTests('make_artifact').make_artifact(root, 'update')
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        root = root.rename(self.mods / ('OoT_Randomizer_' + manifest['seed_id'][:16]))
        _, checks, tracking = synthetic_seed()
        tracking.update(seed_id=manifest['seed_id'], schema_version=1)
        tracking_bytes = json.dumps(tracking, ensure_ascii=False, indent=2).encode('utf-8')
        if tracker:
            for relative, data in [(Path('romfs') / ingame_bundle.SEED_FILE, b'RTRK from 0.1.0'),
                                   (Path('exefs') / 'subsdk7', b'NSO0 module 0.1.0')]:
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_bytes(data)
            manifest['files'] = dict(sorted({**manifest['files'],
                                             ingame_bundle.SEED_FILE: ingame_bundle.describe(b'RTRK from 0.1.0')}.items()))
            manifest['exefs'] = {'subsdk7': ingame_bundle.describe(b'NSO0 module 0.1.0')}
        manifest['tracking'] = {'schema_version': 1, 'sha256': hashlib.sha256(tracking_bytes).hexdigest(),
                                'new_save_required': True, 'mode': 'save'}
        for name, data in [('manifest.json', manifest), ('checks.json', {'seed_id': manifest['seed_id'], 'checks': checks}),
                           ('spoiler.json', {'placements': ['Ice Arrows']})]:
            (root / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        (root / 'tracking.json').write_bytes(tracking_bytes)
        read_artifact(root)
        return root

    @staticmethod
    def snapshot(root):
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()}

    def changed(self, before, after):
        self.assertLessEqual(set(before), set(after))   # nothing removed, and only the tracker's files added
        self.assertLessEqual(set(after) - set(before), self.TRACKER_PATHS)
        return {path for path in after if before.get(path) != after[path]}

    def test_only_the_tracker_files_and_their_manifest_entries_change(self):
        root = self.installed_seed()
        before = self.snapshot(root)
        self.assertEqual(update_ingame_tracker(root), ['romfs/' + ingame_bundle.SEED_FILE, 'exefs/subsdk7', 'manifest.json'])
        after = self.snapshot(root)
        self.assertEqual(self.changed(before, after), self.TRACKER_PATHS | {'manifest.json'})
        self.assertEqual(after['exefs/subsdk7'], FAKE_MODULE)
        self.assertEqual(struct.unpack_from('<H', after['romfs/' + ingame_bundle.SEED_FILE], 4)[0], fmt.VERSION)
        old, new = (json.loads(data['manifest.json']) for data in (before, after))
        self.assertEqual(new['files'][ingame_bundle.SEED_FILE],
                         ingame_bundle.describe(after['romfs/' + ingame_bundle.SEED_FILE]))
        self.assertEqual(new['exefs'], {'subsdk7': ingame_bundle.describe(FAKE_MODULE)})
        for manifest in (old, new):
            del manifest['files'][ingame_bundle.SEED_FILE], manifest['exefs']
        self.assertEqual(old, new)
        old_lines, new_lines = before['manifest.json'].splitlines(True), after['manifest.json'].splitlines(True)
        self.assertEqual(len(old_lines), len(new_lines))   # same layout and line endings: only the four values differ
        self.assertEqual(len([1 for a, b in zip(old_lines, new_lines) if a != b]), 4)
        read_artifact(root)

    def test_a_second_update_changes_nothing(self):
        root = self.installed_seed()
        update_ingame_tracker(root)
        before = self.snapshot(root)
        self.assertEqual(update_ingame_tracker(root), [])
        self.assertEqual(self.snapshot(root), before)

    def test_a_seed_without_the_tracker_gets_it_only_when_asked(self):
        root = self.installed_seed(tracker=False)
        before = self.snapshot(root)
        with self.assertRaisesRegex(ValueError, 'without the in-game tracker'):
            update_ingame_tracker(root)
        self.assertEqual(self.snapshot(root), before)
        update_ingame_tracker(root, add=True)
        after = self.snapshot(root)
        self.assertEqual(self.changed(before, after), self.TRACKER_PATHS | {'manifest.json'})
        manifest = read_artifact(root)[0]
        self.assertIn(ingame_bundle.SEED_FILE, manifest['files'])
        self.assertEqual(update_ingame_tracker(root), [])

    def test_refuses_what_is_not_a_seed_or_does_not_match_its_manifest(self):
        with self.assertRaisesRegex(ValueError, 'no manifest.json'):
            update_ingame_tracker(self.mods)
        with self.assertRaisesRegex(ValueError, 'Neither a seed folder'):
            update_ingame_trackers(self.mods)
        for name, change, message in [('tracking.json', lambda t: t.replace(b'4000000000', b'4000000001'), 'Tracking data'),
                                      ('checks.json', lambda t: t.replace(b'"seed_id": "', b'"seed_id": "0'), 'another seed'),
                                      ('tracking.json', None, 'damaged or incomplete')]:
            with self.subTest(name=name, message=message):
                root = self.installed_seed()
                if change:
                    (root / name).write_bytes(change((root / name).read_bytes()))
                else:
                    (root / name).unlink()
                before = self.snapshot(root)
                with self.assertRaisesRegex(ValueError, message):
                    update_ingame_tracker(root)
                self.assertEqual(self.snapshot(root), before)
                for path in root.parent.iterdir():
                    shutil.rmtree(path)

    def test_a_file_in_use_leaves_the_seed_as_it_was(self):
        root = self.installed_seed()
        before, real_replace, calls = self.snapshot(root), os.replace, []

        def replace(source, target):
            calls.append(target)
            if len(calls) == 3:   # the module, after the seed file is in place
                raise PermissionError('in use')
            real_replace(source, target)
        with patch('oot_rando.randomizer.randomizer_services.os.replace', replace):
            with self.assertRaisesRegex(ValueError, 'in use: close the game'):
                update_ingame_tracker(root)
        self.assertEqual(self.snapshot(root), before)
        self.assertEqual([path.name for path in root.iterdir() if path.name.startswith('.')], [])

    def test_the_games_icons_come_with_the_update_and_stay_without_the_game(self):
        root, received = self.installed_seed(), []
        icon_path = 'romfs/' + ingame_icons.ICON_FILE

        def game_icons(nup):
            received.append(nup)
            return FAKE_ICONS
        with patch('oot_rando.randomizer.randomizer_services._game_icons', game_icons):
            self.assertEqual(update_ingame_tracker(root, nup='game.nup'),
                             ['romfs/' + ingame_bundle.SEED_FILE, icon_path, 'exefs/subsdk7', 'manifest.json'])
            self.assertEqual(update_ingame_tracker(root, nup='game.nup'), [])
        self.assertEqual(received, ['game.nup', 'game.nup'])
        before = self.snapshot(root)
        self.assertEqual(before[icon_path], FAKE_ICONS)
        self.assertEqual(update_ingame_tracker(root), [])
        self.assertEqual(self.snapshot(root), before)
        self.assertEqual(read_artifact(root)[0]['files'][ingame_icons.ICON_FILE], ingame_bundle.describe(FAKE_ICONS))

    def test_the_command_takes_the_game_for_the_icons(self):
        self.installed_seed()
        received, output = [], io.StringIO()
        with patch('oot_rando.randomizer.randomizer_services._game_icons', lambda nup: received.append(nup) or FAKE_ICONS), \
                contextlib.redirect_stdout(output):
            self.assertEqual(command_line(['update-tracker', '--nup', 'game.nup', str(self.mods)]), 0)
            self.assertEqual(command_line(['update-tracker', str(self.mods), '--nup']), 2)
        self.assertEqual(received, ['game.nup'])
        self.assertIn(ingame_icons.ICON_FILE, output.getvalue())

    def test_the_command_updates_every_seed_of_a_mods_folder(self):
        root = self.installed_seed()
        for expected in ('Updated ' + str(root), 'Already up to date: ' + str(root)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(command_line(['update-tracker', str(self.mods)]), 0)
            self.assertIn(expected, output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(command_line(['update-tracker', str(self.mods / 'missing')]), 1)


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
        icons = ingame_icons.parse((output / 'romfs' / ingame_icons.ICON_FILE).read_bytes())
        self.assertEqual([item for item, _ in icons], [item for item, _ in ingame_icons.grid_icons()])
        self.assertIn(ingame_icons.ICON_FILE, manifest['files'])

    def test_option_leaves_the_tracker_out(self):
        output, manifest = self.generate_seed(ingame_tracker=False)
        read_artifact(output)
        self.assertNotIn(ingame_bundle.SEED_FILE, manifest['files'])
        self.assertNotIn('exefs', manifest)
        self.assertFalse((output / 'exefs').exists())
        self.assertFalse((output / 'romfs' / 'RandoTracker').exists())


if __name__ == '__main__':
    unittest.main()
