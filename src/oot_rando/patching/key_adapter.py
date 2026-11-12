"""Dungeon-specific keys: key rings and boss keys usable outside their dungeon.

The remake's keys are generic: ``Item_Dungeon_SmallKey``/``Item_Dungeon_BossKey``
are credited by native code (``EventGetDungeonSmallKey``…) to the dungeon the
player stands in. Each dungeon keeps its state in the saved GameData struct
``DungeonInfo.<folder>`` (RSDB ``DungeonParam`` rows, verified on the local data):
``.SmallKeyNum`` (Int, keys held, used by the locked doors), ``.IsGetBossKey``
(Bool), ``.IsGetMap``, ``.IsGetCompass``.

As in OoTR, a dungeon can get one *key ring* (every small key of the dungeon at
once) and its boss key can become an item of its own, both placeable anywhere:

* new pouch actors ``Item_KeyRing_<folder>`` and ``Item_BossKey_<folder>`` built
  like the souls (Forest Medallion key-item template, model of the native key);
* every item-get flow ends in ``ActionGuide/ActionGuide`` (see
  ``qol_patches.ocarina_guide_on_get``): it first checks each key item of the
  seed; a ring in the pouch not yet applied adds its keys to ``SmallKeyNum``
  once (saved flag ``RandoKeyRing.<folder>``), a boss key in the pouch sets
  ``IsGetBossKey``. A key obtained by a path that skips the get flow is applied
  on the next item get.

A ring gives the AP number of keys of the dungeon (never fewer than the remake's
locked doors seen in the maps): an extra key is harmless. Not validated in game.
"""
import io

from oot_rando.game.remake_world import FOLDER_DUNGEON

RING_PREFIX = 'Item_KeyRing_'
BOSS_PREFIX = 'Item_BossKey_'
MAP_PREFIX = 'Item_DungeonMap_'
COMPASS_PREFIX = 'Item_DungeonCompass_'
# Dungeon-specific items of this module: actor prefix -> (AP item kind, model, GameData field).
SPECIFIC = {RING_PREFIX: ('Small Key Ring', 'Item_Dungeon_SmallKey', 'SmallKeyNum'),
            BOSS_PREFIX: ('Boss Key', 'Item_Dungeon_BossKey', 'IsGetBossKey'),
            MAP_PREFIX: ('Map', 'Item_Dungeon_Map', 'IsGetMap'),
            COMPASS_PREFIX: ('Compass', 'Item_Dungeon_Compass', 'IsGetCompass')}
APPLIED_PREFIX = 'RandoKeyRing.'
SMALL_KEY_MODEL = 'Item_Dungeon_SmallKey'
BOSS_KEY_MODEL = 'Item_Dungeon_BossKey'
ACTION_GUIDE_FLOW = 'Event/EventFlow/ActionGuide.bfevfl.zs'
ACTION_GUIDE_ENTRY = 'ActionGuide'
# Dungeons with small keys (AP vanilla count, Thieves' Hideout apart) and with a boss key.
RING_DUNGEONS = {
    'ForestTemple': 5, 'FireTemple': 8, 'WaterTemple': 6, 'ShadowTemple': 5, 'SpiritTemple': 5,
    'BottomOfTheWell': 3, 'GerudoTrainingGround': 9, 'InsideGanonCastle': 2,
}
BOSS_KEY_DUNGEONS = ('ForestTemple', 'FireTemple', 'WaterTemple', 'ShadowTemple', 'SpiritTemple')
# Dungeons with a map and a compass (AP items ``Map (…)``/``Compass (…)``).
MAP_DUNGEONS = ('InsideTheDekuTree', 'DodongoCavern', 'InsideJabuJabuBelly', 'ForestTemple', 'FireTemple',
                'WaterTemple', 'ShadowTemple', 'SpiritTemple', 'BottomOfTheWell', 'IceCavern')
