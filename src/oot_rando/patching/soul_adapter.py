"""Enemy souls (OoTR Dev-Rob ``shuffle_enemy_spawns``) for the remake.

An enemy whose family soul has not been obtained does not appear. The remake
already supports conditional presence on map actors::

    "Presence": {"FlagName": <name>, "IsNegation": false, "IsCheckLazy": false}

and records ``IsGet.<actor>`` flags for obtained pouch actors (murmur3 hash of
the name, verified on the local data). Each soul is therefore a new pouch actor
``Item_Soul_<Family>`` built from the Forest Medallion key-item template with the
Poe soul model, plus a saved ``IsGet.Item_Soul_<Family>`` flag. An enemy that
already carries a Presence condition (Death Mountain and Zora's River tektites,
Kokiri Forest Deku Babas...) reads a new GameData BoolExp instead: its soul AND its
vanilla condition (:func:`soul_expression`). They used to stay soul-independent,
so they appeared without their soul (Discord 17/11).

Logic (conservative): entering a dungeon requires its mechanical and combat
souls, entering a boss room requires the boss soul. Native AI defeat outputs,
counter locks and scripted rewards count even when a shutter is hidden by the
patch. Overworld passage fights gate their AP region; physical rewards get
the souls of the native AI group controlling them.
"""
from collections import defaultdict

from oot_rando.game.remake_world import FOLDER_AP_DUNGEON

from oot_rando.catalog.souls import (  # noqa: F401  (moved to oot_rando.catalog.souls, re-exported)
    FAMILIES,
    BY_ID,
    EXCLUDED_MARKERS,
    EXCLUDED_FOLDERS,
    REGION_LABELS,
    LOCATION_KEYWORDS,
    FLAG_PREFIX,
    EXCLUDED_EXCEPTIONS,
    family_of,
    soul_item,
    MAX_ACTOR_NAME,
    REGION_CODES,
    soul_actor,
    soul_label,
    _spaced,
    soul_name,
    ENGLISH_FAMILIES,
    ENGLISH_REGIONS,
    soul_event_name,
    soul_event_member,
    soul_event_ain,
)


def resolve_room_locks(candidates):
    """Keep "defeat every enemy" rooms openable without their soul.

    For each enemy counter whose enemies are soul-bound, one soul (the one with
    most enemies there) gates the room: its doors get ``Presence`` on that soul's
    flag, so without the soul the shutters are absent (open passage) and with it
    the room works as in the original game. Enemies of the counter bound to
    another soul stay unbound (they always spawn, so the counter can complete).
    A counter whose door already has a Presence condition, or a door shared with
    a counter gated by another soul, cannot be patched: its enemies stay unbound.
    Returns ``(kept candidates, door edits)``.
    """
    candidates = list(candidates)
    while True:
        counters = {}
        for position, (enemy, key, _) in enumerate(candidates):
            for lock in enemy.get('locks', ()):
                entry = counters.setdefault(lock['counter'], {'doors': lock['doors'], 'members': []})
                entry['members'].append((position, key))
        drop, door_flag, door_info = set(), {}, {}
        for counter_id in sorted(counters):
            entry = counters[counter_id]
            weight = defaultdict(int)
            for _, key in entry['members']:
                weight[key] += 1
            primary = min(weight, key=lambda k: (-weight[k], k))
            blocked = any(door['presence'] is not None or door_flag.get(door['hash'], primary) != primary
                          for door in entry['doors'])
            if blocked or not entry['doors']:
                # Not patchable (or opened by something we cannot see): never strand the player.
                drop.update(position for position, _ in entry['members'])
                continue
            drop.update(position for position, key in entry['members'] if key != primary)
            for door in entry['doors']:
                door_flag[door['hash']] = primary
                door_info[door['hash']] = door
        if not drop:
            break
        candidates = [c for position, c in enumerate(candidates) if position not in drop]
    door_edits = [{'resource': door_info[h]['resource'], 'index': door_info[h]['index'],
                   'actor': door_info[h]['actor'], 'hash': h, 'soul': door_flag[h],
                   'flag': FLAG_PREFIX + soul_actor(soul_item(door_flag[h])), 'door': True}
                  for h in sorted(door_flag)]
    return candidates, door_edits


