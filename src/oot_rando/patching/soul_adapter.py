"""Enemy souls (OoTR Dev-Rob ``shuffle_enemy_spawns``) for the remake.

An enemy whose family soul has not been obtained does not appear. The remake
already supports conditional presence on map actors::

    "Presence": {"FlagName": <name>, "IsNegation": false, "IsCheckLazy": false}

and records ``IsGet.<actor>`` flags for obtained pouch actors (murmur3 hash of
the name, verified on the local data). Each soul is therefore a new pouch actor
``Item_Soul_<Family>`` built from the Forest Medallion key-item template with the
Poe soul model, plus a saved ``IsGet.Item_Soul_<Family>`` flag. Enemies that
already carry a Presence condition keep it and stay soul-independent.

Logic (conservative): entering a dungeon requires the souls of every family
patched in that dungeon, entering a boss room requires the boss soul, chests
that appear on a condition require the souls of their map, and named overworld
enemy checks require their family soul.
"""
from collections import defaultdict

from oot_rando.game.remake_world import FOLDER_AP_DUNGEON

# (family id, French label, Gyaml prefixes, boss room AP region or None)
FAMILIES = [
    ('Stalfos', 'Stalfos', ('Enemy_Stalfos',), None),
    ('Octorok', 'Octorok', ('Enemy_Octorok',), None),
    ('BigOcto', 'Gros Octorok', ('Enemy_MiddleBoss_BigOcto',), None),
    ('Wallmaster', 'Main Mortelle', ('Enemy_Wallmaster',), None),
    ('Floormaster', 'Main Mortelle au sol', ('Enemy_Floormaster',), None),
    ('Dodongo', 'Dodongo', ('Enemy_Dodongo',), None),
    ('BabyDodongo', 'Bébé Dodongo', ('Enemy_BabyDodongo',), None),
    ('Keese', 'Keese', ('Enemy_Keese',), None),
    ('Tektite', 'Araknon', ('Enemy_Tektite',), None),
    ('Peahat', 'Pihat', ('Enemy_Peahat',), None),
    ('Lizalfos', 'Lézalfos et Dinolfos', ('Enemy_Lizalfos', 'Enemy_MiddleBoss_Lizalfos', 'Enemy_Dinolfos'), None),
    ('GohmaLarva', 'Larves de Gohma', ('Enemy_Gohma_Larva', 'Enemy_Gohma_Egg'), None),
    ('Shabom', 'Shabom', ('Enemy_Shabom',), None),
    ('BiriBari', 'Biri et Bari', ('Enemy_Biri', 'Enemy_Bari'), None),
    ('Tailpasaran', 'Tailpasaran', ('Enemy_Tailpasaran',), None),
    ('TorchSlug', 'Limace de feu', ('Enemy_TorchSlug',), None),
    ('Skulltula', 'Skulltula', ('Enemy_Skulltula',), None),
    ('Skullwalltula', 'Skullwalltula', ('Enemy_Skullwalltula',), None),
    ('Moblin', 'Moblin', ('Enemy_Moblin',), None),
    ('Armos', 'Armos', ('Enemy_Amos',), None),
    ('Beamos', 'Beamos', ('Enemy_Beamos',), None),
    ('DekuBaba', 'Baba Mojo', ('Enemy_Dekubaba',), None),
    ('DekuScrub', 'Peste Mojo', ('Enemy_Scrub_Deku', 'Enemy_Scrub_Mad'), None),
    ('Bubble', 'Bubble', ('Enemy_Bubble',), None),
    ('ReDead', 'ReDead et Gibdo', ('Enemy_ReDead', 'Enemy_Gibdo'), None),
    ('DeadHand', 'Main Morte', ('Enemy_DeadHand',), None),
    ('FlareDancer', 'Danse-Flamme', ('Enemy_MiddleBoss_FlareDancer',), None),
    ('ShellBlade', 'Coquillame', ('Enemy_ShellBlade',), None),
    ('LikeLike', 'Like Like', ('Enemy_LikeLike',), None),
    ('Spike', 'Hérisson', ('Enemy_Spike',), None),
    ('Anubis', 'Anubis', ('Enemy_Anubis',), None),
    ('IronKnuckle', 'Hache-Viande', ('Enemy_IronKnuckle',), None),
    ('FlyingPot', 'Jarre volante', ('Enemy_FlyingPot',), None),
    ('Freezard', 'Freezard', ('Enemy_Freezard',), None),
    ('Stinger', 'Raie', ('Enemy_Stinger',), None),
    ('Wolfos', 'Wolfos', ('Enemy_Wolfos',), None),
    ('Guay', 'Guay', ('Enemy_Guay', 'Enemy_FlockGuayManager'), None),
    ('JabuTentacle', 'Tentacules de Jabu', ('Enemy_Tentacle',), None),
    ('DarkLink', 'Link Noir', ('Enemy_MiddleBoss_DarkLink',), None),
    ('Gohma', 'Reine Gohma', ('Enemy_DungeonBoss_Gohma',), 'Queen Gohma Boss Room'),
    ('KingDodongo', 'King Dodongo', ('Enemy_DungeonBoss_Dodongo',), 'King Dodongo Boss Room'),
    ('Barinade', 'Barinade', ('Enemy_DungeonBoss_Barinade',), 'Barinade Boss Room'),
    ('PhantomGanon', 'Ganon Spectral', ('Enemy_DungeonBoss_PhantomGanon',), 'Phantom Ganon Boss Room'),
    ('Volvagia', 'Volvagia', ('Enemy_DungeonBoss_Volvagia',), 'Volvagia Boss Room'),
    ('Morpha', 'Morpha', ('Enemy_DungeonBoss_Morpha',), 'Morpha Boss Room'),
    ('BongoBongo', 'Bongo Bongo', ('Enemy_DungeonBoss_BongoBongo',), 'Bongo Bongo Boss Room'),
    ('Twinrova', 'Twinrova', ('Enemy_DungeonBoss_Twinrova', 'Enemy_DungeonBoss_Kotake',
                              'Enemy_DungeonBoss_Koume', 'Enemy_KotakeKoumeBattleManager'), 'Twinrova Boss Room'),
]
BY_ID = {family: (label, prefixes, boss) for family, label, prefixes, boss in FAMILIES}
EXCLUDED_MARKERS = ('_Dictionary', 'Haribote', 'ClimaxOnly', 'GhostPicturePerformer', 'Skulltula_Gold',
                    'Scrub_Business', 'Scrub_ForestStage', 'IronKnuckle_Nabooru', 'SkullKid', 'Poe',
                    'Stalchild', 'Leever', 'GerudoThief', 'Ganon', 'CrazyFloorTile', 'TrickyDoor')
