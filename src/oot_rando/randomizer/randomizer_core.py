"""Versioned local generator: prudent adapters plus the complete AP-glitchless mode.

RNG protocol sha256-counter-v1 hashes canonical settings + a big-endian counter,
then uses rejection sampling. It does not depend on Python's random implementation.
When ``Settings.full`` is set, every chest is placed by the glitchless solver of
``full_randomizer`` (AP OoT rules read from the local Archipelago installation)
and verified by an independent sweep before any file is written.
"""
from dataclasses import dataclass, field, fields
import hashlib
import json
from pathlib import Path
import tempfile

import zstandard as zstd

from oot_rando.formats.inspect_nup import Nup
from oot_rando.formats.inspect_resources import Byml, decompress, dictionaries, sarc
from oot_rando.patching.randomize_kokiri import BUILD, TITLE, MAP, RESTBL, CHESTS, POOL, check_supported_game, patch_map
from oot_rando.patching.qol_patches import (STATIC, STATIC_SOURCE_SHA256, DYNAMIC_SOURCE_SHA256, PHYSICS, EVENT_SETTINGS,
                         patch_forest, patch_baked_wall, sha256, cutscene_files, patch_dialogues,
                         area_presentation_files, quick_chest, CHEST_FLOW,
                         quick_small_chest, SMALL_CHEST_FLOW,
                         KOKIRI_SHOP_MAPS, KOKIRI_SHOP_PACKS, open_kokiri_shop,
                         release_kokiri_shop_goods, BOMB_LIFT_PACKS, free_bomb_lift,
                         DC_BOULDER_MODULE, let_bombs_break_dc_boulder, SCRUB_FLOW, keep_one_scrub_good,
                         ACTION_GUIDE_FLOW, ocarina_guide_on_get,
                         SWORD_CHEST_FLOW, skip_kokiri_sword_cutscene,
                         NOCTURNAL_SKULLTULA_MAPS, nocturnal_skulltula_edits)
from oot_rando.game.randomizer_categories import CATEGORIES
from oot_rando.game.world_maps import SAFE_CATEGORIES, build_world, effective_members
from oot_rando.game.resource_allocations import allocation, grow_resources, add_resources
from oot_rando.formats.byml_writer import patch_strings
from oot_rando.logic import rando_options

GENERATOR_VERSION = '0.8.0'
ADAPTER_VERSION = 'ap-glitchless-v4'   # v4: short key ring / boss key / regional soul actor names
ADULT_MAP = MAP.replace('_Child_', '_Adult_')
STARTING_ITEMS = ('Item_BulletBag_Small', 'Item_Quiver_Small')


def ap_records(settings):
    """Reception records of an Archipelago seed (items of this game found in other worlds)."""
    if settings.archipelago is None or not settings.archipelago.get('remote'):
        return []
    from oot_rando.patching.ap_mailbox import records
    return records(settings.archipelago['remote'])


def starting_pouch_items(full):
    """Actors given silently at the end of the opening: bag, quiver, starting items.

    Starting items come from the Archipelago patch, else from the starting
    inventory option (solo seed, ``full['starting']``).
    """
    full = full or {}
    starting = (full.get('archipelago') or {}).get('starting') if full.get('archipelago') else full.get('starting')
    return list(STARTING_ITEMS) + [s['actor'] for s in starting or []]
# Archipelago goal flag: after Defeat_Ganon's native "Complete" step (Ganon's death),
# before the transition to Dm_Ending_0000.
GOAL_FLOW, GOAL_EVENT = 'Event/EventFlow/Defeat_Ganon.bfevfl.zs', 'Event37'
GOAL_MARKER_PREFIX = 'RandoGoal.'
SEED_MARKER_PREFIX = 'RandoSeed.'


def save_marker(manifest):
    """Name of the saved flag that binds a save to this seed (set by the new-game opening)."""
    return SEED_MARKER_PREFIX + str(manifest.get('save_seed_id') or manifest.get('seed_id', ''))
CHECKS = [{'id': str(ident), 'region': 'Kokiri Forest',
           'name': f'Four-chest house — slot {i + 1}'}
          for i, ident in enumerate(sorted(CHESTS))]
PRUDENT_POOL = [name for name in POOL if name.startswith('TBox_Rupee_')]
SKIP_OPTIONS = ('skip_locked_cutscenes', 'skip_auto_dialogues', 'skip_chest_cutscenes')
# Omitted from ``to_dict`` while False (earlier seeds keep their identity).
OPTIONAL_SKIPS = SKIP_OPTIONS + ('skulltulas_always_present',)
# Removed options (≤ 0.7): their patches are part of the broader skips.
LEGACY_SKIPS = {'skip_intro': 'skip_locked_cutscenes'}
# Removed without replacement: NPC dialogue skips crashed in game (turbo A instead).
DROPPED_SKIPS = ('skip_saria_dialogue', 'skip_npc_dialogues')


