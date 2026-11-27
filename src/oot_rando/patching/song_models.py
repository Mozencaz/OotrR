"""Songs drawn as Sheik's harp, one colour per song (songs shuffled everywhere).

A song pouch actor (``Item_Melody_<song>``) has a rupee as its model
(``Component/ModelInfo/Item_Melody_<song>``: ``Obj_Rupee``): nothing shows it when
a cutscene gives it with its text only (``song_adapter``). In a chest or as a
pickup the item is held up or stands in the world, so with the ``everywhere``
mode each song gets the model of Sheik's harp (``Dm_Item_Sheik_Harp``,
``Model/Item_Harp_Sheik.Item_Harp_Sheik.bfres``) under a project of its own:

* ``Model/Item_Harp_<song>.Item_Harp_Sheik.bfres``: a copy of the harp whose
  material ``Mt_Harp_Sheik`` has its six colour parameters (``ns_param_color0``
  to ``5``, white in the game) set to the song's colour of the ocarina menu;
* the song's ModelInfo names ``Item_Harp_Sheik`` (model) and its project; its
  ActorInfo row takes the harp's model name, box and the song's project.

The derived pickups of a song (``Obj_Rando_Item_Melody_*``) copy the song's
ModelInfo and ActorInfo model keys (``item_forms``): they show the same harp.

BFRES v10 layout read here (little endian, 64-bit offsets from the file start):
the file header holds the model array at 0x28 and the model count (u16) at 0xdc;
a model (``FMDL``, 0x78 bytes) its material array at +0x38 and material
dictionary at +0x40 (count: u32 at +4); a material (``FMAT``, 0xb0 bytes) its
name at +0x08 (u16 length, then the text), a pointer to its shader assign
pointer at +0x10 and its parameter values at +0x58. The shader assign holds its
parameter array at +0x20 and their count (u16) at +0x4a; a parameter (0x18
bytes) holds its name key (u64) at +0x08, its value offset (u16) at +0x10 and
its type (u16, 15: float4) at +0x12. Parameter names are keys of the shared
``Shader/ExternalBinaryString.bfres``: key array at 0xb8, name dictionary at 0xc0
(count: u32 at +4, entries of 16 bytes from +0x18, name at +8 of each).

Not validated in game: the colour parameters are taken as multipliers of the
harp's albedo.
"""
import struct
from oot_rando.formats import byml_codec as codec
from oot_rando.formats.inspect_resources import sarc

HARP_ACTOR = 'Dm_Item_Sheik_Harp'
HARP_FMDB = 'Item_Harp_Sheik'
HARP_MODEL = f'Model/{HARP_FMDB}.{HARP_FMDB}.bfres.zs'
SHADER_NAMES = 'Shader/ExternalBinaryString.bfres.zs'
MATERIAL = 'Mt_Harp_Sheik'
COLOUR_PARAMS = tuple(f'ns_param_color{i}' for i in range(6))
FLOAT4 = 15
ACTOR_INFO = 'RSDB/ActorInfo.Product.111.rstbl.byml.zs'
ROW_MODEL_KEYS = ('FmdbName', 'ModelAabbMax', 'ModelAabbMin')

# Song actor -> colour (sRGB) of its notes on the ocarina menu.
SONG_COLOURS = {
    'Item_Melody_ZeldaLullaby': (255, 120, 200), 'Item_Melody_EponaSong': (240, 95, 40),
    'Item_Melody_SariaSong': (90, 205, 90), 'Item_Melody_SunSong': (255, 215, 60),
    'Item_Melody_TimeSong': (80, 200, 235), 'Item_Melody_StormSong': (110, 100, 235),
    'Item_Melody_ForestMinuet': (104, 172, 82), 'Item_Melody_FireBolero': (200, 80, 72),
    'Item_Melody_WaterSerenade': (87, 120, 217), 'Item_Melody_SpiritRequiem': (201, 126, 59),
    'Item_Melody_ShadowNocturne': (137, 89, 219), 'Item_Melody_LightPrelude': (208, 172, 76),
}
MELODY_PREFIX = 'Item_Melody_'


def project_of(actor):
    """Model project of a song's harp: ``Item_Harp_<song>``."""
    if actor not in SONG_COLOURS:
        raise ValueError('Not a shuffled song: ' + actor)
    return 'Item_Harp_' + actor[len(MELODY_PREFIX):]


def model_path(actor):
    return f'Model/{project_of(actor)}.{HARP_FMDB}.bfres.zs'


def pack_path(actor):
    return f'Pack/Actor/{actor}.pack.zs'


def model_info_path(actor):
    return f'Component/ModelInfo/{actor}.engine__component__ModelInfo.bgyml'


# ------------------------------------------------------------------ BFRES
def read_u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def read_u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def read_pointer(data, offset):
    value = struct.unpack_from('<Q', data, offset)[0]
    if not 0 < value < len(data):
        raise ValueError('BFRES: pointer outside the file.')
    return value


def read_name(data, offset):
    size = read_u16(data, offset)
    return data[offset + 2:offset + 2 + size].decode('utf-8')