DUNGEON_FOLDER = {dungeon: folder for folder, dungeon in FOLDER_DUNGEON.items()}
# In-game names for the French message files (EUfr / CAfr).
FRENCH_DUNGEONS = {
    'ForestTemple': 'Temple de la Forêt', 'FireTemple': 'Temple du Feu', 'WaterTemple': 'Temple de l’Eau',
    'ShadowTemple': 'Temple de l’Ombre', 'SpiritTemple': 'Temple de l’Esprit',
    'BottomOfTheWell': 'Puits de Cocorico', 'GerudoTrainingGround': 'Gymnase Gerudo',
    'InsideGanonCastle': 'Château de Ganon',
}
ENGLISH_DUNGEONS = {
    'ForestTemple': 'Forest Temple', 'FireTemple': 'Fire Temple', 'WaterTemple': 'Water Temple',
    'ShadowTemple': 'Shadow Temple', 'SpiritTemple': 'Spirit Temple', 'BottomOfTheWell': 'Bottom of the Well',
    'GerudoTrainingGround': 'Gerudo Training Ground', 'InsideGanonCastle': "Ganon's Castle",
}


def ring_item(folder):
    return f'Small Key Ring ({FOLDER_DUNGEON[folder]})'


def small_key_item(folder):
    return f'Small Key ({FOLDER_DUNGEON[folder]})'


def is_ring(item):
    return item.startswith('Small Key Ring (')


def item_folder(item):
    """Dungeon folder of a key item (``Small Key Ring (X)``, ``Boss Key (X)``…)."""
    return DUNGEON_FOLDER[item[item.index('(') + 1:-1]]


def ring_actor(folder):
    return RING_PREFIX + folder


def boss_actor(folder):
    return BOSS_PREFIX + folder


def map_actor(folder):
    return MAP_PREFIX + folder


def compass_actor(folder):
    return COMPASS_PREFIX + folder


def specific_actor(item):
    """Dungeon-specific actor of a ring, boss key, map or compass AP item."""
    for prefix, (kind, _, _) in SPECIFIC.items():
        if item.startswith(kind + ' ('):
            return prefix + item_folder(item)
    raise ValueError('Not a dungeon item: ' + item)


def _split(actor):
    for prefix in SPECIFIC:
        if actor.startswith(prefix) and actor[len(prefix):] in FOLDER_DUNGEON:
            return prefix, actor[len(prefix):]
    return None, None


def key_actor_item(actor):
    """AP item of a dungeon-specific key actor, or None."""
    prefix, folder = _split(actor)
    return f'{SPECIFIC[prefix][0]} ({FOLDER_DUNGEON[folder]})' if prefix else None


def is_key_actor(actor):
    return key_actor_item(actor) is not None


def key_texts(actor, language):
    prefix, folder = _split(actor)
    ring = prefix == RING_PREFIX
    if prefix in (MAP_PREFIX, COMPASS_PREFIX):
        return dungeon_item_texts(prefix == MAP_PREFIX, folder, language)
    if language.endswith('fr'):
        name = FRENCH_DUNGEONS[folder]
        if ring:
            return {'Name': f'Trousseau : {name}',
                    'Caption': f'Toutes les petites clés du donjon « {name} ».',
                    'GetMessage': f'Vous avez obtenu le trousseau du donjon : {name} !',
                    'GetCaption': 'Ses portes verrouillées peuvent maintenant s’ouvrir.'}
        return {'Name': f'Clé du boss : {name}',
                'Caption': f'La grande clé du donjon « {name} ».',
                'GetMessage': f'Vous avez obtenu la clé du boss : {name} !',
                'GetCaption': 'Elle ouvre la porte du boss de ce donjon.'}
    name = ENGLISH_DUNGEONS[folder]
    if ring:
        return {'Name': f'Key Ring: {name}', 'Caption': f'Every small key of the {name}.',
                'GetMessage': f'You got the {name} key ring!', 'GetCaption': 'Its locked doors can now open.'}
    return {'Name': f'Boss Key: {name}', 'Caption': f'The boss key of the {name}.',
            'GetMessage': f'You got the {name} boss key!', 'GetCaption': 'It opens the boss door of this dungeon.'}


