"""Archipelago item: items of other players shown as a medallion with the Archipelago logo.

Model: a copy of the Fire Medallion (``Model/Item_Medal_Fire.Item_Medal_Fire.bfres``)
under another project name, whose albedo, emission and normal textures are
renamed (same length, so no offset moves). The new textures are the medallion's
own BNTX files with their pixels rewritten in place:

* albedo (ASTC 8x6): both faces of the disc become a cream face with the logo
  and a golden rim; the rest of the sheet (edge, ribbon) is kept;
* emission (ASTC 12x12): black (no fire glow);
* normal (ASTC 5x5): flat on both faces (no engraving under the logo).

Every block written is an ASTC *void-extent* block (one constant colour), so no
ASTC encoder is needed: the logo is a flat-coloured drawing, sampled once per
block with light supersampling for the edges.

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
REPLACED = ('Alb', 'Emc', 'Nrm')
# Faces of the disc on the albedo sheet (pixels of the 576x576 texture): centre, radius.
FACES = ((153, 152), (377, 375))
FACE_RADIUS = 134
RIM = 0.86                            # inner radius of the golden rim, relative to the face
CREAM, GOLD = (243, 234, 212), (205, 160, 74)
FLAT_NORMAL = (128, 128, 128, 128)
# Archipelago logo in a 512x512 frame: six circles drawn in this order, each with
# a background-coloured halo that cuts the circles drawn before it.
LOGO_CIRCLES = (((255.5, 102), (201, 118, 130)), ((110, 183), (238, 227, 145)), ((400.5, 183), (117, 194, 117)),
                ((111, 325), (118, 126, 189)), ((400, 325), (202, 148, 194)), ((255.5, 410), (217, 160, 125)))
LOGO_RADIUS, LOGO_HALO = 100, 125
ASTC_BLOCKS = {0x2d: (4, 4), 0x2e: (5, 4), 0x2f: (5, 5), 0x30: (6, 5), 0x31: (6, 6), 0x32: (8, 5), 0x33: (8, 6),
               0x34: (8, 8), 0x35: (10, 5), 0x36: (10, 6), 0x37: (10, 8), 0x38: (10, 10), 0x39: (12, 10),
               0x3a: (12, 12)}


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


# ------------------------------------------------------------------ logo
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
    if distance > FACE_RADIUS * RIM:
        return GOLD
    inner = FACE_RADIUS * RIM * 0.92
    scale = 512 / (2 * inner)
    colour = logo_colour(256 + dx * scale, 256 + dy * scale)
    return colour or CREAM


def albedo_block(x0, y0, width, height, samples=3):
    """Average colour of a block of the albedo sheet, or None when the block is not on a face."""
    reach = FACE_RADIUS + (width * width + height * height) ** 0.5
    for cx, cy in FACES:
        if (x0 + width / 2 - cx) ** 2 + (y0 + height / 2 - cy) ** 2 > reach * reach:
            continue
        colours = []
        for i in range(samples):
            for j in range(samples):
                colour = face_colour(x0 + (i + 0.5) * width / samples - cx, y0 + (j + 0.5) * height / samples - cy)
                if colour is not None:
                    colours.append(colour)
        if len(colours) * 2 >= samples * samples:   # mostly on the face: the face wins
            return tuple(round(sum(c[k] for c in colours) / len(colours)) for k in range(3)) + (255,)
    return None


# ------------------------------------------------------------------ ASTC and BNTX
def void_extent(rgba):
    """ASTC LDR void-extent block: one constant colour (8-bit channels)."""
    return bytes.fromhex('fcfdffffffffffff') + struct.pack('<4H', *(c * 257 for c in rgba))


def _block_address(x, y, gob_height, width_gobs, bpe=16):
    """Byte address of element (x, y) in Tegra block-linear layout (see icon_extract.deblock_linear)."""
    gob_row = (y // (8 * gob_height)) * 512 * gob_height * width_gobs + ((y % (8 * gob_height)) // 8) * 512
    y_in = (y & 1) * 16 + ((y >> 1) & 1) * 32 + ((y >> 2) & 1) * 128
    return gob_row + (x // 4) * 512 * gob_height + y_in + (x & 1) * 64 + ((x >> 1) & 1) * 256


def bntx_info(data):
    """Texture header of a single-texture BNTX: name, format, size, layout and mip levels."""
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


def paint_bntx(data, block_colour):
    """Rewrite every mip level in place.

    ``block_colour(x0, y0, w, h)`` gets a block in level-0 pixels and returns RGBA,
    or None to keep the block. Only GOB height 1 is handled (it never grows with
    the mip levels, so every level uses the same addressing).
    """
    info = bntx_info(data)
    if info['format'] not in ASTC_BLOCKS:
        raise ValueError(f'Unsupported texture format {info["format"]:#x}.')
    if info['gob_height'] != 1:
        raise ValueError('Unsupported texture layout (GOB height above 1).')
    bw, bh = ASTC_BLOCKS[info['format']]
    out = bytearray(data)
    painted = 0
    end = info['start'] + info['size']
    for level, start in enumerate(info['levels']):
        width, height = max(1, info['width'] >> level), max(1, info['height'] >> level)
        width_blocks, height_blocks = -(-width // bw), -(-height // bh)
        width_gobs = -(-width_blocks * 16 // 64)
        scale = 1 << level
        for y in range(height_blocks):
            for x in range(width_blocks):
                colour = block_colour(x * bw * scale, y * bh * scale, bw * scale, bh * scale)
                if colour is None:
                    continue
                address = start + _block_address(x, y, 1, width_gobs)
                if address + 16 > end:
                    raise ValueError('Texture block outside the image data.')
                out[address:address + 16] = void_extent(colour)
                painted += 1
    return bytes(out), painted


def rename(data, old, new):
    """Same-length rename of every occurrence of a name (offsets unchanged)."""
    old, new = old.encode(), new.encode()
    if len(old) != len(new):
        raise ValueError('Renamed resources must keep their name length.')
    if not data.count(old):
        raise ValueError(f'Name not found: {old.decode()}')
    return data.replace(old, new)


def build_model_files(read_raw):
    """New raw resources of the Archipelago medallion: ``{path: (raw, template_path)}``."""
    files = {}
    for suffix in REPLACED:
        source = f'Tex/{OLD_TEX}_{suffix}.bntx.zs'
        raw = rename(read_raw(source), f'{OLD_TEX}_{suffix}', f'{NEW_TEX}_{suffix}')
        if suffix == 'Alb':
            raw, painted = paint_bntx(raw, albedo_block)
        elif suffix == 'Emc':
            raw, painted = paint_bntx(raw, lambda *block: (0, 0, 0, 255))
        else:
            scale = bntx_info(raw)['width'] / 576

            def flat(x0, y0, w, h, scale=scale):
                inside = any(((x0 + w / 2) / scale - cx) ** 2 + ((y0 + h / 2) / scale - cy) ** 2
                             <= (FACE_RADIUS + 2) ** 2 for cx, cy in FACES)
                return FLAT_NORMAL if inside else None
            raw, painted = paint_bntx(raw, flat)
        if not painted:
            raise ValueError(f'Archipelago texture left unchanged: {suffix}')
        files[f'Tex/{NEW_TEX}_{suffix}.bntx.zs'] = (raw, source)
    model = read_raw(MODEL_FILE)
    for suffix in REPLACED:
        name = f'{OLD_TEX}_{suffix}'.encode()
        if model.count(name) != 1:
            raise ValueError(f'Unexpected medallion model: {name.decode()}')
        model = rename(model, f'{OLD_TEX}_{suffix}', f'{NEW_TEX}_{suffix}')
    files[NEW_MODEL_FILE] = (model, MODEL_FILE)
    return files


def build_ap_files(read_raw, items, message_archives=()):
    """``(modified, new)`` resources for these foreign items: {planner item: (item name, player)}."""
    from oot_rando.patching.soul_adapter import build_item_files, soul_event_ain, soul_event_member, \
        soul_event_name
    specs = []
    for item, (name, player) in sorted(items.items()):
        actor = ap_actor(item)
        specs.append({'actor': actor, 'model': MODEL_ACTOR, 'model_info': MODEL_INFO,
                      'event_name': soul_event_name(actor), 'event_member': soul_event_member(actor),
                      'event_ain': soul_event_ain(actor),
                      'texts': (lambda lang, name=name, player=player: ap_messages(name, player, lang))})
    modified, new = build_item_files(read_raw, specs, message_archives)
    new.update(build_model_files(read_raw))
    return modified, new