EXCLUDED_FOLDERS = ('DreamWorld', 'GanonCastle')
# French in-game names (EUfr / CAfr message files); FAMILIES labels are French too.
REGION_LABELS = {
    'InsideTheDekuTree': 'Arbre Mojo', 'DodongoCavern': 'Caverne Dodongo', 'InsideJabuJabuBelly': 'Jabu-Jabu',
    'ForestTemple': 'Temple de la Forêt', 'FireTemple': 'Temple du Feu', 'WaterTemple': 'Temple de l’Eau',
    'ShadowTemple': 'Temple de l’Ombre', 'SpiritTemple': 'Temple de l’Esprit', 'BottomOfTheWell': 'Puits',
    'IceCavern': 'Caverne Polaire', 'GerudoTrainingGround': 'Gymnase Gerudo', 'InsideGanonCastle': 'Château de Ganon',
    'KokiriForest': 'Forêt Kokiri', 'LostWood': 'Bois Perdus', 'SacredForestMeadow': 'Bosquet sacré',
    'HyruleField': 'Plaine d’Hyrule', 'Market': 'Bourg', 'HyruleCastle': 'Château d’Hyrule',
    'Graveyard': 'Cimetière', 'DeathMountainTrail': 'Mont du Péril', 'DeathMountainCrater': 'Cratère',
    'ZoraRiver': 'Rivière Zora', 'ZoraFountain': 'Fontaine Zora', 'GerudoValley': 'Vallée Gerudo',
    'GerudoFortress': 'Forteresse Gerudo', 'HountedWasteland': 'Désert hanté', 'DesertColossus': 'Colosse',
    'LakeHylia': 'Lac Hylia', 'KakarikoVillage': 'Cocorico', 'GoronCity': 'Village Goron', 'ZoraDomain': 'Domaine Zora',
}
LOCATION_KEYWORDS = {'Wolfos': 'Wolfos', 'Redead': 'ReDead', 'Moblin': 'Moblin', 'Octorok': 'Octorok',
                     'Tektite': 'Tektite', 'Deku Baba': 'DekuBaba', 'Dodongo': 'Dodongo', 'Peahat': 'Peahat'}