def dungeon_item_texts(is_map, folder, language):
    if language.endswith('fr'):
        name = FRENCH_DUNGEON_NAMES[folder]
        if is_map:
            return {'Name': f'Carte : {name}', 'Caption': f'La carte du donjon « {name} ».',
                    'GetMessage': f'Vous avez obtenu la carte du donjon : {name} !',
                    'GetCaption': 'Le plan du donjon apparaît dans le menu.'}
        return {'Name': f'Boussole : {name}', 'Caption': f'La boussole du donjon « {name} ».',
                'GetMessage': f'Vous avez obtenu la boussole du donjon : {name} !',
                'GetCaption': 'Les coffres du donjon apparaissent sur la carte.'}
    name = ENGLISH_DUNGEON_NAMES[folder]
    if is_map:
        return {'Name': f'Map: {name}', 'Caption': f'The dungeon map of the {name}.',
                'GetMessage': f'You got the {name} map!', 'GetCaption': 'The dungeon layout is now shown in the menu.'}
    return {'Name': f'Compass: {name}', 'Caption': f'The compass of the {name}.',
            'GetMessage': f'You got the {name} compass!', 'GetCaption': 'The dungeon chests now show on the map.'}


def start_dungeon_values(options):
    """GameData values written at the end of the opening for the "start with" / "removed" modes.

    * maps and compasses "Start with": ``IsGetMap``/``IsGetCompass`` of every dungeon;
    * small keys "Removed": ``SmallKeyNum`` = every key of the dungeon (AP count),
      so the locked doors open as if the keys were found (an extra key is harmless);
    * boss keys "Removed": ``IsGetBossKey`` of the five temples (Ganon's key apart).
    """
    values = {}
    if options.get('shuffle_mapcompass') == 'startwith':
        for folder in MAP_DUNGEONS:
            values[f'DungeonInfo.{folder}.IsGetMap'] = True
            values[f'DungeonInfo.{folder}.IsGetCompass'] = True
    if options.get('shuffle_smallkeys') == 'remove':
        for folder, count in RING_DUNGEONS.items():
            values[f'DungeonInfo.{folder}.SmallKeyNum'] = count
    if options.get('shuffle_bosskeys') == 'remove':
        for folder in BOSS_KEY_DUNGEONS:
            values[f'DungeonInfo.{folder}.IsGetBossKey'] = True
    return values


def start_logic_items(options):
    """AP items the logic holds from the start for the "removed" key modes."""
    items = {}
    if options.get('shuffle_smallkeys') == 'remove':
        items.update({small_key_item(folder): count for folder, count in RING_DUNGEONS.items()})
    if options.get('shuffle_bosskeys') == 'remove':
        items.update({f'Boss Key ({FOLDER_DUNGEON[folder]})': 1 for folder in BOSS_KEY_DUNGEONS})
    return items


def check_start_values(gamedata_raw, values):
    """Every start value names a saved GameData entry of the matching type."""
    from oot_rando.formats.inspect_resources import Byml
    from oot_rando.patching.soul_adapter import murmur3
    data = Byml(gamedata_raw).root['Data']
    for name, value in values.items():
        kind = 'Bool' if type(value) is bool else 'Int'
        entry = next((e for e in data[kind] if e['Hash'] == murmur3(name)), None)
        if entry is None or entry.get('SaveFileIndex') != 0:
            raise ValueError('Start value not found in the saved game data: ' + name)


FRENCH_DUNGEON_NAMES = dict(FRENCH_DUNGEONS, InsideTheDekuTree='Arbre Mojo', DodongoCavern='Caverne Dodongo',
                            InsideJabuJabuBelly='Ventre de Jabu-Jabu', IceCavern='Caverne Polaire')
