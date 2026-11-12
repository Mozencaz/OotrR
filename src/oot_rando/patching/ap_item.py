"""Archipelago item: items of other players shown as a golden medallion with the Archipelago logo.

Model: a copy of the Fire Medallion (``Model/Item_Medal_Fire.Item_Medal_Fire.bfres``)
under another project name (``Item_Medal_Arch``):

* the glass dome, the fire emblem under it and the glaze of the back
  (shapes ``Glass``, ``Glass_Back``, ``Glaze``) are hidden: their vertices are
  collapsed to one point, so their triangles have no area; so are the pieces
  of the golden flame in relief on the base (``Medal_Base``, every LOD);
* the six textures of the base (``Mt_Item_Medal_Fire_*``) are renamed to
  ``Mt_Item_Medal_Arch_*`` (same length: no offset moves) and replaced.

Textures (no game pixel is decoded or kept):

* albedo: a BC1 texture of the same size and name length
  (``Mt_Upper_Enemy_Poe_Alb``) used as container, entirely rewritten: gold
  everywhere, and both faces of the disc carry the logo on cream with a gold
  rim. BC1 (two colours and four shades per 4x4 block) is encoded here, so the
  logo stays sharp;
* metalness: metal everywhere except the logo area; roughness, occlusion,
  emission and normal: one constant value.

Held over Link's head, the item spins like the other key items (wallet):
common item animation (``AS/Item_Common``, ``Item_Common_Animation``).

Each foreign item gets its own pouch actor (``Item_AP_<hash>``) built like the
monster souls, with get-item texts naming the item and the player it belongs to.
"""
import hashlib
import struct

PREFIX = 'Archipelago: '
ACTOR_PREFIX = 'Item_AP_'
MODEL_ACTOR = 'Item_Medal_Fire'
MODEL_FILE = 'Model/Item_Medal_Fire.Item_Medal_Fire.bfres.zs'
PROJECT = 'Item_Medal_Arch'           # same length as Item_Medal_Fire
MODEL_INFO = {'FmdbName': 'Item_Medal_Fire', 'ModelProjectName': PROJECT}
NEW_MODEL_FILE = f'Model/{PROJECT}.Item_Medal_Fire.bfres.zs'
OLD_TEX, NEW_TEX = 'Mt_Item_Medal_Fire', 'Mt_Item_Medal_Arch'
HIDDEN_SHAPES = ('Glass_Back__Mt_Medal_Glass_Back', 'Glass__Mt_Medal_Glass', 'Glaze__Mt_Medal_Glaze')
# The golden flame in relief: separate pieces of the base standing on its front
# face (shape, plane of the face, radius of the face).
RELIEF = ('Medal_Base__Mt_Item_Medal_Fire', 0.0095, 0.105)
# Texture suffix -> source BNTX (same size and name length as the medallion's own).
SOURCES = {'Alb': 'Tex/Mt_Upper_Enemy_Poe_Alb.bntx.zs'}
REPLACED = ('Alb', 'AO', 'Emc', 'Mtl', 'Nrm', 'Rgh')
# Spinning when held: the common item animation of the key items (wallet).
SPIN_TEMPLATE = 'Item_Wallet_Medium'
SPIN_AS = '?AS/Item_Common.root.asb'
SPIN_ANIMATION = 'Item_Common_Animation'
# Faces of the disc on the 576x576 albedo sheet: centre, radius (UV of the base shape).
SHEET = 576
FACES = ((153, 152), (377, 375))
FACE_RADIUS = 134
RIM = 0.86                            # inner radius of the golden rim, relative to the face
CREAM, GOLD, GOLD_DARK = (246, 239, 222), (214, 168, 74), (150, 104, 38)
FLAT_NORMAL = (128, 128, 128, 128)
METAL, MATTE, ROUGHNESS, OCCLUSION = 255, 0, 96, 255
# Archipelago logo in a 512x512 frame: six circles drawn in this order, each with
# a background-coloured halo that cuts the circles drawn before it.
LOGO_CIRCLES = (((255.5, 102), (201, 118, 130)), ((110, 183), (238, 227, 145)), ((400.5, 183), (117, 194, 117)),
                ((111, 325), (118, 126, 189)), ((400, 325), (202, 148, 194)), ((255.5, 410), (217, 160, 125)))