def _check(data, offset, magic):
    if data[offset:offset + 4] != magic:
        raise ValueError(f'BFRES: {magic.decode()} expected at {offset:#x}.')


def shader_keys(names):
    """``Shader/ExternalBinaryString.bfres``: parameter name -> key."""
    _check(names, 0, b'FRES')
    keys, dictionary = read_pointer(names, 0xb8), read_pointer(names, 0xc0)
    return {read_name(names, read_pointer(names, dictionary + 0x20 + 16 * i)):
            struct.unpack_from('<Q', names, keys + 8 * i)[0] for i in range(read_u32(names, dictionary + 4))}


def material_params(model):
    """``{material: {key: (type, value offset)}}`` of every model of a BFRES."""
    _check(model, 0, b'FRES')
    result = {}
    models = read_pointer(model, 0x28)
    for m in range(read_u16(model, 0xdc)):
        fmdl = models + 0x78 * m
        _check(model, fmdl, b'FMDL')
        materials = read_pointer(model, fmdl + 0x38)
        for i in range(read_u32(model, read_pointer(model, fmdl + 0x40) + 4)):
            fmat = materials + 0xb0 * i
            _check(model, fmat, b'FMAT')
            assign = read_pointer(model, read_pointer(model, fmat + 0x10))
            count = read_u16(model, assign + 0x4a)
            params = {}
            if count:
                array, values = read_pointer(model, assign + 0x20), read_pointer(model, fmat + 0x58)
                for p in range(count):
                    entry = array + 0x18 * p
                    key = struct.unpack_from('<Q', model, entry + 8)[0]
                    params[key] = (read_u16(model, entry + 0x12), values + read_u16(model, entry + 0x10))
            result[read_name(model, read_pointer(model, fmat + 8))] = params
    return result


def linear(rgb):
    """sRGB 0-255 -> linear, scaled so the brightest channel is 1 (the harp keeps its shading)."""
    channels = [(c / 255) / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in rgb]
    top = max(channels)
    return tuple(1.0 for _ in channels) if top <= 0 else tuple(c / top for c in channels)


def tinted_harp(model, keys, rgb):
    """Copy of the harp model with its colour parameters set to ``rgb``."""
    params = material_params(model).get(MATERIAL)
    if params is None:
        raise ValueError('Harp material not found: ' + MATERIAL)
    out = bytearray(model)
    colour = linear(rgb)
    for name in COLOUR_PARAMS:
        if name not in keys or keys[name] not in params:
            raise ValueError('Harp colour parameter not found: ' + name)
        kind, offset = params[keys[name]]
        if kind != FLOAT4:
            raise ValueError('Harp colour parameter is not a float4: ' + name)
        old = struct.unpack_from('<4f', out, offset)
        if old[:3] != (1.0, 1.0, 1.0):
            raise ValueError('Harp colour parameter is not white: ' + name)
        struct.pack_into('<4f', out, offset, *colour, old[3])
    return bytes(out)


# ------------------------------------------------------------------ actors
def repoint_pack(pack, actor, codec):
    """Song pack bytes whose ModelInfo names the song's harp."""
    files = sarc(pack)
    path = model_info_path(actor)
    if path not in files:
        raise ValueError('Song model info not found: ' + actor)
    document = codec.load(files[path])
    if set(document['root']) != {'FmdbName', 'ModelProjectName'}:
        raise ValueError('Unexpected song model info: ' + actor)
    document['root'].update(FmdbName=HARP_FMDB, ModelProjectName=project_of(actor))
    files[path] = codec.dump(document)
    return codec.build_sarc(files)


def repoint_rows(rows, actors):
    """ActorInfo rows of the songs take the harp's model keys and their project."""
    by_id = {row['__RowId']: row for row in rows}
    harp = by_id.get(HARP_ACTOR)
    if harp is None or harp.get('FmdbName') != HARP_FMDB:
        raise ValueError('Harp ActorInfo row not found.')
    for actor in actors:
        row = by_id.get(actor)
        if row is None:
            raise ValueError('Song ActorInfo row not found: ' + actor)
        for key in ROW_MODEL_KEYS:
            row[key] = dict(harp[key]) if isinstance(harp[key], dict) else harp[key]
        row['ModelProjectName'] = project_of(actor)
    return rows


def build_files(read_raw, actors=tuple(SONG_COLOURS)):
    """``(modified, new)`` raw resources drawing ``actors`` as coloured harps.

    ``read_raw(path)`` returns decompressed bytes (modified ones first); ``new``
    values are ``(raw, compression and size template path)``."""
    keys = shader_keys(read_raw(SHADER_NAMES))
    harp = read_raw(HARP_MODEL)
    modified, new = {}, {}
    for actor in sorted(actors):
        new[model_path(actor)] = (tinted_harp(harp, keys, SONG_COLOURS[actor]), HARP_MODEL)
        modified[pack_path(actor)] = repoint_pack(read_raw(pack_path(actor)), actor, codec)
    table = codec.load(read_raw(ACTOR_INFO))
    repoint_rows(table['root'], sorted(actors))
    modified[ACTOR_INFO] = codec.dump(table)
    return modified, new