@dataclass
class Settings:
    seed: str
    randomize_chests: bool = True
    pool: list[str] = field(default_factory=lambda: list(PRUDENT_POOL))
    excluded_checks: list[str] = field(default_factory=list)
    avoid_vanilla: bool = True
    open_forest: bool = True
    # Omitted from ``to_dict`` while False. ``skip_locked_cutscenes`` covers the intro,
    # every other locked cutscene and the area presentations.
    skip_locked_cutscenes: bool = False
    skip_auto_dialogues: bool = False
    # Big chests: lid animation, Link holds the item up, no chest performance.
    skip_chest_cutscenes: bool = False
    # Night-only gold skulltulas present day and night (the logic stays unchanged).
    skulltulas_always_present: bool = False
    categories: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(CATEGORIES, False))
    full: dict | None = None
    # Archipelago patch (``.aprmk`` content): the placements come from a multiworld.
    archipelago: dict | None = None

    def validate(self):
        if not isinstance(self.seed, str) or not self.seed.strip() or len(self.seed) > 256:
            raise ValueError('The seed must be a non-empty text of at most 256 characters.')
        for name in ('randomize_chests', 'avoid_vanilla', 'open_forest') + OPTIONAL_SKIPS:
            if type(getattr(self, name)) is not bool:
                raise ValueError(f'{name} must be a boolean.')
        for name, allowed in [('pool', set(POOL)), ('excluded_checks', {str(h) for h in CHESTS})]:
            values = getattr(self, name)
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError(f'{name} must be a list of texts.')
            if len(values) != len(set(values)) or not set(values) <= allowed:
                raise ValueError(f'{name} holds an unknown or duplicate value.')
        if (not isinstance(self.categories, dict) or set(self.categories) - set(CATEGORIES)
                or any(type(v) is not bool for v in self.categories.values())):
            raise ValueError('Unknown categories or non-boolean values.')
        if self.full is not None:
            self.full = rando_options.validate(self.full)
            if self.randomize_chests or self.categories.get('world_chests'):
                raise ValueError('The full randomizer handles every chest: disable the four Kokiri '
                                 'chests and the Ordinary chests category.')
            overlap = [CATEGORIES[name] for name, option, off in (
                ('pots', 'shuffle_pots', 'off'), ('bushes', 'shuffle_bushes', False), ('rocks', 'shuffle_rocks', False))
                if self.categories.get(name) and self.full.get(option, off) != off]
            if overlap:
                raise ValueError('These categories are already shuffled as checks by the full randomizer: '
                                 + ', '.join(overlap) + '. Untick the matching cosmetic category.')
        if self.archipelago is not None:
            from oot_rando.archipelago.bridge import check_patch
            check_patch(self.archipelago)
            if self.full is None or self.full != rando_options.validate(self.archipelago['options']):
                raise ValueError('The full randomizer options must be those of the Archipelago patch.')
            if self.open_forest != self.archipelago['open_forest']:
                raise ValueError('"Open the way" must match the Archipelago patch.')
        if self.randomize_chests:
            for ident, original in CHESTS.items():
                if str(ident) not in self.excluded_checks and not [v for v in self.pool if not self.avoid_vanilla or v != original]:
                    raise ValueError('The pool cannot fill every active chest.')
        if not (self.full is not None or any(self.categories.values()) or self.open_forest
                or any(getattr(self, name) for name in OPTIONAL_SKIPS)
                or (self.randomize_chests and len(self.excluded_checks) < len(CHESTS))):
            raise ValueError('Enable at least one option or chest to randomize to generate a mod.')
        return self

    def validate_supported(self):
        self.validate()
        if self.randomize_chests and any(name not in PRUDENT_POOL for name in self.pool):
            raise ValueError('Rewards other than rupees are disabled in the first prudent release. Use the prudent profile.')
        if self.full is not None:
            rando_options.validate(self.full, supported_only=True)
        pending = [CATEGORIES[name] for name, enabled in self.categories.items() if enabled and name not in SAFE_CATEGORIES]
        if pending:
            raise ValueError('Adapters still to be written for: ' + ', '.join(pending)
                             + '. Settings can be exported; no partial seed is produced.')
        return self

    def to_dict(self):
        self.validate()
        # ``full`` is omitted when unset so that earlier seeds keep their identity.
        return {f.name: (sorted(getattr(self, f.name)) if f.name in ('pool', 'excluded_checks')
                        else {name: self.categories.get(name, False) for name in sorted(CATEGORIES)}
                        if f.name == 'categories' else dict(sorted(self.full.items()))
                        if f.name == 'full' else getattr(self, f.name))
                for f in fields(self) if not (f.name in ('full', 'archipelago') and getattr(self, f.name) is None)
                and not (f.name in OPTIONAL_SKIPS and not getattr(self, f.name))}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError('Unknown settings or invalid format.')
        value = dict(value)
        for dropped in DROPPED_SKIPS:
            value.pop(dropped, None)
        for legacy, current in LEGACY_SKIPS.items():
            if legacy in value:
                enabled = value.pop(legacy)
                if type(enabled) is not bool:
                    raise ValueError(f'{legacy} must be a boolean.')
                value[current] = bool(value.get(current, False)) or enabled
        if set(value) - {f.name for f in fields(cls)}:
            raise ValueError('Unknown settings or invalid format.')
        if 'seed' not in value:
            raise ValueError('The seed is required.')
        return cls(**value).validate()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def settings_identity(settings, generator_version=GENERATOR_VERSION, adapter_version=ADAPTER_VERSION):
    return sha256(_canonical({'generator': generator_version, 'adapter': adapter_version,
                              'settings': settings.to_dict()}))


def placements_for(settings):
    """Complete map, including original values for excluded/disabled checks."""
    settings.validate()
    key = bytes.fromhex(settings_identity(settings))
    counter = 0
    result = dict(CHESTS)
    if settings.randomize_chests:
        for ident in sorted(CHESTS):
            if str(ident) in settings.excluded_checks:
                continue
            choices = sorted(v for v in settings.pool if not settings.avoid_vanilla or v != CHESTS[ident])
            limit = (1 << 256) - ((1 << 256) % len(choices))
            while True:
                sample = int.from_bytes(hashlib.sha256(key + counter.to_bytes(8, 'big')).digest(), 'big')
                counter += 1
                if sample < limit:
                    result[ident] = choices[sample % len(choices)]
                    break
    return result


def source_reader(nup, members, sources):
    """``read(path, expected_sha256=None)``: a resource of the game; its hash is recorded in ``sources``."""
    def read(path, expected=None):
        data = nup.read(members[path])
        sources[path] = sha256(data)
        if expected and sources[path] != expected:
            raise ValueError(f'Unexpected source resource: {path}')
        return data
    return read


def recompress(raw, original, dictionaries_):
    """Compress ``raw`` with the dictionary of the resource it replaces, and check the round trip."""
    ident = zstd.get_frame_parameters(original).dict_id
    candidates = [zstd.ZstdCompressionDict(v) for v in dictionaries_.values()]
    matched = [v for v in candidates if v.dict_id() == ident] if ident else []
    if ident and len(matched) != 1:
        raise ValueError('Compression dictionary ambiguous or missing.')
    encoded = zstd.ZstdCompressor(level=10, dict_data=matched[0] if matched else None).compress(raw)
    if decompress(encoded, dictionaries_) != raw:
        raise ValueError('Recompression check failed.')
    return encoded