# Families whose defeat the dungeon logic always expects (minibosses blocking
# the way, Jabu-Jabu's tentacles), even if no map link says so.
ALWAYS_MECHANICAL = ('BigOcto', 'DarkLink', 'FlareDancer', 'JabuTentacle')


def is_mechanical(enemy):
    if 'mechanics' not in enemy:
        return True
    return bool(enemy['mechanics'] or enemy.get('locks') or enemy.get('combat')) or family_of(enemy['actor']) in ALWAYS_MECHANICAL


def plan_souls(mode, enemies, logic_regions):
    """Return the soul items, map edits and logic requirements for ``mode``."""
    if mode == 'off':
        return {'items': [], 'edits': [], 'door_edits': [], 'exit_requirements': {}, 'location_requirements': {},
                'chest_requirements': {}, 'families': {}}
    if mode not in ('bosses', 'regional', 'all'):
        raise ValueError('Unknown soul mode.')
    patched = defaultdict(set)          # soul key -> folders
    per_folder = defaultdict(set)       # folder -> soul keys (non-boss)
    boss_rooms = {}
    per_map = defaultdict(set)
    combat_targets = defaultdict(set)
    combat_regions = defaultdict(set)
    scripted_locations = defaultdict(set)
    edits = []
    candidates = []
    for enemy in enemies:
        if enemy['folder'] in EXCLUDED_FOLDERS:
            continue
        family = family_of(enemy['actor'])
        if family is None:
            continue
        boss = BY_ID[family][2]
        if mode == 'bosses' and not boss:
            continue
        key = family if mode != 'regional' else 'Region:' + enemy['folder']
        candidates.append((enemy, key, boss))
    candidates, door_edits = resolve_room_locks(candidates)
    for enemy, key, boss in candidates:
        patched[key].add(enemy['folder'])
        if enemy['folder'] == 'KokiriForest' and family_of(enemy['actor']) == 'DekuBaba':
            for location in ('Deku Baba Sticks', 'Deku Baba Nuts'):
                scripted_locations[location].add(soul_item(key))
        if 'NPC_Scrub_Deku_TargetPractice' in enemy.get('mechanics', ()):
            scripted_locations['LW Target in Woods'].add(soul_item(key))
        for combat in enemy.get('combat', ()):
            for target in combat['targets']:
                combat_targets[enemy['folder'] + '#' + target].add(soul_item(key))
            for region in combat['regions']:
                combat_regions[region].add(soul_item(key))
        # Old catalogs do not carry AI evidence, but their native room locks
        # already identify the Royal Tomb battle. Never assume hidden shutters
        # remove the script-controlled collision or make its reward reachable.
        if enemy['folder'] == 'Graveyard' and family_of(enemy['actor']) == 'Keese' and enemy.get('locks'):
            combat_regions['Graveyard Royal Familys Tomb'].add(soul_item(key))
        if boss and mode != 'regional':
            boss_rooms[boss] = key
        else:
            # Entering a dungeon needs only the souls whose enemies drive something
            # (``remake_world.enemy_mechanics``); without its soul any other enemy
            # is absent and its room only gets easier. Enemies scanned before the
            # field existed (older Archipelago catalogs) count as mechanical.
            if is_mechanical(enemy):
                per_folder[enemy['folder']].add(key)
            per_map[enemy['resource']].add(key)
        edit = {'resource': enemy['resource'], 'index': enemy['index'], 'actor': enemy['actor'],
                'hash': enemy['hash'], 'soul': key, 'flag': FLAG_PREFIX + soul_actor(soul_item(key))}
        if enemy['presence'] is not None:
            edit['vanilla'] = dict(enemy['presence'])
        edits.append(edit)
    exit_requirements = {}
    for region in logic_regions:
        name, dungeon = region['region_name'], region.get('dungeon')
        for target in region.get('exits', {}):
            target_region = next((r for r in logic_regions if r['region_name'] == target), None)
            if target_region is None:
                continue
            requirement = set()
            target_dungeon = target_region.get('dungeon')
            if target_dungeon and target_dungeon != dungeon:
                for folder, ap_dungeon in FOLDER_AP_DUNGEON.items():
                    if ap_dungeon == target_dungeon:
                        requirement |= {soul_item(k) for k in per_folder.get(folder, ())}
            if target in boss_rooms and not region.get('is_boss_room'):
                requirement.add(soul_item(boss_rooms[target]))
            requirement.update(combat_regions.get(target, ()))
            if requirement:
                exit_requirements[(name, target)] = requirement
    location_requirements = {k: set(v) for k, v in scripted_locations.items()}
    for region in logic_regions:
        required = combat_regions.get(region['region_name'])
        if required:
            for location in region.get('locations', {}):
                location_requirements.setdefault(location, set()).update(required)
    return {'items': sorted(soul_item(k) for k in patched), 'edits': edits, 'door_edits': door_edits,
            'exit_requirements': exit_requirements,
            'location_requirements': location_requirements, 'per_map': {k: sorted(v) for k, v in per_map.items()},
            'families': {k: sorted(v) for k, v in patched.items()}, 'mode': mode,
            'combat_targets': {k: sorted(v) for k, v in combat_targets.items()},
            'combat_regions': {k: sorted(v) for k, v in combat_regions.items()}}


