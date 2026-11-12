"""In-game test: does the game re-read a mod file rewritten while it runs?

Item reception without any emulator- or Hookshot-specific feature would rely on
the client rewriting a mod file that the game reads again later. This tool
rewrites one small, repeatable event of an installed seed: the Kokiri Forest
message board (``Obj_Kokiri_MessageBoard_A_01``, read at will). After its text,
variant ``a`` silently adds one Deku Nut, variant ``b`` removes one; ``off``
puts back the seed's own file (or removes it: the seed did not change it).

Procedure: install ``a``, read the board (+1 nut), install ``b`` with the game
still running, read it again. -1 nut: the file is read again for each event.
Otherwise leave the forest and come back, then restart the game, to see when
the new file is taken.

``python -m oot_rando reload-test GAME.nup SEED_FOLDER a|b|off``
"""
import json
from pathlib import Path

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import decompress, dictionaries
from oot_rando.game.resource_allocations import allocation, grow_resources
from oot_rando.game.world_maps import effective_members
from oot_rando.patching.event_patch import add_pouch_items
from oot_rando.patching.randomize_kokiri import RESTBL

FLOW = 'Event/EventFlow/Obj_Kokiri_MessageBoard_A_01.bfevfl.zs'
ANCHOR = 'Event1'            # Talk: Event0 (the board's text) → Event1 (action guide) → end
ITEM = 'Item_DekuNut'
VARIANTS = {'a': 1, 'b': -1}  # nuts added / removed (the only Num values of the vanilla flows)
LEVEL = 15                   # zstd level giving both variants the same file size (556 bytes)
STATE = 'reload_test.json'   # beside the seed's manifest: what to restore


def _compress(raw, original, dicts, level=10):
    import zstandard as zstd
    ident = zstd.get_frame_parameters(original).dict_id
    matched = [zstd.ZstdCompressionDict(v) for v in dicts.values()
               if zstd.ZstdCompressionDict(v).dict_id() == ident] if ident else []
    if ident and len(matched) != 1:
        raise ValueError('Compression dictionary ambiguous or missing.')
    encoded = zstd.ZstdCompressor(level=level, dict_data=matched[0] if matched else None).compress(raw)
    if decompress(encoded, dicts) != raw:
        raise ValueError('Recompression check failed.')
    return encoded


def seed_original(seed, name, data):
    """The seed's own bytes of resource ``name`` while the test is installed (else ``data``)."""
    backup = Path(seed) / (STATE + '.restbl')
    if name == RESTBL and (Path(seed) / STATE).is_file() and backup.is_file():
        return backup.read_bytes()
    return data


def variant_flow(vanilla_raw, variant):
    """Board flow of a variant (decompressed bytes)."""
    import io
    import evfl
    from oot_rando.patching.event_patch import starting_item_events
    raw = add_pouch_items(vanilla_raw, ANCHOR, [ITEM])
    if VARIANTS[variant] == 1:
        return raw
    flow = evfl.EventFlow()
    flow.read(raw)
    name = starting_item_events([ITEM])[0]
    event = next(e for e in flow.flowchart.events if e.name == name)
    event.data.params.data['Num'] = VARIANTS[variant]
    stream = io.BytesIO()
    flow.write(stream)
    return stream.getvalue()


def install(nup_path, seed, variant):
    seed = Path(seed)
    if not (seed / 'manifest.json').is_file() or not (seed / 'romfs').is_dir():
        raise ValueError('Not an installed seed folder (manifest.json + romfs/).')
    if variant not in (*VARIANTS, 'off'):
        raise ValueError('Variant: a, b or off.')
    target, rest_path, state_path = seed / 'romfs' / FLOW, seed / 'romfs' / RESTBL, seed / STATE
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.is_file() else None
    if state is None:
        if target.exists():
            raise ValueError('This seed already changes the board flow: choose another seed.')
        state = {'restbl_backup': rest_path.is_file()}
        if rest_path.is_file():
            (seed / (STATE + '.restbl')).write_bytes(rest_path.read_bytes())
    if variant == 'off':
        if target.exists():
            target.unlink()
        backup = seed / (STATE + '.restbl')
        if state.get('restbl_backup') and backup.is_file():
            rest_path.write_bytes(backup.read_bytes())
            backup.unlink()
        elif rest_path.is_file() and not state.get('restbl_backup'):
            rest_path.unlink()
        if state_path.exists():
            state_path.unlink()
        return 'Board flow restored.'
    nup = Nup(nup_path)
    try:
        dicts, members = dictionaries(nup), effective_members(nup)
        source = nup.read(members[FLOW])
        vanilla = decompress(source, dicts)
        raw = variant_flow(vanilla, variant)
        encoded = _compress(raw, source, dicts, LEVEL)
        vanilla_rest_source = nup.read(members[RESTBL])
        vanilla_rest = decompress(vanilla_rest_source, dicts)
        current_source = rest_path.read_bytes() if rest_path.is_file() else vanilla_rest_source
        current_rest = decompress(current_source, dicts)
        before = allocation(current_rest, FLOW)
        # Grow once (both variants have the same size); never grow an already grown entry.
        sizes = {v: len(_compress(variant_flow(vanilla, v), source, dicts, LEVEL)) for v in VARIANTS}
        if len(set(sizes.values())) != 1:
            raise ValueError(f'Variants of different sizes: {sizes}')
        longest = max(len(variant_flow(vanilla, v)) for v in VARIANTS)
        if before == allocation(vanilla_rest, FLOW) and longest > len(vanilla):
            current_rest, _ = grow_resources(current_rest, {FLOW: longest - len(vanilla)})
            rest_path.parent.mkdir(parents=True, exist_ok=True)
            rest_path.write_bytes(_compress(current_rest, current_source, dicts))
    finally:
        nup.stream.close()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_bytes(encoded)
    temporary.replace(target)   # same size for both variants: only the content changes
    state['variant'] = variant
    state_path.write_text(json.dumps(state), encoding='utf-8')
    return f'Variant {variant} installed: the board now changes the Deku Nuts by {VARIANTS[variant]:+d}.'


def main(argv):
    if len(argv) != 3:
        print('Usage: reload-test GAME.nup SEED_FOLDER a|b|off')
        return 2
    print(install(*argv))
    return 0