def complete_event_info(extra_raw, nup, members, d, read):
    """Events load only the external sub-flows listed for them: a changed flow that
    calls a new flowchart (the Deku Tree gift's Dm_SY_GetInEvent) gets it listed.

    Updates ``extra_raw`` in place and returns the summary of what was added."""
    from oot_rando.patching.event_info import (GAME_ANALYZED_EVENT_INFO, add_child_events,
                                                add_subflow_dependencies, flow_name, flow_path,
                                                new_subflows, new_transitions)
    skips = {}
    changed_flows = {flow_name(p): raw for p, raw in extra_raw.items() if flow_name(p)}
    vanilla_cache = {}

    def vanilla_flow(name):
        if name not in vanilla_cache:
            path = flow_path(name)
            vanilla_cache[name] = decompress(nup.read(members[path]), d) if path in members else None
        return vanilla_cache[name]
    added_calls = new_subflows(changed_flows, vanilla_flow)
    current_named = lambda name: changed_flows.get(name) or vanilla_flow(name)
    if added_calls:
        extra_raw[GAME_ANALYZED_EVENT_INFO], skips['subflow_dependencies'] = add_subflow_dependencies(
            decompress(read(GAME_ANALYZED_EVENT_INFO), d), Byml(decompress(read(EVENT_SETTINGS), d)).root,
            added_calls, current_named)
    # Same for the events a changed flow now starts by EventTransition (the ocarina
    # guide's Dm_SY_Ocarina after every item get).
    added_events = new_transitions(changed_flows, vanilla_flow)
    if added_events:
        info_source = extra_raw.get(GAME_ANALYZED_EVENT_INFO) or decompress(read(GAME_ANALYZED_EVENT_INFO), d)
        extra_raw[GAME_ANALYZED_EVENT_INFO], skips['child_events'] = add_child_events(
            info_source, Byml(decompress(read(EVENT_SETTINGS), d)).root, added_events, current_named)
    return skips


def compress_changed(extra_raw, files, growths, read, d):
    """Recompress edited resources into ``files``; ``growths`` records how much each one grew."""
    for path, raw in sorted(extra_raw.items()):
        source = read(path)
        if not path.endswith('.zs'):       # stored uncompressed in the game (logic modules)
            growths[path] = max(len(raw) - len(source), 0)
            files[path] = raw
            continue
        growths[path] = max(len(raw) - len(decompress(source, d)), 0)
        files[path] = recompress(raw, source, d)


def grow_resource_table(files, growths, new_sizes, read, d):
    """Make room in the resource size table (RESTBL) for grown or new resources.

    Writes the new table into ``files`` and returns the changed allocations."""
    if not (any(growths.values()) or new_sizes):
        return []
    rest_source = read(RESTBL)
    rest, allocations = grow_resources(decompress(rest_source, d), growths)
    if new_sizes:
        rest, added = add_resources(rest, new_sizes)
        allocations += added
    files[RESTBL] = recompress(rest, rest_source, d)
    return allocations