def chest_requirements(plan, group, ap_locations):
    """Extra souls for one remake chest group (conditional chests, named enemies)."""
    if not plan['items']:
        return set()
    required = set()
    required.update(plan.get('combat_targets', {}).get(group.get('id'), ()))
    for variant in group['variants']:
        required.update(plan.get('combat_targets', {}).get(
            group['folder'] + '#' + str(variant.get('hash')), ()))
        if variant.get('dynamic', {}).get('SpawnType') == 1:
            required |= {soul_item(k) for k in plan['per_map'].get(variant['resource'], ())}
    if plan['mode'] != 'regional':
        for location in ap_locations:
            for word, family in LOCATION_KEYWORDS.items():
                if word in location and family in plan['families']:
                    required.add(soul_item(family))
    else:
        for location in ap_locations:
            if any(word in location for word in LOCATION_KEYWORDS):
                key = 'Region:' + group['folder']
                if key in plan['families']:
                    required.add(soul_item(key))
    return required


# ---------------------------------------------------------------- game files
TEMPLATE = 'Item_Medal_Forest'
MODEL = 'Obj_Spirit_Poe'
GAMEDATA = 'GameData/GameDataList.Product.110.byml.zs'
RSDB_FILES = {'ActorInfo': 'RSDB/ActorInfo.Product.111.rstbl.byml.zs',
              'GameActorInfo': 'RSDB/GameActorInfo.Product.111.rstbl.byml.zs',
              'PouchActorInfo': 'RSDB/PouchActorInfo.Product.111.rstbl.byml.zs'}


from oot_rando.catalog.hashing import (  # noqa: F401  (moved to oot_rando.catalog.hashing, re-exported)
    murmur3,
)


MESSAGE_FILE = 'ActorMsg/PouchContent.msbt'


def soul_messages(item, language):
    """The four get-item texts of a soul for a ``Mals`` language code (e.g. ``EUfr``)."""
    if language.endswith('fr'):
        name = soul_name(item, True)
        return {'Name': 'Âme : ' + name,
                'Caption': f"L'âme des monstres « {name} ».\nSans elle, ces ennemis n'apparaissent pas.",
                'GetMessage': f"Vous avez obtenu l'âme : {name} !",
                'GetCaption': 'Ces monstres peuvent désormais apparaître.'}
    name = soul_name(item, False)
    return {'Name': 'Soul: ' + name,
            'Caption': f'The soul of the "{name}" monsters.\nWithout it, these enemies do not appear.',
            'GetMessage': f'You got the soul: {name}!',
            'GetCaption': 'These monsters can now appear.'}