LOGO_RADIUS, LOGO_HALO = 100, 125
ASTC_BLOCKS = {0x2d: (4, 4), 0x2e: (5, 4), 0x2f: (5, 5), 0x30: (6, 5), 0x31: (6, 6), 0x32: (8, 5), 0x33: (8, 6),
               0x34: (8, 8), 0x35: (10, 5), 0x36: (10, 6), 0x37: (10, 8), 0x38: (10, 10), 0x39: (12, 10),
               0x3a: (12, 12)}
BC1, BC4 = 0x1a, 0x1d


# ------------------------------------------------------------------ items and actors
def is_ap_item(item):
    return item.startswith(PREFIX)


def ap_item(label):
    """Planner item name of another player's item (``label``: "Sword (Ami)")."""
    return PREFIX + label


def ap_actor(item):
    """Pouch actor of an Archipelago item: stable, independent of the order of the items."""
    return ACTOR_PREFIX + hashlib.sha256(item.encode('utf-8')).hexdigest()[:12]


def is_ap_actor(actor):
    return actor.startswith(ACTOR_PREFIX)


def ap_messages(item, player, language):
    """Get-item texts of another player's item."""
    if language.endswith('fr'):
        return {'Name': f'{item} ({player})',
                'Caption': f'Objet Archipelago de {player}.',
                'GetMessage': f'Vous avez trouvé « {item} » pour {player} !',
                'GetCaption': 'Il sera envoyé dans son monde.'}
    return {'Name': f'{item} ({player})',
            'Caption': f'Archipelago item of {player}.',
            'GetMessage': f'You found "{item}" for {player}!',
            'GetCaption': 'It will be sent to their world.'}


# ------------------------------------------------------------------ drawing
def logo_colour(x, y):
    """Colour of the logo at (x, y) of its 512x512 frame, or None (background)."""
    colour = None
    for (cx, cy), fill in LOGO_CIRCLES:
        distance = (x - cx) ** 2 + (y - cy) ** 2
        if distance <= LOGO_RADIUS ** 2:
            colour = fill
        elif distance <= LOGO_HALO ** 2:
            colour = None
    return colour


def face_colour(dx, dy):
    """Colour of a medallion face at offset (dx, dy) from its centre, or None outside."""
    distance = (dx * dx + dy * dy) ** 0.5
    if distance > FACE_RADIUS:
        return None
    inner = FACE_RADIUS * RIM
    if distance > inner:
        return GOLD
    if distance > inner - 3:
        return GOLD_DARK              # thin engraved line between rim and face
    scale = 512 / (2 * inner * 0.94)
    return logo_colour(256 + dx * scale, 256 + dy * scale) or CREAM


def sheet_colour(x, y):
    """Albedo at (x, y) of the 576x576 sheet: a face, or plain gold elsewhere (edge of the disc)."""
    for cx, cy in FACES:
        colour = face_colour(x - cx, y - cy)
        if colour is not None:
            return colour
    return GOLD


def on_logo(x, y):
    """Whether (x, y) of the sheet is inside the cream face (not metal)."""
    inner = FACE_RADIUS * RIM
    return any((x - cx) ** 2 + (y - cy) ** 2 <= inner * inner for cx, cy in FACES)


# ------------------------------------------------------------------ block encodings
def void_extent(rgba):
    """ASTC LDR void-extent block: one constant colour (8-bit channels)."""
    return bytes.fromhex('fcfdffffffffffff') + struct.pack('<4H', *(c * 257 for c in rgba))


def bc4_constant(value):
    """BC4 block of one value."""
    return bytes((value, value)) + bytes(6)