ENGLISH_DUNGEON_NAMES = dict(ENGLISH_DUNGEONS, InsideTheDekuTree='Deku Tree', DodongoCavern="Dodongo's Cavern",
                             InsideJabuJabuBelly="Jabu-Jabu's Belly", IceCavern='Ice Cavern')


def key_specs(actors):
    specs = []
    for actor in sorted(actors):
        name = 'RandoKey_' + actor[len('Item_'):] + '.event.root'
        specs.append({'actor': actor, 'model': SPECIFIC[_split(actor)[0]][1],
                      'event_name': name, 'event_member': 'AI/' + name + '.ainb',
                      'event_ain': 'Work/AI/Root/Event/' + name + '.ain',
                      'texts': (lambda language, actor=actor: key_texts(actor, language))})
    return specs


def key_records(items):
    """Hook records for the key items of a seed (AP item names)."""
    records = []
    for item in sorted(set(items)):
        folder = item_folder(item)
        if is_ring(item):
            records.append({'kind': 'ring', 'actor': ring_actor(folder), 'folder': folder,
                            'count': RING_DUNGEONS[folder], 'applied': APPLIED_PREFIX + folder,
                            'gamedata': f'DungeonInfo.{folder}.SmallKeyNum'})
        else:
            actor = specific_actor(item)
            kind = {BOSS_PREFIX: 'boss', MAP_PREFIX: 'map', COMPASS_PREFIX: 'compass'}[_split(actor)[0]]
            records.append({'kind': kind, 'actor': actor, 'folder': folder,
                            'gamedata': f'DungeonInfo.{folder}.{SPECIFIC[_split(actor)[0]][2]}'})
    return records


def build_key_files(read_raw, records, message_archives=()):
    """``(modified, new)`` resources of the key actors, plus their saved flags."""
    from oot_rando.patching.soul_adapter import build_item_files, GAMEDATA
    from oot_rando.game.tracking_metadata import add_saved_flags
    if not records:
        return {}, {}
    modified, new = build_item_files(read_raw, key_specs(r['actor'] for r in records), message_archives)
    applied = {r['applied']: False for r in records if r['kind'] == 'ring'}
    if applied:
        raw = modified.get(GAMEDATA)
        modified[GAMEDATA] = add_saved_flags(raw if raw is not None else read_raw(GAMEDATA), applied)
    return modified, new


def check_dungeon_data(gamedata_raw, records):
    """Every GameData name written by the hook exists (saved) in the game."""
    from oot_rando.formats.inspect_resources import Byml
    from oot_rando.patching.soul_adapter import murmur3
    data = Byml(gamedata_raw).root['Data']
    types = {'ring': 'Int', 'boss': 'Bool', 'map': 'Bool', 'compass': 'Bool'}
    for record in records:
        entries = {e['Hash']: e for e in data[types[record['kind']]]}
        entry = entries.get(murmur3(record['gamedata']))
        if entry is None or entry.get('SaveFileIndex') != 0:
            raise ValueError('Dungeon data not found: ' + record['gamedata'])