def publish_mod(output, files, documents, finish=None):
    """Write a mod folder atomically: ``romfs/<path>`` for ``files``, then ``documents``
    (name to bytes or text), then whatever ``finish(staging)`` adds. ``output`` must not exist."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.oot-stage-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'ready'
        staging.mkdir()
        for path, data in files.items():
            destination = staging / 'romfs' / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        for name, data in documents.items():
            if isinstance(data, bytes):
                (staging / name).write_bytes(data)
            else:
                (staging / name).write_text(data, encoding='utf-8')
        if finish:
            finish(staging)
        staging.rename(output)


def json_document(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def generate(nup_path, output, settings, progress=None, save_seed_id=None):
    """Publish a complete new mod directory, never install or modify a game/save.

    ``save_seed_id``: an earlier seed of the same Archipelago slot whose saves this one
    continues (its save marker is kept); by default the seed binds its own saves."""
    settings.validate_supported()
    output = Path(output)
    if output.exists():
        raise ValueError('The output folder already exists. Choose a new folder.')
    report = progress or (lambda message: None)
    report('Checking the game and the settings…')
    nup = Nup(nup_path)
    try:
        check_supported_game(nup)
        d = dictionaries(nup)
        members = effective_members(nup)
        files, sources = {}, {}

        read = source_reader(nup, members, sources)

        def compress(path, raw, original):
            files[path] = recompress(raw, original, d)

        placements = placements_for(settings)
        raw_maps = {}
        world = {'checks': [], 'placements': [], 'coverage': {}}
        if any(settings.categories.values()):
            report('Randomizing the selected categories…')
            world = build_world(nup, d, settings.categories, settings_identity(settings), settings.avoid_vanilla, report)
            raw_maps.update(world['raw_maps'])
            sources.update(world['sources'])
        full = None
        extra_raw, new_files = {}, {}
        if settings.full is not None:
            full, extra_raw, new_files = _build_full(nup, d, members, settings, raw_maps, sources, read, report)
        chests = []
        active = settings.randomize_chests and len(settings.excluded_checks) < len(CHESTS)
        if active or settings.open_forest:
            source = read(MAP, DYNAMIC_SOURCE_SHA256)
            raw = raw_maps.get(MAP, decompress(source, d))
            if active:
                report('Composing chest rewards…')
                for reward in sorted(set(placements.values())):
                    pack = sarc(decompress(nup.read(nup.latest(f'romfs/Pack/Actor/{reward}.pack.zs')), d))
                    Byml(pack[f'Actor/{reward}.engine__actor__ActorParam.bgyml'])
                raw, chests = patch_map(raw, placements)
                # One logical check must have the same reward in both native ages.
                adult_source = read(ADULT_MAP)
                adult_raw = raw_maps.get(ADULT_MAP, decompress(adult_source, d))
                raw_maps[ADULT_MAP], _ = patch_map(adult_raw, placements)
            if settings.open_forest:
                report('Opening the way to Hyrule and fixing collision…')
                static_source = read(STATIC, STATIC_SOURCE_SHA256)
                static, raw = patch_forest(raw_maps.get(STATIC, decompress(static_source, d)), raw)
                raw_maps[STATIC] = static
                physics_source = read(PHYSICS)
                physics, _ = patch_baked_wall(decompress(physics_source, d))
                compress(PHYSICS, physics, physics_source)
            raw_maps[MAP] = raw
        if settings.skulltulas_always_present:
            report('Night skulltulas present day and night…')
            nocturnal = 0
            for path in NOCTURNAL_SKULLTULA_MAPS:
                current = raw_maps[path] if path in raw_maps else decompress(read(path), d)
                edits = nocturnal_skulltula_edits(Byml(current).root)
                if edits:
                    raw_maps[path], nocturnal = patch_strings(current, edits), nocturnal + len(edits)
            if not nocturnal:
                raise ValueError('Night skulltulas not found in the maps.')
        from oot_rando.game.tracking_metadata import GAMEDATA, add_saved_flags, build_tracking, reward_label
        from oot_rando.patching.soul_adapter import murmur3
        marker_name = SEED_MARKER_PREFIX + (save_seed_id or settings_identity(settings))
        if settings.full is not None:
            report('Opening the full Kokiri shop…')
            opened = 0
            for path in KOKIRI_SHOP_MAPS:
                current = raw_maps.get(path)
                if current is None:
                    current = decompress(read(path), d)
                patched, count = open_kokiri_shop(current, marker_name)
                if count:
                    raw_maps[path], opened = patched, opened + count
            if not opened:
                raise ValueError('Kokiri shop not found in the maps.')
            released = 0
            for path in KOKIRI_SHOP_PACKS:
                current = extra_raw.get(path)
                if current is None:
                    current = decompress(read(path), d)
                patched, count = release_kokiri_shop_goods(current)
                if count:
                    extra_raw[path], released = patched, released + count
            if not released:
                raise ValueError('Kokiri shop sale conditions not found.')
            # The bomb bag can come before the Goron Bracelet: bombs must not need it.
            freed = 0
            for path in BOMB_LIFT_PACKS:
                current = extra_raw.get(path)
                if current is None:
                    current = decompress(read(path), d)
                patched, count = free_bomb_lift(current)
                if count:
                    extra_raw[path], freed = patched, freed + count
            if not freed:
                raise ValueError('Bomb lift parameter not found.')
            # The bomb bag can come before the Goron Bracelet: Link's bombs break the
            # Dodongo's Cavern boulder, not only the bomb flower (raw file, not compressed).
            extra_raw[DC_BOULDER_MODULE], dc_boulder = let_bombs_break_dc_boulder(
                extra_raw.get(DC_BOULDER_MODULE) or read(DC_BOULDER_MODULE))
            # Items found in any order: a refill scrub may have no good Link can use yet.
            extra_raw[SCRUB_FLOW], scrub_goods = keep_one_scrub_good(
                extra_raw.get(SCRUB_FLOW) or decompress(read(SCRUB_FLOW), d))
            # The Fairy Ocarina can come before the Deku Tree: it gets the vanilla
            # ocarina guide (normally shown in Hyrule Field after the bridge) on item get.
            extra_raw[ACTION_GUIDE_FLOW], ocarina_guide = ocarina_guide_on_get(
                extra_raw.get(ACTION_GUIDE_FLOW) or decompress(read(ACTION_GUIDE_FLOW), d))
            if full.get('key_items'):
                # Key rings / dungeon boss keys: applied at the end of every item get.
                from oot_rando.patching.key_adapter import add_key_hook
                extra_raw[ACTION_GUIDE_FLOW], key_hook = add_key_hook(extra_raw[ACTION_GUIDE_FLOW],
                                                                      full['key_items'])
            # The Kokiri Sword chest no longer hands over (and equips) the sword
            # through its cutscene whatever it contains.
            extra_raw[SWORD_CHEST_FLOW], sword_chest = skip_kokiri_sword_cutscene(
                extra_raw.get(SWORD_CHEST_FLOW) or decompress(read(SWORD_CHEST_FLOW), d))
        gamedata_source = extra_raw.get(GAMEDATA)
        if gamedata_source is None:
            gamedata_source = decompress(read(GAMEDATA), d)
        goal_name = GOAL_MARKER_PREFIX + settings_identity(settings) if settings.archipelago is not None else None
        extra_raw[GAMEDATA] = add_saved_flags(gamedata_source, {marker_name: False,
                                                                **({goal_name: False} if goal_name else {})})
        # Bind a save only when the actual new-game opening completes. A True
        # default would incorrectly bind an old save when its missing flags initialize.
        from oot_rando.patching.event_patch import add_collection_markers
        opening = 'Event/EventFlow/OpeningEvent.bfevfl.zs'
        extra_raw[opening], seed_markers = add_collection_markers(
            decompress(read(opening), d), {'Event3': marker_name})
        goal_markers = []
        if goal_name:
            # Archipelago goal: set once Ganon's defeat completes the native challenge,
            # just before the ending cutscene (read live by the client: no save follows).
            extra_raw[GOAL_FLOW], goal_markers = add_collection_markers(
                extra_raw.get(GOAL_FLOW) or decompress(read(GOAL_FLOW), d), {GOAL_EVENT: goal_name})
        if settings.full is not None:
            # Seed bag and quiver (level 1) from the start: the slingshot and the
            # bow can come from any source (a shop slot never grants the bag).
            from oot_rando.patching.event_patch import add_pouch_items
            extra_raw[opening] = add_pouch_items(extra_raw[opening], 'RandoCollected_Event3',
                                                 starting_pouch_items(full))
            # Maps/compasses "start with", keys "removed": dungeon data written at the start.
            from oot_rando.patching.event_patch import add_start_values
            from oot_rando.patching.key_adapter import start_dungeon_values, check_start_values
            start_values = start_dungeon_values(settings.full)
            if start_values:
                check_start_values(extra_raw[GAMEDATA], start_values)
                extra_raw[opening] = add_start_values(extra_raw[opening], 'RandoCollected_Event3', start_values)
        skips = {}
        if settings.full is not None:
            skips['ocarina_guide'] = ocarina_guide
            skips['dc_boulder_bombs'] = dc_boulder
            skips['scrub_goods'] = scrub_goods
            if full.get('key_items'):
                skips['key_items'] = {'records': full['key_items'], 'hook': key_hook}
            skips['sword_chest'] = sword_chest
            if full.get('gift_get'):
                skips['gift_get'] = full['gift_get']
        current_flow = lambda path: extra_raw[path] if path in extra_raw else decompress(read(path), d)
        if settings.skip_locked_cutscenes:
            report('Skippable area presentations…')
            flows, skips['area_presentations'] = area_presentation_files(current_flow)
            extra_raw.update(flows)
        if settings.skip_chest_cutscenes or (settings.full or {}).get('fast_chests'):
            report('Chests without cutscene…')
            extra_raw[CHEST_FLOW], skips['quick_chest'] = quick_chest(current_flow(CHEST_FLOW))
            extra_raw[SMALL_CHEST_FLOW], skips['quick_small_chest'] = quick_small_chest(current_flow(SMALL_CHEST_FLOW))
        if settings.skip_locked_cutscenes:
            # Flow-driven cutscenes: native skip windows up to each
            # event, with idempotent state writes replayed when skipped. Analysed on
            # the original flows; flows already changed by another patch are left alone.
            report('Cutscenes skippable up to their events…')
            from oot_rando.patching.qol_patches import skip_window_candidates, cutscene_window_files
            flow_names = {p[len('Event/EventFlow/'):-len('.bfevfl.zs')] for p in members
                          if p.startswith('Event/EventFlow/') and p.endswith('.bfevfl.zs')}
            original_flow = lambda path: decompress(nup.read(members[path]), d)
            candidates = [n for n in skip_window_candidates(decompress(read(EVENT_SETTINGS), d))
                          if 'Event/EventFlow/' + n + '.bfevfl.zs' not in extra_raw]
            flows, skips['cutscene_windows'] = cutscene_window_files(original_flow, flow_names, candidates)
            extra_raw.update(flows)
        skips.update(complete_event_info(extra_raw, nup, members, d, read))
        if settings.skip_locked_cutscenes or settings.skip_auto_dialogues:
            # In place on the vanilla table (same size); chest rows are added after.
            report('Dialogues and area presentations skippable with + …')
            extra_raw[EVENT_SETTINGS], skips['dialogues'] = patch_dialogues(
                decompress(read(EVENT_SETTINGS), d), settings.skip_auto_dialogues, settings.skip_locked_cutscenes)
        plain_raw = {}
        mailbox_items = ap_records(settings)
        if mailbox_items:
            # Items of other worlds: the client sets a Bool in the game's memory, the
            # global sequence starts an item-get event (patching.ap_mailbox). After the
            # sub-flow completion above: its own row lists what it calls.
            report('Archipelago item reception…')
            from oot_rando.patching import ap_mailbox
            from oot_rando.patching.event_info import GAME_ANALYZED_EVENT_INFO, flow_path as mailbox_flow_path
            current_raw = lambda path: extra_raw[path] if path in extra_raw else decompress(read(path), d)
            extra_raw[ap_mailbox.FLOW_PATH] = ap_mailbox.add_entries(current_raw(ap_mailbox.FLOW_PATH), mailbox_items)
            mailbox_flows = lambda name: (extra_raw[ap_mailbox.FLOW_PATH] if name == ap_mailbox.FLOW
                                          else current_raw(mailbox_flow_path(name))
                                          if mailbox_flow_path(name) in members else None)
            extra_raw[EVENT_SETTINGS] = ap_mailbox.add_event_rows(current_raw(EVENT_SETTINGS), mailbox_items)
            extra_raw[GAME_ANALYZED_EVENT_INFO], mailbox_row = ap_mailbox.add_analyzed_rows(
                current_raw(GAME_ANALYZED_EVENT_INFO), mailbox_items, mailbox_flows)
            plain_raw[ap_mailbox.MAIN_UPDATE] = ap_mailbox.patch_main_update(read(ap_mailbox.MAIN_UPDATE),
                                                                             mailbox_items)
            extra_raw[GAMEDATA] = add_saved_flags(extra_raw[GAMEDATA], {
                flag: False for record in mailbox_items for flag in (record['recv'], record['got'])})
            skips['ap_mailbox'] = {'items': mailbox_items, 'row': mailbox_row}
        if full is not None:
            # Chests save no flag of their own: each shuffled chest runs its own copy of
            # its opening event, which sets a saved Bool first (tracking, Archipelago).
            # Last of the event patches: the copied rows inherit every completed list.
            report('Opening flags of the chests…')
            from oot_rando.patching import chest_flags
            current_raw = lambda path: extra_raw[path] if path in extra_raw else decompress(read(path), d)
            map_root = lambda path: Byml(raw_maps[path] if path in raw_maps else decompress(read(path), d)).root
            settings_raw = current_raw(chest_flags.EVENT_SETTINGS)
            settings_rows = {row['__RowId']: row for row in Byml(settings_raw).root}
            records, skipped = chest_flags.plan_records(full['placements'], map_root, settings_identity(settings),
                                                        settings_rows)
            for resource, edits in sorted(chest_flags.map_edits(records).items()):
                raw_maps[resource] = patch_strings(raw_maps[resource] if resource in raw_maps
                                                   else decompress(read(resource), d), edits)
            for path, flow_records in sorted(chest_flags.by_flow(records).items()):
                extra_raw[path] = chest_flags.add_entries(current_raw(path), flow_records)
            extra_raw[chest_flags.EVENT_SETTINGS] = chest_flags.add_rows(settings_raw, records)
            extra_raw[chest_flags.ANALYZED], analyzed = chest_flags.add_analyzed_rows(
                current_raw(chest_flags.ANALYZED), records)
            extra_raw[GAMEDATA] = add_saved_flags(extra_raw[GAMEDATA], {r['flag']: False for r in records})
            for record in records:
                full['matches'][record['id']]['tracking_flag'] = record['flag']
            skips['chest_flags'] = {'records': records, 'skipped': skipped, 'analyzed_rows': analyzed}
            # Meeting Zelda before the Deku Tree must not send Mido away from his wall.
            from oot_rando.patching.qol_patches import MIDO_SCHEDULE, keep_mido_at_post
            plain_raw[MIDO_SCHEDULE], skips['mido_post'] = keep_mido_at_post(read(MIDO_SCHEDULE))
        growths = {}
        for path, raw in sorted(raw_maps.items()):
            source = read(path)
            growth = len(raw) - len(decompress(source, d))
            if growth < 0:
                raise ValueError('A composed map shrank unexpectedly.')
            growths[path] = growth
            compress(path, raw, source)
        compress_changed(extra_raw, files, growths, read, d)
        for path, raw in sorted(plain_raw.items()):
            # Uncompressed resources (sequence AI): written as they are.
            growths[path] = max(len(raw) - len(read(path)), 0)
            files[path] = raw
        new_sizes = {}
        rest_raw = decompress(read(RESTBL), d) if new_files else None
        for path, (raw, template) in sorted(new_files.items()):
            compress(path, raw, read(template))
            # A copy of a resource (model, texture) needs at least the original's allocation.
            new_sizes[path] = max((len(raw) + 0x1000 + 4095) & ~4095, allocation(rest_raw, template) or 0)
        allocations = grow_resource_table(files, growths, new_sizes, read, d)
        if settings.skip_locked_cutscenes:
            report('Skippable cutscenes…')
            cutscenes, skips['cutscenes'] = cutscene_files(read)
            files.update(cutscenes)

        manifest = {'schema_version': 1, 'generator_version': GENERATOR_VERSION,
                    'adapter_version': ADAPTER_VERSION, 'seed_id': settings_identity(settings),
                    'title_id': TITLE, 'build_id': BUILD, 'settings': settings.to_dict(),
                    'scope': 'Four Kokiri chests, ordinary chests, explicit drops of the selected pots, bushes and rocks, and QoL. Progression and ambiguous sources kept.',
                    'files': {p: {'size': len(v), 'sha256': sha256(v)} for p, v in sorted(files.items())},
                    'source_files': sources, 'resource_allocations': allocations,
                    'coverage': world['coverage'], 'skips': skips, 'progression_randomized': full is not None,
                    'complete_randomizer': False,
                    'validation': 'Static checks done; this composed seed is still to be tested in game.'}
        if save_seed_id:
            manifest['save_seed_id'] = save_seed_id
        if full is not None:
            families = sorted({p['source'] for p in full['placements']})
            manifest['scope'] = ('Full glitchless randomizer: sources shuffled together ('
                                 + ', '.join(families) + ') placed by the remake glitchless solver and checked by a '
                                 'second playthrough; other sources unchanged.')
            manifest['full_randomizer'] = {
                'logic_world_version': full['logic_world_version'],
                'logic_world_sha256': full['logic_world_sha256'], 'coverage': full['coverage'], 'attempts': full['attempts'],
                'experimental': rando_options.experimental_choices(settings.full),
                'souls': full['souls']['items'], 'new_save_required': bool(full['souls']['items']),
                'derived_actors': full['derived_actors'],
                'sources': dict(sorted(__import__('collections').Counter(
                    p['source'] for p in full['placements']).items()))}
            if full.get('archipelago'):
                # Read by the Archipelago client: location IDs and items found in other worlds.
                manifest['archipelago'] = full['archipelago']
            elif full.get('starting'):
                manifest['starting'] = full['starting']
        checks = {'schema_version': 1, 'seed_id': manifest['seed_id'],
                  # With the complete randomizer its catalogue lists every check (the
                  # four historical Kokiri chests included): no duplicates.
                  'checks': full['checks'] + world['checks'] if full else (
                      [dict(check, randomized=active and check['id'] not in settings.excluded_checks)
                       for check in CHECKS] + world['checks'])}
        spoiler = {'schema_version': 1, 'seed_id': manifest['seed_id'],
                   'placements': [dict(c, id=c['hash'], category='kokiri_chests', resources=[MAP, ADULT_MAP])
                                  for c in chests] + world['placements']
                                  + ([dict(p, category='full_' + ('chests' if p['source'] == 'chest' else p['source']))
                                      for p in full['spoiler']] if full else []),
                   'playthrough': full['playthrough'] if full else []}

        def tracking_read(path):
            if path in extra_raw:
                return extra_raw[path]
            if path in new_files:
                return new_files[path][0]
            return decompress(read(path), d)

        tracking = build_tracking(manifest['seed_id'], checks['checks'], full, tracking_read)
        tracking['seed_marker'] = str(murmur3(marker_name))
        tracking['event_markers'][opening] = seed_markers
        if goal_name:
            tracking['goal_marker'] = str(murmur3(goal_name))
            tracking['event_markers'][GOAL_FLOW] = goal_markers
        if full is None:
            from oot_rando.game.remake_world import actor_item
            for c in chests:
                row = tracking['checks'].get(str(c['hash']))
                if row:
                    row['reward'] = reward_label(actor_item(c['after'], 'KokiriForest'), c['after'])
            for placement in world['placements']:
                row = tracking['checks'].get(placement['id'])
                if row:
                    actor = placement.get('after', '')
                    row['reward'] = reward_label(actor_item(actor, placement.get('folder', '')), actor)
        tracking_bytes = json.dumps(tracking, ensure_ascii=False, indent=2).encode('utf-8')
        manifest['tracking'] = {'schema_version': 1, 'sha256': sha256(tracking_bytes),
                                'new_save_required': True, 'mode': 'save'}
        report('Writing the mod and its manifests atomically…')
        def write_spoiler_text(staging):
            # Human-readable spoiler next to spoiler.json (not part of the manifest).
            from oot_rando.randomizer.spoiler_report import SPOILER_TEXT, load_report, write_text
            write_text(load_report(staging), staging / SPOILER_TEXT)
        publish_mod(output, files, {'manifest.json': json_document(manifest), 'checks.json': json_document(checks),
                                    'spoiler.json': json_document(spoiler), 'tracking.json': tracking_bytes},
                    write_spoiler_text)
        report('Generation done.')
        return manifest
    finally:
        nup.stream.close()


def _build_full(nup, dictionaries_, members, settings, raw_maps, sources, read, report):
    """Plan and compose the complete randomizer. Returns (plan, modified, new)."""
    from collections import defaultdict
    from oot_rando.logic.world import World
    from oot_rando.formats import byml_codec
    from oot_rando.randomizer import full_randomizer
    from oot_rando.game.extra_sources import scan_world
    from oot_rando.game.item_forms import add_rsdb_rows, build_pack, derived_actors, is_derived
    from oot_rando.patching.soul_adapter import build_soul_files, presence_changes, RSDB_FILES
    from oot_rando.patching.event_patch import patch_event_params

    report('Reading the remake logic…')
    data = World()
    maps, groups, enemies, extra = scan_world(nup, dictionaries_, members, report)
    if settings.archipelago is not None:
        from oot_rando.archipelago import bridge
        patch = settings.archipelago
        if patch['game_build'] != BUILD or patch['world'] != data.fingerprint()                 or patch['scan'] != bridge.scan_fingerprint(groups, enemies, extra):
            raise ValueError('This Archipelago patch was generated with an apworld built from another game '
                             'or another version of the application: rebuild the apworld and generate again.')
        report('Applying the Archipelago placements…')
        plan = full_randomizer.plan_assigned(data, settings.full, groups, enemies, patch['seed_key'],
                                             bridge.assigned_items(patch), settings.open_forest, report,
                                             extra=extra, labels=bridge.foreign_labels(patch),
                                             order=bridge.patch_spheres(patch),
                                             starting=patch.get('precollected', ()))
        plan['archipelago'] = {'starting': plan['starting'], 'seed_name': patch.get('seed_name'), 'slot_name': patch.get('slot_name'),
                               'player': patch.get('player'), 'location_ids': patch.get('location_ids', {}),
                               'remote': patch['remote'], 'spheres': bridge.patch_spheres(patch)}
    else:
        report('Glitchless placement and independent check…')
        plan = full_randomizer.plan(data, settings.full, groups, enemies, settings_identity(settings),
                                    settings.open_forest, report, extra=extra)
    from oot_rando.patching.repeatable_adapter import (prepare_repeatables, patch_repeatable_sources,
                                     build_repeatable_packs, register_repeatable_flags)
    repeatables = prepare_repeatables(plan, maps)
    repeatable_actors = {r['actor'] for r in repeatables}
    plan['repeatables'] = repeatables
    for record in repeatables:
        plan['matches'][record['id']]['tracking_flag'] = record['flag']
        for row in plan['spoiler']:
            if row['id'] == record['id']:
                row['reward_actor'] = row['actor']
                row['actor'] = record['actor']
    changes, event_changes = defaultdict(list), defaultdict(list)
    for placement in plan['placements']:
        unchanged = placement['after'] == placement['before']
        for patch in placement['patches']:
            if 'after' in patch:      # own value (scrub price), whatever the item
                event_changes[patch['resource']].append(
                    (patch['event'], patch['param'], patch['before'], patch['after']))
            elif unchanged:
                continue
            elif 'event' in patch:
                event_changes[patch['resource']].append(
                    (patch['event'], patch['param'], patch['before'], placement['after']))
            else:
                changes[patch['resource']].append({'path': tuple(patch['path']), 'before': patch['before'],
                                                   'after': placement['after']})
    for resource, edits in presence_changes(plan['souls']['edits'] + plan['souls'].get('door_edits', []),
                                            {path: maps[path]['root'] for path in maps}).items():
        changes[resource].extend(edits)
    actors = {p['after'] for p in plan['placements']} - {p['before'] for p in plan['placements']}
    from oot_rando.patching.key_adapter import is_key_actor as _is_key_actor
    for actor in sorted(actors):
        if (actor.startswith(('Item_Soul_', 'Item_AP_')) or is_derived(actor) or actor in repeatable_actors
                or _is_key_actor(actor)):
            continue
        if 'Pack/Actor/' + actor + '.pack.zs' not in members:
            raise ValueError('Reward actor missing from the game: ' + actor)
    for resource, edits in sorted(changes.items()):
        report('Composition : ' + resource.split('/')[-1])
        if resource not in raw_maps:
            sources[resource] = sha256(maps[resource]['compressed'])
        raw_maps[resource] = patch_strings(raw_maps.get(resource, maps[resource]['raw']), edits)
    patch_repeatable_sources(repeatables, maps, raw_maps)
    modified, new = {}, {}
    if plan['souls']['items']:
        report('Building souls: items, tables, flags and texts…')
        messages = sorted(m for m in members if m.startswith('Mals/') and '.Product.110.' in m)
        if not messages:
            raise ValueError('Message archives not found: soul names cannot be shown.')
        modified, new = build_soul_files(lambda path: decompress(read(path), dictionaries_),
                                         plan['souls']['items'], messages)
    # Dungeon-specific keys (key rings, boss keys found outside their dungeon).
    from oot_rando.patching.key_adapter import build_key_files, check_dungeon_data, is_key_actor, key_records
    from oot_rando.game.item_forms import canonical_of
    def _reward(placement):   # repeatable pickups keep their reward actor apart
        actor = placement.get('reward_actor', placement['after'])
        return canonical_of(actor) if is_derived(actor) else actor

    key_items = {p['item'] for p in plan['placements'] if is_key_actor(_reward(p))}
    # Received from other worlds too: the mailbox hands over the same actors.
    from oot_rando.patching.ap_mailbox import key_items as _mailbox_key_items
    key_items = sorted(key_items | set(_mailbox_key_items(ap_records(settings))))
    plan['key_items'] = key_records(key_items)
    if plan['key_items']:
        report('Building dungeon-specific keys (key rings, boss keys)…')
        messages = sorted(m for m in members if m.startswith('Mals/') and '.Product.110.' in m)

        def key_read(path):
            return modified[path] if path in modified else decompress(read(path), dictionaries_)

        from oot_rando.patching.soul_adapter import GAMEDATA as _GAMEDATA
        check_dungeon_data(key_read(_GAMEDATA), plan['key_items'])
        key_modified, key_new = build_key_files(key_read, plan['key_items'], messages)
        modified.update(key_modified)
        new.update(key_new)
    if settings.archipelago is not None:
        from oot_rando.archipelago.bridge import foreign_items
        from oot_rando.patching.ap_item import build_ap_files
        placed = {p['item'] for p in plan['placements']}
        ap_items = {item: label for item, label in foreign_items(settings.archipelago).items() if item in placed}
        if ap_items:
            report(f'Building {len(ap_items)} Archipelago items (medallion with the logo, names)…')
            messages = sorted(m for m in members if m.startswith('Mals/') and '.Product.110.' in m)

            def ap_read(path):
                return modified[path] if path in modified else decompress(read(path), dictionaries_)

            ap_modified, ap_new = build_ap_files(ap_read, ap_items, messages)
            modified.update(ap_modified)
            new.update(ap_new)
    for resource, edits in sorted(event_changes.items()):
        report('Event: ' + resource.split('/')[-1])
        modified[resource] = patch_event_params(decompress(read(resource), dictionaries_), edits)
    from oot_rando.patching.event_patch import add_collection_markers
    from oot_rando.game.tracking_metadata import GAMEDATA, add_saved_flags
    markers, saved_flags = defaultdict(dict), {}
    for gid, entry in sorted(plan['matches'].items()):
        event_variants = [v for v in entry['variants'] if 'event' in v]
        if not event_variants:
            continue
        if entry.get('native_flag'):
            # Business scrubs save their own flag once the purchase succeeded
            # (a marker after the sub-flow would also fire on "No").
            entry['tracking_flag'] = entry['native_flag']
            continue
        flag = 'RandoCheck.' + settings_identity(settings)[:16] + '.' + gid
        entry['tracking_flag'] = flag
        saved_flags[flag] = False
        for variant in event_variants:
            old = markers[variant['resource']].get(variant['event'])
            if old and old != flag:
                raise ValueError('Two checks share the same collection event.')
            markers[variant['resource']][variant['event']] = flag
    plan['collection_markers'] = {}
    for resource, events in sorted(markers.items()):
        raw = modified.get(resource)
        if raw is None:
            raw = decompress(read(resource), dictionaries_)
        modified[resource], plan['collection_markers'][resource] = add_collection_markers(raw, events)
    # Cutscene gifts: the shuffled item is given (and shown in Link's hands) once back
    # in game, after the cutscene (pilot flows only).
    from oot_rando.patching.qol_patches import GIFT_AFTER_CUTSCENE, bypass_cutscene_gift, give_gift_after
    plan['gift_get'] = {}
    for resource, spec in sorted(GIFT_AFTER_CUTSCENE.items()):
        if resource not in event_changes:
            continue
        modified[resource], bypass = bypass_cutscene_gift(modified[resource], spec['event'])
        target = spec['flow']
        raw = modified.get(target)
        if raw is None:
            raw = decompress(read(target), dictionaries_)
        modified[target], given = give_gift_after(raw, spec['after'], bypass['actor'], bypass['flag'])
        plan['gift_get'][resource] = {'event': spec['event'], 'actor': bypass['actor'], 'flag': bypass['flag'],
                                      'flow': target, 'after': spec['after'], 'call': given['call']}
    if saved_flags:
        raw = modified.get(GAMEDATA)
        if raw is None:
            raw = decompress(read(GAMEDATA), dictionaries_)
        modified[GAMEDATA] = add_saved_flags(raw, saved_flags)
    # Shuffled shelves are sold once by the shop itself: the slot stays selectable.
    from oot_rando.patching.repeatable_adapter import limit_shop_stock, shop_stock_edits
    for seller, slots in sorted(shop_stock_edits(repeatables, maps).items()):
        path = 'Pack/Actor/' + seller + '.pack.zs'
        if path in modified or path in new:
            raise ValueError('Shopkeeper pack already modified: ' + seller)
        modified[path], _ = limit_shop_stock(decompress(read(path), dictionaries_), slots)
    derived = derived_actors(p['after'] for p in plan['placements'])
    if derived or repeatables:
        report(f'Building {len(derived)} derived actors (freestanding and shop items)…')
        packs = {}

        def read_pack(actor):
            if actor not in packs:
                path = 'Pack/Actor/' + actor + '.pack.zs'
                if path in new:      # generated pack (soul): derive world/shop forms from it
                    packs[actor] = sarc(new[path][0])
                else:
                    packs[actor] = sarc(decompress(read(path), dictionaries_)) if path in members else None
            return packs[actor]

        for actor in derived:
            new['Pack/Actor/' + actor + '.pack.zs'] = build_pack(actor, read_pack, byml_codec)
        documents = {name: byml_codec.load(modified[path] if path in modified
                                           else decompress(read(path), dictionaries_))
                     for name, path in RSDB_FILES.items()}
        add_rsdb_rows({name: document['root'] for name, document in documents.items()}, derived)
        tables = {name: document['root'] for name, document in documents.items()}

        def repeat_read_raw(path):
            return modified[path] if path in modified else decompress(read(path), dictionaries_)

        new.update(build_repeatable_packs(repeatables, read_pack, repeat_read_raw, tables))
        for name, path in RSDB_FILES.items():
            modified[path] = byml_codec.dump(documents[name])
    if repeatables:
        raw = modified.get(GAMEDATA)
        if raw is None:
            raw = decompress(read(GAMEDATA), dictionaries_)
        modified[GAMEDATA], plan['repeatable_flags'] = register_repeatable_flags(raw, repeatables)
    plan['derived_actors'] = derived + sorted(repeatable_actors)
    plan['logic_world_version'] = data.version
    plan['logic_world_sha256'] = data.fingerprint()
    return plan, modified, new