def _rgb565(colour):
    r, g, b = colour[:3]
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _expand565(value):
    r, g, b = value >> 11, (value >> 5) & 63, value & 31
    return ((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31)


def bc1_block(texels):
    """BC1 block (opaque, four-colour mode) of 16 RGB texels in row order."""
    distinct = sorted(set(texels))
    if len(distinct) == 1:
        a = b = distinct[0]
    else:
        # The two texels furthest apart: exact for the two-colour edges of a flat drawing.
        a, b = max(((p, q) for i, p in enumerate(distinct) for q in distinct[i + 1:]),
                   key=lambda pair: sum((pair[0][k] - pair[1][k]) ** 2 for k in range(3)))
    c0, c1 = _rgb565(a), _rgb565(b)
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return struct.pack('<HHI', c0, c1, 0)
    e0, e1 = _expand565(c0), _expand565(c1)
    palette = (e0, e1, tuple((2 * e0[k] + e1[k]) // 3 for k in range(3)),
               tuple((e0[k] + 2 * e1[k]) // 3 for k in range(3)))
    indices = 0
    for index, texel in enumerate(texels):
        best = min(range(4), key=lambda i: sum((palette[i][k] - texel[k]) ** 2 for k in range(3)))
        indices |= best << (2 * index)
    return struct.pack('<HHI', c0, c1, indices)


# ------------------------------------------------------------------ BNTX
def _block_address(x, y, gob_height, width_gobs, bpe=16):
    """Byte address of element (x, y) in Tegra block-linear layout (see icon_extract.deblock_linear).

    Inside a 64-byte x 8-row GOB, address bits 4..8 are y0, y1, xb4, y2, xb5 where
    xb is the byte column (decoding the game's own textures confirms this order).
    """
    xb = x * bpe
    gob_row = (y // (8 * gob_height)) * 512 * gob_height * width_gobs + ((y % (8 * gob_height)) // 8) * 512
    return (gob_row + (xb // 64) * 512 * gob_height + (xb & 15) + (y & 1) * 16 + ((y >> 1) & 1) * 32
            + ((xb >> 4) & 1) * 64 + ((y >> 2) & 1) * 128 + ((xb >> 5) & 1) * 256)


def bntx_info(data):
    """Texture header of a single-texture BNTX: format, size, layout and mip levels."""
    if data[:4] != b'BNTX':
        raise ValueError('Not a BNTX texture.')
    at = data.find(b'BRTI')
    if at < 0 or data.find(b'BRTI', at + 4) >= 0:
        raise ValueError('Expected exactly one texture in the BNTX.')
    tile_mode = struct.unpack_from('<H', data, at + 0x12)[0]
    mip_count = struct.unpack_from('<H', data, at + 0x16)[0]
    fmt = struct.unpack_from('<I', data, at + 0x1C)[0]
    width, height = struct.unpack_from('<II', data, at + 0x24)
    layout = struct.unpack_from('<I', data, at + 0x34)[0]
    size = struct.unpack_from('<I', data, at + 0x50)[0]
    mips = struct.unpack_from('<Q', data, at + 0x70)[0]
    levels = [struct.unpack_from('<Q', data, mips + 8 * level)[0] for level in range(mip_count)]
    if tile_mode != 0:
        raise ValueError('Linear BNTX layout not supported.')
    return {'format': fmt >> 8, 'width': width, 'height': height, 'gob_height': 1 << (layout & 7),
            'start': levels[0], 'size': size, 'levels': levels}


def _footprint(fmt):
    if fmt in ASTC_BLOCKS:
        return ASTC_BLOCKS[fmt] + (16,)
    if fmt in (BC1, BC4):
        return 4, 4, 8
    raise ValueError(f'Unsupported texture format {fmt:#x}.')


def paint_bntx(data, block):
    """Rewrite every mip level in place.

    ``block(x0, y0, w, h, scale)`` gets a block in level-0 pixels (``scale``: size
    of one texel of this level in level-0 pixels) and returns the encoded block
    bytes, or None to keep it. Only GOB height 1 is handled (it never changes with
    the mip levels, so every level uses the same addressing).
    """
    info = bntx_info(data)
    bw, bh, bpe = _footprint(info['format'])
    if info['gob_height'] != 1:
        raise ValueError('Unsupported texture layout (GOB height above 1).')
    out = bytearray(data)
    painted = 0
    end = info['start'] + info['size']
    for level, start in enumerate(info['levels']):
        width, height = max(1, info['width'] >> level), max(1, info['height'] >> level)
        width_blocks, height_blocks = -(-width // bw), -(-height // bh)
        width_gobs = -(-width_blocks * bpe // 64)
        scale = 1 << level
        for y in range(height_blocks):
            for x in range(width_blocks):
                encoded = block(x * bw * scale, y * bh * scale, bw * scale, bh * scale, scale)
                if encoded is None:
                    continue
                if len(encoded) != bpe:
                    raise ValueError('Encoded block of the wrong size.')
                address = start + _block_address(x, y, 1, width_gobs, bpe)
                if address + bpe > end:
                    raise ValueError('Texture block outside the image data.')
                out[address:address + bpe] = encoded
                painted += 1
    return bytes(out), painted


def fill_bntx(data, encoded):
    """Every block of every mip level set to one encoded block (layout does not matter)."""
    info = bntx_info(data)
    _, _, bpe = _footprint(info['format'])
    if len(encoded) != bpe or info['start'] % bpe or info['size'] % bpe:
        raise ValueError('Constant block does not match the texture.')
    out = bytearray(data)
    out[info['start']:info['start'] + info['size']] = encoded * (info['size'] // bpe)
    return bytes(out)


def rename(data, old, new):
    """Same-length rename of every occurrence of a name (offsets unchanged)."""
    old, new = old.encode(), new.encode()
    if len(old) != len(new):
        raise ValueError('Renamed resources must keep their name length.')
    if not data.count(old):
        raise ValueError(f'Name not found: {old.decode()}')
    return data.replace(old, new)


def albedo_block(x0, y0, width, height, scale):
    """BC1 block of the albedo sheet (2x2 samples per texel at the full-size level)."""
    step = width / 4
    samples = 2 if scale == 1 else 1
    texels = []
    for j in range(4):
        for i in range(4):
            colours = [sheet_colour(x0 + (i + (a + 0.5) / samples) * step, y0 + (j + (b + 0.5) / samples) * step)
                       for a in range(samples) for b in range(samples)]
            texels.append(tuple(round(sum(c[k] for c in colours) / len(colours)) for k in range(3)))
    return bc1_block(texels)


def metal_block(x0, y0, width, height, scale):
    return bc4_constant(MATTE if on_logo(x0 + width / 2, y0 + height / 2) else METAL)


# ------------------------------------------------------------------ BFRES
def _shapes(data):
    """``{name: shape}`` of a BFRES model: vertex positions (``_p0``, half4) and LOD meshes.

    The buffer section (second one of the relocation table) holds the index
    buffers first, then the vertex buffers.
    """
    if data[:8] != b'FRES    ':
        raise ValueError('Not a BFRES model.')
    rlt = struct.unpack_from('<I', data, 0x18)[0]
    if data[rlt:rlt + 4] != b'_RLT':
        raise ValueError('BFRES relocation table not found.')
    buffers = struct.unpack_from('<QI', data, rlt + 16 + 24)[1]

    def string(offset):
        length = struct.unpack_from('<H', data, offset)[0]
        return bytes(data[offset + 2:offset + 2 + length]).decode('utf-8', 'replace')

    shapes = {}
    at = data.find(b'FSHP')
    while 0 <= at < rlt:
        name = string(struct.unpack_from('<Q', data, at + 8)[0])
        fvtx = struct.unpack_from('<Q', data, at + 0x10)[0]
        if data[fvtx:fvtx + 4] != b'FVTX' or data[fvtx + 0x4D] != 1:
            raise ValueError('Unexpected vertex buffer for ' + name)
        attributes = struct.unpack_from('<Q', data, fvtx + 8)[0]
        position = None
        for index in range(data[fvtx + 0x4C]):
            entry = attributes + index * 16
            if string(struct.unpack_from('<Q', data, entry)[0]) == '_p0':
                position = struct.unpack_from('<HH', data, entry + 8)
                offset = struct.unpack_from('<H', data, entry + 12)[0]
        if position is None or position[0] != 0x1505:
            raise ValueError('Unexpected position format for ' + name)
        stride = struct.unpack_from('<I', data, struct.unpack_from('<Q', data, fvtx + 0x38)[0])[0]
        first = buffers + struct.unpack_from('<I', data, fvtx + 0x48)[0]
        count = struct.unpack_from('<I', data, fvtx + 0x50)[0]
        meshes = []
        mesh_array = struct.unpack_from('<Q', data, at + 0x18)[0]
        for level in range(data[at + 0x5B]):
            mesh = mesh_array + level * 0x38
            start, primitive, kind, total, base = struct.unpack_from('<5I', data, mesh + 0x20)
            if primitive != 3 or kind != 1:
                raise ValueError('Unexpected index buffer for ' + name)
            indices = struct.unpack_from(f'<{total}H', data, buffers + start)
            if max(indices) + base >= count:
                raise ValueError('Index out of range for ' + name)
            meshes.append([index + base for index in indices])
        shapes[name] = {'positions': [first + v * stride + offset for v in range(count)], 'meshes': meshes}
        at = data.find(b'FSHP', at + 4)
    return shapes


def hide_shapes(model, names=HIDDEN_SHAPES):
    """Collapse every vertex of the named shapes to the origin (their triangles vanish)."""
    data = bytearray(model)
    shapes = _shapes(data)
    missing = set(names) - set(shapes)
    if missing:
        raise ValueError('Shapes not found in the model: ' + ', '.join(sorted(missing)))
    for name in names:
        for address in shapes[name]['positions']:
            data[address:address + 6] = bytes(6)          # x, y, z = 0 (w kept)
    return bytes(data)


def relief_islands(model, shape, face, radius):
    """Vertex sets of the separate pieces of ``shape`` lying in front of the plane
    ``z = face`` within ``radius`` of the axis (the emblem standing on the disc).

    Pieces are triangles joined by shared indices or by equal positions (split
    normals and UV seams), over every LOD.
    """
    shapes = _shapes(model)
    if shape not in shapes:
        raise ValueError('Shape not found in the model: ' + shape)
    points = [struct.unpack_from('<3e', model, address) for address in shapes[shape]['positions']]
    parent = list(range(len(points)))

    def root(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    def join(a, b):
        a, b = root(a), root(b)
        if a != b:
            parent[a] = b

    for indices in shapes[shape]['meshes']:
        for t in range(0, len(indices) - 2, 3):
            join(indices[t], indices[t + 1])
            join(indices[t], indices[t + 2])
    seen = {}
    for vertex, point in enumerate(points):
        join(vertex, seen.setdefault(point, vertex))
    pieces = {}
    for vertex in range(len(points)):
        pieces.setdefault(root(vertex), []).append(vertex)
    return [piece for piece in pieces.values()
            if len(piece) > 3 and all(points[v][2] >= face and points[v][0] ** 2 + points[v][1] ** 2 < radius ** 2
                                      for v in piece)]


def remove_relief(model, relief=RELIEF):
    """Collapse the emblem pieces standing on the disc to the origin (inside the disc)."""
    data = bytearray(model)
    islands = relief_islands(data, *relief)
    if not islands:
        raise ValueError('No relief found on ' + relief[0])
    addresses = _shapes(data)[relief[0]]['positions']
    for piece in islands:
        for vertex in piece:
            data[addresses[vertex]:addresses[vertex] + 6] = bytes(6)
    return bytes(data)


def build_model_files(read_raw):
    """New raw resources of the Archipelago medallion: ``{path: (raw, template_path)}``."""
    files = {}
    for suffix in REPLACED:
        source = SOURCES.get(suffix, f'Tex/{OLD_TEX}_{suffix}.bntx.zs')
        old_name = source[len('Tex/'):-len('.bntx.zs')]
        raw = rename(read_raw(source), old_name, f'{NEW_TEX}_{suffix}')
        info = bntx_info(raw)
        if suffix == 'Alb':
            if (info['format'], info['width'], info['height']) != (BC1, SHEET, SHEET):
                raise ValueError('Unexpected albedo container for the Archipelago medallion.')
            raw, painted = paint_bntx(raw, albedo_block)
        elif suffix == 'Mtl':
            if (info['format'], info['width']) != (BC4, SHEET):
                raise ValueError('Unexpected metalness texture for the Archipelago medallion.')
            raw, painted = paint_bntx(raw, metal_block)
        else:
            value = {'AO': bc4_constant(OCCLUSION), 'Rgh': bc4_constant(ROUGHNESS),
                     'Emc': void_extent((0, 0, 0, 255)), 'Nrm': void_extent(FLAT_NORMAL)}[suffix]
            raw, painted = fill_bntx(raw, value), 1
        if not painted:
            raise ValueError(f'Archipelago texture left unchanged: {suffix}')
        files[f'Tex/{NEW_TEX}_{suffix}.bntx.zs'] = (raw, source)
    model = remove_relief(hide_shapes(read_raw(MODEL_FILE)))
    for suffix in REPLACED:
        name = f'{OLD_TEX}_{suffix}'
        if model.count(name.encode()) != 1:
            raise ValueError(f'Unexpected medallion model: {name}')
        model = rename(model, name, f'{NEW_TEX}_{suffix}')
    files[NEW_MODEL_FILE] = (model, MODEL_FILE)
    return files


def spin_parts(read_raw):
    """Pack files, component references and ActorInfo values making the held item spin."""
    from oot_rando.formats import byml_codec
    from oot_rando.formats.inspect_resources import sarc
    pack = sarc(read_raw(f'Pack/Actor/{SPIN_TEMPLATE}.pack.zs'))
    as_info = 'Component/ASInfo/Item_GetDemo.engine__component__ASInfo.bgyml'
    if as_info not in pack:
        raise ValueError('Get-item animation settings not found.')
    animation = 'Component/AnimationParam/Item_AP_Spin.engine__component__AnimationParam.bgyml'
    files = {as_info: pack[as_info],
             animation: byml_codec.dump({'endian': '<', 'version': 7, 'root': {
                 'AnimationResources': [{'ModelProjectName': SPIN_ANIMATION}]}})}
    components = {'ASRef': SPIN_AS, 'ASInfoRef': '?' + as_info, 'AnimationRef': '?' + animation}
    return files, components, {'AnimationResources': [{'ModelProjectName': SPIN_ANIMATION}]}


def build_ap_files(read_raw, items, message_archives=()):
    """``(modified, new)`` resources for these foreign items: {planner item: (item name, player)}."""
    from oot_rando.patching.soul_adapter import build_item_files, soul_event_ain, soul_event_member, \
        soul_event_name
    spin_files, spin_components, spin_info = spin_parts(read_raw)
    specs = []
    for item, (name, player) in sorted(items.items()):
        actor = ap_actor(item)
        specs.append({'actor': actor, 'model': MODEL_ACTOR, 'model_info': MODEL_INFO,
                      'files': spin_files, 'components': spin_components, 'actor_info': spin_info,
                      'event_name': soul_event_name(actor), 'event_member': soul_event_member(actor),
                      'event_ain': soul_event_ain(actor),
                      'texts': (lambda lang, name=name, player=player: ap_messages(name, player, lang))})
    modified, new = build_item_files(read_raw, specs, message_archives)
    new.update(build_model_files(read_raw))
    return modified, new