def patch_soul_messages(raw_archive, language, soul_items):
    """Add the get-item labels of every soul actor to one ``Mals`` archive."""
    return patch_item_messages(raw_archive, language,
                               {soul_actor(item): (lambda lang, item=item: soul_messages(item, lang))
                                for item in soul_items})


def patch_item_messages(raw_archive, language, texts):
    """``texts``: new actor -> function(language) giving its four get-item texts."""
    from oot_rando.formats import byml_codec
    from oot_rando.formats import msbt
    from oot_rando.formats.inspect_resources import sarc
    files = dict(sarc(raw_archive))
    if MESSAGE_FILE not in files:
        raise ValueError('Item messages missing from the archive ' + language)
    message = msbt.load(files[MESSAGE_FILE])
    if message.get(TEMPLATE + '_GetMessage') is None:
        raise ValueError('Soul template message missing: ' + language)
    for actor in sorted(texts):
        for suffix, text in texts[actor](language).items():
            message.add(f'{actor}_{suffix}', text)
    files[MESSAGE_FILE] = msbt.dump(message)
    return byml_codec.build_sarc(files)


def build_soul_files(read_raw, soul_items, message_archives=()):
    """Return ``(modified, new)`` raw resources for the soul actors and flags.

    ``read_raw(path)`` returns the decompressed bytes of a game resource.
    ``message_archives`` lists the ``Mals/<lang>.Product.<ver>.sarc.zs`` paths
    that receive the get-item texts (without them the item box never closes).
    ``modified`` replaces existing resources; ``new`` maps a new resource path to
    ``(raw, template_path)`` where the template gives the compression dictionary.
    """
    specs = []
    for item in soul_items:
        actor = soul_actor(item)
        specs.append({'actor': actor, 'model': MODEL, 'event_name': soul_event_name(actor),
                      'event_member': soul_event_member(actor), 'event_ain': soul_event_ain(actor),
                      'texts': (lambda lang, item=item: soul_messages(item, lang))})
    return build_item_files(read_raw, specs, message_archives)


