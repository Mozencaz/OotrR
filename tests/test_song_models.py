"""Songs shuffled everywhere: Sheik's harp in each song's colour, placement rule."""
import os
import struct
import unittest

import _src_path  # noqa: F401
from oot_rando.formats import byml_codec as codec
from oot_rando.patching import song_models
from oot_rando.patching.song_adapter import song_allowed

NUP = os.environ.get('OOT_NUP')


def _text(name):
    raw = name.encode()
    return struct.pack('<H', len(raw)) + raw + b'\0'


def fake_names(names):
    """Minimal ExternalBinaryString: keys at 0xb8, dictionary at 0xc0."""
    data = bytearray(0x100)
    data[:4] = b'FRES'
    keys_at, dict_at = len(data), len(data) + 8 * len(names)
    data += b''.join(struct.pack('<Q', 1000 + i) for i in range(len(names)))
    data += bytes(0x18 + 16 * (len(names) + 1))
    struct.pack_into('<I', data, dict_at + 4, len(names))
    for i, name in enumerate(names):
        struct.pack_into('<Q', data, dict_at + 0x20 + 16 * i, len(data))
        data += _text(name)
    struct.pack_into('<Q', data, 0xb8, keys_at)
    struct.pack_into('<Q', data, 0xc0, dict_at)
    return bytes(data)


def fake_model(material, params):
    """One FMDL, one FMAT whose parameters are ``[(key, type, value)]``."""
    data = bytearray(0x100)
    data[:4] = b'FRES'
    struct.pack_into('<H', data, 0xdc, 1)
    fmdl = len(data)
    data += b'FMDL' + bytes(0x74)
    struct.pack_into('<Q', data, 0x28, fmdl)
    dictionary = len(data)
    data += struct.pack('<II', 0, 1) + bytes(8)
    fmat = len(data)
    data += b'FMAT' + bytes(0xac)
    struct.pack_into('<Q', data, fmdl + 0x38, fmat)
    struct.pack_into('<Q', data, fmdl + 0x40, dictionary)
    struct.pack_into('<Q', data, fmat + 8, len(data))
    data += _text(material) + b'\0'
    assign = len(data)
    data += bytes(0x50)
    holder = len(data)
    data += struct.pack('<Q', assign)
    struct.pack_into('<Q', data, fmat + 0x10, holder)
    struct.pack_into('<H', data, assign + 0x4a, len(params))
    array = len(data)
    data += bytes(0x18 * len(params))
    struct.pack_into('<Q', data, assign + 0x20, array)
    values = len(data)
    struct.pack_into('<Q', data, fmat + 0x58, values)
    for i, (key, kind, value) in enumerate(params):
        entry = array + 0x18 * i
        struct.pack_into('<QHH', data, entry + 8, key, len(data) - values, kind)
        data += struct.pack('<4f', *value)
    return bytes(data)


class HarpModelTests(unittest.TestCase):
    def setUp(self):
        names = list(song_models.COLOUR_PARAMS) + ['p_other']
        self.names = fake_names(names)
        self.keys = song_models.shader_keys(self.names)
        params = [(self.keys[n], song_models.FLOAT4, (1.0, 1.0, 1.0, 0.5)) for n in song_models.COLOUR_PARAMS]
        params.append((self.keys['p_other'], song_models.FLOAT4, (0.25, 0.25, 0.25, 1.0)))
        self.model = fake_model(song_models.MATERIAL, params)

    def colours(self, model):
        params = song_models.material_params(model)[song_models.MATERIAL]
        return {name: struct.unpack_from('<4f', model, params[self.keys[name]][1])
                for name in list(song_models.COLOUR_PARAMS) + ['p_other']}

    def test_tint_sets_the_six_colour_parameters_only(self):
        tinted = song_models.tinted_harp(self.model, self.keys, (255, 0, 0))
        self.assertEqual(len(tinted), len(self.model))
        colours = self.colours(tinted)
        for name in song_models.COLOUR_PARAMS:
            self.assertEqual(colours[name], (1.0, 0.0, 0.0, 0.5))
        self.assertEqual(colours['p_other'], (0.25, 0.25, 0.25, 1.0))

    def test_tint_refuses_an_unexpected_harp(self):
        once = song_models.tinted_harp(self.model, self.keys, (90, 205, 90))
        with self.assertRaises(ValueError):
            song_models.tinted_harp(once, self.keys, (90, 205, 90))   # no longer white
        with self.assertRaises(ValueError):
            song_models.tinted_harp(fake_model('Mt_Other', []), self.keys, (1, 2, 3))

    def test_colours_are_normalised_and_distinct(self):
        self.assertEqual(len(song_models.SONG_COLOURS), 12)
        shades = {song: song_models.linear(rgb) for song, rgb in song_models.SONG_COLOURS.items()}
        self.assertEqual(len(set(shades.values())), 12)
        for shade in shades.values():
            self.assertAlmostEqual(max(shade), 1.0)
            self.assertTrue(all(0.0 <= c <= 1.0 for c in shade))

    def test_names(self):
        self.assertEqual(song_models.project_of('Item_Melody_SunSong'), 'Item_Harp_SunSong')
        self.assertEqual(song_models.model_path('Item_Melody_SunSong'),
                         'Model/Item_Harp_SunSong.Item_Harp_Sheik.bfres.zs')
        with self.assertRaises(ValueError):
            song_models.project_of('Item_Melody_ScarecrowSong')