def add_key_hook(raw, records):
    """Prepend the key checks to ``ActionGuide/ActionGuide``. Returns (bytes, report).

    Bool switches: case 0 = true (as the vanilla flows).
    """
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.event import Event, ActionEvent, SwitchEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import _flow, _snapshot, GAMEDATA_ACTOR_PARAMS
    flow = _flow(raw)
    chart = flow.flowchart
    expected = _snapshot(flow)
    entries = {e.name: e for e in chart.entry_points}
    if ACTION_GUIDE_ENTRY not in entries or entries[ACTION_GUIDE_ENTRY].main_event.v is None:
        raise ValueError('Flow ActionGuide inattendu.')
    if any(e.name.startswith('RandoKey') for e in chart.events):
        raise ValueError('ActionGuide flow already has the keys.')

    def system_actor(name, params):
        actor = next((a for a in chart.actors if a.identifier.name == name and a.identifier.sub_name == ''), None)
        if actor is None:
            actor = Actor()
            actor.identifier = ActorIdentifier(name)
            actor.concurrent_clips = 1
            actor.params = Container()
            actor.params.data = dict(params)
            chart.actors.append(actor)
        return actor

    def holder(collection, name):
        found = next((h for h in collection if h.v == name), None)
        if found is None:
            found = StringHolder(name)
            collection.append(found)
        return found

    pouch = system_actor('PouchSystemActor', {})
    # A named actor without its parameter container crashes the game (seen with
    # GameDataActor at the end of the intro): vanilla parameters.
    gamedata = system_actor('GameDataActor', GAMEDATA_ACTOR_PARAMS)
    in_pouch = holder(pouch.queries, 'EventQueryIsExistInPouch')
    is_bool = holder(gamedata.queries, 'EventQueryIsGameDataBool')
    set_bool = holder(gamedata.actions, 'EventTriggerSetGameDataBool')
    add_int = holder(gamedata.actions, 'EventTriggerAddOrSubGameDataInt')

    def event(name, data):
        e = Event()
        e.name, e.data = name, data
        chart.events.append(e)
        return e

    def action(name, actor, act, params):
        data = ActionEvent()
        data.actor, data.actor_action = make_rindex(actor), make_rindex(act)
        data.params = Container()
        data.params.data = dict(params)
        expected[name] = dict(params)
        return event(name, data)

    def switch(name, actor, query, params, true, false):
        data = SwitchEvent()
        data.actor, data.actor_query = make_rindex(actor), make_rindex(query)
        data.params = Container()
        data.params.data = dict(params)
        data.cases = {0: make_index(true), 1: make_index(false)}
        expected[name] = dict(params)
        return event(name, data)

    entry = entries[ACTION_GUIDE_ENTRY]
    following = entry.main_event.v
    report = []
    # Built from the last record backwards: each check continues to the next one.
    for record in reversed(records):
        stem = record['actor'][len('Item_'):]
        if record['kind'] == 'ring':
            mark = action(f'RandoKeyApplied_{stem}', gamedata, set_bool,
                          {'GameDataName': record['applied'], 'Value': True, 'Index': -1})
            mark.data.nxt = make_index(following)
            give = action(f'RandoKeyGive_{stem}', gamedata, add_int,
                          {'GameDataName': record['gamedata'], 'Value': record['count'], 'Index': -1})
            give.data.nxt = make_index(mark)
            done = switch(f'RandoKeyDone_{stem}', gamedata, is_bool,
                          {'GameDataName': record['applied'], 'Index': -1}, following, give)
            first = switch(f'RandoKeyHeld_{stem}', pouch, in_pouch,
                           {'Actor': record['actor'], 'Num': 1}, done, following)
        else:
            give = action(f'RandoKeyGive_{stem}', gamedata, set_bool,
                          {'GameDataName': record['gamedata'], 'Value': True, 'Index': -1})
            give.data.nxt = make_index(following)
            first = switch(f'RandoKeyHeld_{stem}', pouch, in_pouch,
                           {'Actor': record['actor'], 'Num': 1}, give, following)
        report.append({'actor': record['actor'], 'start': first.name})
        following = first
    entry.main_event = make_index(following)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = _flow(result)
    if _snapshot(checked) != expected:
        raise ValueError('Dungeon keys changed other parameters.')
    start = {e.name: e for e in checked.flowchart.entry_points}[ACTION_GUIDE_ENTRY].main_event.v
    if records and start.name != f"RandoKeyHeld_{records[0]['actor'][len('Item_'):]}":
        raise ValueError('ActionGuide entry wrongly attached to the keys.')
    return result, list(reversed(report))