def build_item_files(read_raw, specs, message_archives=()):
    """New key-item pouch actors from the Forest Medallion template (souls, dungeon keys).

    ``specs``: dicts with ``actor``, ``model`` (native actor lending its model; an
    optional ``model_info`` overrides its ``FmdbName``/``ModelProjectName``; optional
    ``files``, ``components`` and ``actor_info`` add pack files, component references
    and ActorInfo values),
    ``event_name``/``event_member``/``event_ain`` (cloned get event) and ``texts``
    (function(language) -> get-item texts). Reading goes through ``read_raw`` so
    that successive calls compose.
    """
    import copy
    from oot_rando.formats import byml_codec
    from oot_rando.formats.inspect_resources import sarc

    if not specs:
        return {}, {}
    specs = sorted(specs, key=lambda spec: spec['actor'])
    too_long = [spec['actor'] for spec in specs if len(spec['actor']) > MAX_ACTOR_NAME]
    if too_long:
        raise ValueError('Generated actor names too long for the game: ' + ', '.join(too_long))
    from oot_rando.patching.repeatable_adapter import EVENT_MEMBER, EVENT_PACK, instrument_pickup_event
    actors = [spec['actor'] for spec in specs]
    modified, new = {}, {}
    get_event = sarc(read_raw(EVENT_PACK))[EVENT_MEMBER]
    # 1. Packs: Forest Medallion key item with the Poe soul model.
    template = sarc(read_raw(f'Pack/Actor/{TEMPLATE}.pack.zs'))
    models = {}
    for spec in specs:
        if spec['model'] not in models:
            pack = sarc(read_raw(f"Pack/Actor/{spec['model']}.pack.zs"))
            models[spec['model']] = byml_codec.load(
                pack[f"Component/ModelInfo/{spec['model']}.engine__component__ModelInfo.bgyml"])
    actor_param = f'Actor/{TEMPLATE}.engine__actor__ActorParam.bgyml'
    model_info = f'Component/ModelInfo/{TEMPLATE}.engine__component__ModelInfo.bgyml'
    if actor_param not in template or model_info not in template:
        raise ValueError('Unexpected key item template for souls.')
    for spec in specs:
        actor = spec['actor']
        files = {k: v for k, v in template.items() if k not in (actor_param, model_info)}
        param = byml_codec.load(template[actor_param])
        components = param['root']['Components']
        components['ModelInfoRef'] = f'?Component/ModelInfo/{actor}.engine__component__ModelInfo.bgyml'
        # The game identifies a pouch item by its ActorName (vanilla: always equal to
        # ActorInfo.ActorName, e.g. Item_HoverBoot → Armor_Adult_HoverBoot → flag
        # IsGet.Armor_Adult_HoverBoot). Keeping the template's name made every soul
        # count as "Item_Medal_Forest": IsGet.Item_Soul_* stayed false, so the
        # enemies never appeared.
        if 'ActorNameRef' not in components:
            raise ValueError('Soul template actor name not found.')
        components['ActorNameRef'] = f'?ActorSystem/ActorName/{actor}.engine__actor__ActorName.bgyml'
        # The game only writes IsGet.<name> for the pouch items it knows (tested in
        # game: a new name stays false whatever its ActorName). The get event of the
        # soul is a clone of the native one writing the flag right after the native
        # add-to-pouch action (same technique as first-collection pickups).
        flag = FLAG_PREFIX + actor
        files[spec['event_member']] = instrument_pickup_event(get_event, flag, spec['event_name'])
        event_param = f'Component/EventPerformerParam/{actor}.engine__component__EventPerformerParam.bgyml'
        files[event_param] = byml_codec.dump({'endian': '<', 'version': 7, 'root': {
            'EventUniqueAin': spec['event_ain'], 'UseEventUniqueAin': True}})
        components['EventPerformerRef'] = '?' + event_param
        files.update(spec.get('files', {}))
        components.update(spec.get('components', {}))
        files[f'Actor/{actor}.engine__actor__ActorParam.bgyml'] = byml_codec.dump(param)
        model = copy.deepcopy(models[spec['model']])
        model['root'].update(spec.get('model_info', {}))
        files[f'Component/ModelInfo/{actor}.engine__component__ModelInfo.bgyml'] = byml_codec.dump(model)
        new[f'Pack/Actor/{actor}.pack.zs'] = (byml_codec.build_sarc(files), f'Pack/Actor/{TEMPLATE}.pack.zs')
    # 2. RSDB rows (sorted by row id), cloned from the template / model rows.
    for table, path in RSDB_FILES.items():
        document = byml_codec.load(read_raw(path))
        rows = document['root']
        by_id = {row['__RowId']: row for row in rows}
        if TEMPLATE not in by_id or any(actor in by_id for actor in actors):
            raise ValueError(f'Unexpected {table} table for souls.')
        for spec in specs:
            actor = spec['actor']
            row = copy.deepcopy(by_id[TEMPLATE])
            row['__RowId'] = actor
            if table == 'ActorInfo':
                model_row = by_id[spec['model']]
                row['ActorName'] = actor
                for key in ('FmdbName', 'ModelProjectName', 'ModelAabbMax', 'ModelAabbMin',
                            'ModelVariationFmabName', 'AnimationResources', 'ASInfoAutoPlayMaterials'):
                    if key in model_row:
                        row[key] = copy.deepcopy(model_row[key])
                row.update(spec.get('model_info', {}))
                row.update(copy.deepcopy(spec.get('actor_info', {})))
                row['InstanceHeapSize'] = max(row['InstanceHeapSize'], model_row['InstanceHeapSize'])
            rows.append(row)
        rows.sort(key=lambda row: row['__RowId'])
        modified[path] = byml_codec.dump(document)
    # 3. Saved IsGet flags for the new pouch actors.
    document = byml_codec.load(read_raw(GAMEDATA))
    data = document['root']['Data']
    known = {entry['Hash'] for entries in data.values() for entry in entries if 'Hash' in entry}
    sample = next(e for e in data['Bool'] if e['Hash'] == murmur3(FLAG_PREFIX + TEMPLATE))
    for actor in actors:
        value = murmur3(FLAG_PREFIX + actor)
        if value in known:
            raise ValueError('Flag collision for ' + actor)
        entry = copy.deepcopy(sample)
        entry['Hash'] = byml_codec.U32(value)
        entry['DefaultValue'] = False
        data['Bool'].append(entry)
    # The native pouch code writes IsGet.<ActorName> through the ``IsGet`` struct
    # (member murmur3(name) -> flag murmur3('IsGet.' + name)); a name missing from
    # the struct is silently not recorded. Chests and NPC gifts add the item by
    # name (GetPouchContent flow) without running the item's own event AI, so
    # without these members a soul found in a chest never set its flag and its
    # enemies (Queen Gohma in the Deku Tree map chest…) never appeared.
    members = next(e for e in data['Struct'] if e['Hash'] == murmur3(FLAG_PREFIX.rstrip('.')))['DefaultValue']
    template_member = next(m for m in members if m['Hash'] == murmur3(TEMPLATE))
    if template_member['Value'] != murmur3(FLAG_PREFIX + TEMPLATE):
        raise ValueError('Unexpected IsGet structure for souls.')
    present = {m['Hash'] for m in members}
    for actor in actors:
        if murmur3(actor) in present:
            raise ValueError('IsGet member already present for ' + actor)
        members.append({'Hash': byml_codec.U32(murmur3(actor)), 'Value': byml_codec.U32(murmur3(FLAG_PREFIX + actor))})
    meta = document['root']['MetaData']
    index, grown = sample['SaveFileIndex'], 8 * len(actors)
    meta['SaveDataSize'][index] += grown
    meta['SaveDataOffsetPos'][index] += grown
    meta['AllDataSaveSize'] += grown
    meta['AllDataSaveOffset'] += grown
    modified[GAMEDATA] = byml_codec.dump(document)
    # 4. Get-item texts (name shown when the soul is obtained).
    for path in message_archives:
        language = path.split('/')[-1].split('.')[0]
        modified[path] = patch_item_messages(read_raw(path), language,
                                             {spec['actor']: spec['texts'] for spec in specs})
    return modified, new