FLAG_PREFIX = 'IsGet.'


def family_of(actor):
    if any(marker in actor for marker in EXCLUDED_MARKERS):
        return None
    best = None
    for family, _, prefixes, _ in FAMILIES:
        for prefix in prefixes:
            if (actor == prefix or actor.startswith(prefix + '_')) and (best is None or len(prefix) > best[1]):
                best = (family, len(prefix))
    return best[0] if best else None


def soul_item(key):
    return f'Soul ({key})'


def soul_actor(item):
    key = item[len('Soul ('):-1]
    return 'Item_Soul_' + key.replace('Region:', 'Region_')


def soul_label(item):
    return 'Soul: ' + soul_name(item, False)


def _spaced(name):
    return ''.join(' ' + c if c.isupper() and i else c for i, c in enumerate(name))


def soul_name(item, french=True):
    """Display name of the soul (without the "Soul" prefix)."""
    key = item[len('Soul ('):-1]
    if key.startswith('Region:'):
        folder = key[7:]
        return REGION_LABELS.get(folder, folder) if french else ENGLISH_REGIONS.get(folder, _spaced(folder))
    return BY_ID[key][0] if french else ENGLISH_FAMILIES.get(key, _spaced(key))


ENGLISH_FAMILIES = {'BigOcto': 'Big Octo', 'Wallmaster': 'Wallmaster', 'Floormaster': 'Floormaster',
                    'BabyDodongo': 'Baby Dodongo', 'Lizalfos': 'Lizalfos and Dinolfos',
                    'GohmaLarva': 'Gohma Larva', 'BiriBari': 'Biri and Bari', 'TorchSlug': 'Torch Slug',
                    'DekuBaba': 'Deku Baba', 'DekuScrub': 'Deku Scrub', 'ReDead': 'ReDead and Gibdo',
                    'DeadHand': 'Dead Hand', 'FlareDancer': 'Flare Dancer', 'ShellBlade': 'Shell Blade',
                    'LikeLike': 'Like Like', 'IronKnuckle': 'Iron Knuckle', 'FlyingPot': 'Flying Pot',
                    'JabuTentacle': 'Jabu-Jabu Tentacles', 'DarkLink': 'Dark Link', 'Gohma': 'Queen Gohma',
                    'KingDodongo': 'King Dodongo', 'PhantomGanon': 'Phantom Ganon', 'BongoBongo': 'Bongo Bongo'}