class ActorTests(unittest.TestCase):
    def test_pack_names_the_song_harp(self):
        actor = 'Item_Melody_SariaSong'
        info = song_models.model_info_path(actor)
        pack = codec.build_sarc({info: codec.dump({'endian': '<', 'version': 7, 'root': {
            'FmdbName': 'Obj_Rupee', 'ModelProjectName': 'Obj_Rupee'}}), 'Other/File.bin': b'\1\2'})
        from oot_rando.formats.inspect_resources import sarc
        files = sarc(song_models.repoint_pack(pack, actor, codec))
        self.assertEqual(codec.load(files[info])['root'],
                         {'FmdbName': 'Item_Harp_Sheik', 'ModelProjectName': 'Item_Harp_SariaSong'})
        self.assertEqual(files['Other/File.bin'], b'\1\2')

    def test_rows_take_the_harp_box(self):
        box = {'X': 0.29, 'Y': 0.25, 'Z': 0.05}
        rows = [{'__RowId': 'Dm_Item_Sheik_Harp', 'FmdbName': 'Item_Harp_Sheik', 'ModelProjectName': 'Item_Harp_Sheik',
                 'ModelAabbMax': box, 'ModelAabbMin': box},
                {'__RowId': 'Item_Melody_SunSong', 'FmdbName': 'Obj_Rupee', 'ModelProjectName': 'Obj_Rupee',
                 'ModelAabbMax': {}, 'ModelAabbMin': {}, 'ClassName': 'X'}]
        song_models.repoint_rows(rows, ['Item_Melody_SunSong'])
        self.assertEqual(rows[1], {'__RowId': 'Item_Melody_SunSong', 'FmdbName': 'Item_Harp_Sheik',
                                   'ModelProjectName': 'Item_Harp_SunSong', 'ModelAabbMax': box,
                                   'ModelAabbMin': box, 'ClassName': 'X'})
        with self.assertRaises(ValueError):
            song_models.repoint_rows(rows[1:], ['Item_Melody_SunSong'])

    def test_pickups_stand_above_the_ground(self):
        from oot_rando.game.item_forms import ground_lift, model_of
        self.assertEqual(model_of('Item_Melody_SunSong'), 'Dm_Item_Sheik_Harp')
        self.assertGreater(ground_lift('Obj_Rupee_Green', 'Obj_Rando_Item_Melody_SunSong'), 0.25)


class PlacementTests(unittest.TestCase):
    def test_everywhere_adds_chests_and_pickups(self):
        song = 'Item_Melody_SunSong'
        for source, form in (('chest', 'chest'), ('freestanding', 'world'), ('pot', 'world')):
            self.assertTrue(song_allowed('everywhere', source, song, form), source)
            self.assertFalse(song_allowed('any', source, song, form), source)
        self.assertTrue(song_allowed('everywhere', 'boss', song, 'event'))
        self.assertFalse(song_allowed('everywhere', 'npc', song, 'event'))
        self.assertFalse(song_allowed('everywhere', 'shop', song, 'shop'))
        self.assertTrue(song_allowed('everywhere', 'song', 'Item_Hookshot', 'event'))


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class WithGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        from oot_rando.game.world_maps import effective_members
        nup = Nup(NUP)
        try:
            members, d = effective_members(nup), dictionaries(nup)
            cls.members = set(members)
            needed = [song_models.HARP_MODEL, song_models.SHADER_NAMES, song_models.ACTOR_INFO] + [
                song_models.pack_path(a) for a in song_models.SONG_COLOURS]
            cls.raw = {path: decompress(nup.read(members[path]), d) for path in needed}
        finally:
            nup.stream.close()

    def test_new_names_are_free(self):
        for actor in song_models.SONG_COLOURS:
            self.assertNotIn(song_models.model_path(actor), self.members)
            self.assertFalse([p for p in self.members if song_models.project_of(actor) in p])

    def test_build_files(self):
        modified, new = song_models.build_files(self.raw.__getitem__)
        self.assertEqual(set(new), {song_models.model_path(a) for a in song_models.SONG_COLOURS})
        keys = song_models.shader_keys(self.raw[song_models.SHADER_NAMES])
        for actor, rgb in song_models.SONG_COLOURS.items():
            model, template = new[song_models.model_path(actor)]
            self.assertEqual((len(model), template), (len(self.raw[template]), song_models.HARP_MODEL))
            params = song_models.material_params(model)[song_models.MATERIAL]
            for name in song_models.COLOUR_PARAMS:
                value = struct.unpack_from('<4f', model, params[keys[name]][1])
                self.assertEqual(value[:3], tuple(struct.unpack('<3f', struct.pack('<3f', *song_models.linear(rgb)))))
            changed = sum(a != b for a, b in zip(model, self.raw[template]))
            self.assertLessEqual(changed, 6 * 12)
        rows = {r['__RowId']: r for r in codec.load(modified[song_models.ACTOR_INFO])['root']}
        self.assertEqual(rows['Item_Melody_TimeSong']['ModelProjectName'], 'Item_Harp_TimeSong')
        self.assertEqual(rows['Item_Melody_TimeSong']['FmdbName'], 'Item_Harp_Sheik')
        self.assertEqual(len(rows), len(codec.load(self.raw[song_models.ACTOR_INFO])['root']))