def is_boss_soul(key):
    """A boss soul: only required to enter the boss room, so it can be found in the same map."""
    return bool(BY_ID.get(key, (None, None, None))[2])


def soul_presence(flag, key, vanilla=None):
    """``Presence`` of an enemy bound to soul ``key``.

    A boss soul can be picked up inside its own dungeon (the logic only asks for it at
    the boss door), while the map is loaded: an immediate check (``IsCheckLazy`` false,
    read when the map loads) left the boss away until the dungeon was left and entered
    again, so the boss scene had no boss (15/11 report, Barinade). The lazy check, as the
    vanilla maps use for actors that appear or leave on a flag set in the map (Death
    Mountain Tektites, Enemy Museum statues), follows the flag live. Other souls keep
    the immediate check: the ones whose enemies drive something are required to enter
    their dungeon, and the others only bring back enemies the player can do without.

    ``vanilla``: the enemy's own Presence; the enemy then reads :func:`soul_expression`
    (lazy when either check is)."""
    if vanilla is not None:
        return {'FlagName': soul_expression(flag, vanilla), 'IsNegation': False,
                'IsCheckLazy': bool(vanilla.get('IsCheckLazy')) or is_boss_soul(key)}
    return {'FlagName': flag, 'IsNegation': False, 'IsCheckLazy': is_boss_soul(key)}


# GameData BoolExp programs are postfix (decoded on the vanilla list: KokiriForest_
# DeleteDekubaba = [10 Get_StoneOfForest_IsAfter_DefeatBoss_Exp] [0 <bool>] [5] [3],
# DreamWorldPlate_* = [10 a] [10 b] [4]): push a Bool (0) or a BoolExp (10), NOT (5),
# AND (3), OR (4). Values are U64; the entries are not saved (SaveFileIndex -1).
EXPRESSION_PREFIX = 'RandoSoul.'
PUSH = {'Bool': 0, 'BoolExp': 10}
OP_NOT, OP_AND = 5, 3