ENGLISH_REGIONS = {'InsideTheDekuTree': 'Deku Tree', 'DodongoCavern': "Dodongo's Cavern",
                   'InsideJabuJabuBelly': "Jabu-Jabu's Belly", 'BottomOfTheWell': 'Bottom of the Well',
                   'InsideGanonCastle': "Ganon's Castle", 'LostWood': 'Lost Woods',
                   'HountedWasteland': 'Haunted Wasteland', 'Market': 'Market', 'ZoraRiver': "Zora's River",
                   'ZoraFountain': "Zora's Fountain", 'ZoraDomain': "Zora's Domain"}


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
    edits = []
    candidates = []
    for enemy in enemies:
        if enemy['folder'] in EXCLUDED_FOLDERS or enemy['presence'] is not None:
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
        if boss and mode != 'regional':
            boss_rooms[boss] = key
        else:
            per_folder[enemy['folder']].add(key)
            per_map[enemy['resource']].add(key)
        edits.append({'resource': enemy['resource'], 'index': enemy['index'], 'actor': enemy['actor'],
                      'hash': enemy['hash'], 'soul': key, 'flag': FLAG_PREFIX + soul_actor(soul_item(key))})
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
            if requirement:
                exit_requirements[(name, target)] = requirement
    location_requirements = {}
    if mode == 'all' and 'DekuBaba' in patched:
        for location in ('Deku Baba Sticks', 'Deku Baba Nuts'):
            location_requirements[location] = {soul_item('DekuBaba')}
    return {'items': sorted(soul_item(k) for k in patched), 'edits': edits, 'door_edits': door_edits,
            'exit_requirements': exit_requirements,
            'location_requirements': location_requirements, 'per_map': {k: sorted(v) for k, v in per_map.items()},
            'families': {k: sorted(v) for k, v in patched.items()}, 'mode': mode}


def chest_requirements(plan, group, ap_locations):
    """Extra souls for one remake chest group (conditional chests, named enemies)."""
    if not plan['items']:
        return set()
    required = set()
    for variant in group['variants']:
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


def murmur3(text, seed=0):
    data = text.encode('utf-8')
    h, c1, c2, n = seed, 0xcc9e2d51, 0x1b873593, len(data)
    for i in range(0, n // 4 * 4, 4):
        k = int.from_bytes(data[i:i + 4], 'little')
        k = (k * c1) & 0xffffffff
        k = ((k << 15) | (k >> 17)) & 0xffffffff
        h ^= (k * c2) & 0xffffffff
        h = ((h << 13) | (h >> 19)) & 0xffffffff
        h = (h * 5 + 0xe6546b64) & 0xffffffff
    tail, k = data[n // 4 * 4:], 0
    for i, byte in enumerate(tail):
        k |= byte << (8 * i)
    if tail:
        k = (k * c1) & 0xffffffff
        k = ((k << 15) | (k >> 17)) & 0xffffffff
        h ^= (k * c2) & 0xffffffff
    h ^= n
    h ^= h >> 16
    h = (h * 0x85ebca6b) & 0xffffffff
    h ^= h >> 13
    h = (h * 0xc2b2ae35) & 0xffffffff
    h ^= h >> 16
    return h


MESSAGE_FILE = 'ActorMsg/PouchContent.msbt'


def soul_event_name(actor):
    return 'RandoSoul_' + actor[len('Item_Soul_'):] + '.event.root'


def soul_event_member(actor):
    """Pack member of the soul's get event (beside its actor parameters)."""
    return 'AI/' + soul_event_name(actor) + '.ainb'


def soul_event_ain(actor):
    return 'Work/AI/Root/Event/' + soul_event_name(actor) + '.ain'


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


def presence_changes(edits, roots):
    """BYML edits adding ``Presence`` to every soul-bound enemy (absent before)."""
    changes = defaultdict(list)
    for edit in edits:
        actor = roots[edit['resource']]['Actors'][edit['index']]
        if actor.get('Gyaml') != edit['actor'] or str(actor.get('Hash')) != edit['hash'] or 'Presence' in actor:
            raise ValueError('Unexpected enemy for souls: ' + edit['hash'])
        base = ('Actors', edit['index'], 'Presence')
        changes[edit['resource']] += [{'path': base + ('FlagName',), 'before': None, 'after': edit['flag']},
                                      {'path': base + ('IsNegation',), 'before': None, 'after': False},
                                      {'path': base + ('IsCheckLazy',), 'before': None, 'after': False}]
    return dict(changes)