def soul_expression(flag, vanilla):
    """Name of the BoolExp "soul ``flag`` AND the enemy's vanilla Presence"."""
    negation = '.Not' if vanilla.get('IsNegation') else ''
    return f"{EXPRESSION_PREFIX}{flag[len(FLAG_PREFIX):]}.{vanilla['FlagName']}{negation}"


def expression_program(flag, vanilla, kind):
    """BoolExp ``Values`` of :func:`soul_expression`; ``kind``: 'Bool' or 'BoolExp' of the vanilla flag."""
    program = [[PUSH['Bool'], murmur3(flag)], [PUSH[kind], murmur3(vanilla['FlagName'])]]
    if vanilla.get('IsNegation'):
        program.append([OP_NOT])
    return program + [[OP_AND]]


def soul_expressions(gamedata_raw, edits):
    """{name: program} of the soul enemies that keep a vanilla Presence."""
    from oot_rando.formats import byml_codec
    data = byml_codec.load(gamedata_raw)['root']['Data']
    kinds = {int(e['Hash']): kind for kind in PUSH for e in data[kind]}
    found = {}
    for edit in edits:
        vanilla = edit.get('vanilla')
        if vanilla is None:
            continue
        name = soul_expression(edit['flag'], vanilla)
        kind = kinds.get(murmur3(vanilla['FlagName']))
        if kind is None:
            raise ValueError('Soul enemy condition not in the game data: ' + name)
        program = expression_program(edit['flag'], vanilla, kind)
        if found.setdefault(name, program) != program:
            raise ValueError('Two programs for one soul condition: ' + name)
    return found


def add_soul_expressions(gamedata_raw, edits):
    """GameData with the BoolExps of the soul enemies that keep a vanilla Presence.

    Run once the soul flags exist (their ``IsGet`` Bools are read by the programs)."""
    from oot_rando.formats import byml_codec
    programs = soul_expressions(gamedata_raw, edits)
    if not programs:
        return gamedata_raw
    document = byml_codec.load(gamedata_raw)
    data = document['root']['Data']
    known = {int(e['Hash']) for entries in data.values() for e in entries if 'Hash' in e}
    bools = {int(e['Hash']) for e in data['Bool']}
    for name, program in sorted(programs.items()):
        if murmur3(name) in known:
            raise ValueError('Soul condition name collision: ' + name)
        if program[0][1] not in bools:
            raise ValueError('Soul flag missing for: ' + name)
        data['BoolExp'].append({'Hash': byml_codec.U32(murmur3(name)), 'ResetTypeValue': 0, 'SaveFileIndex': -1,
                                'Values': [[byml_codec.U64(v) for v in step] for step in program]})
        known.add(murmur3(name))
    return byml_codec.dump(document)


def presence_changes(edits, roots):
    """BYML edits giving every soul-bound enemy its soul ``Presence``.

    Added when absent; an enemy with its own Presence (``edit['vanilla']``) reads
    the soul's BoolExp instead (:func:`add_soul_expressions`)."""
    changes = defaultdict(list)
    for edit in edits:
        actor = roots[edit['resource']]['Actors'][edit['index']]
        vanilla = edit.get('vanilla')
        if (actor.get('Gyaml') != edit['actor'] or str(actor.get('Hash')) != edit['hash']
                or actor.get('Presence') != vanilla):
            raise ValueError('Unexpected enemy for souls: ' + edit['hash'])
        base = ('Actors', edit['index'], 'Presence')
        presence = soul_presence(edit['flag'], edit['soul'], vanilla)
        changes[edit['resource']] += [{'path': base + (name,), 'before': (vanilla or {}).get(name),
                                       'after': presence[name]}
                                      for name in ('FlagName', 'IsNegation', 'IsCheckLazy')
                                      if vanilla is None or vanilla.get(name) != presence[name]]
    return dict(changes)
