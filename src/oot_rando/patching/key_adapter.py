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
  seed; a ring got not yet applied adds its keys to ``SmallKeyNum``
  and ``SmallKeyTotalNum`` (keys found, credited too by the native key get)
  once (saved flag ``RandoKeyRing.<folder>``), a boss key got sets
  ``IsGetBossKey``. A key obtained by a path that skips the get flow is applied
  on the next item get.

Maps and compasses work the same way (``Item_Map_<folder>``, ``Item_Compass_<folder>``:
``IsGetMap``/``IsGetCompass``). The native ones are only credited by the big chest
sequence (``Dm_SY_Treasurebox/Success_AddContent``: ``EventGetDungeonMap``, to the
dungeon Link stands in); from a small chest, a pickup or an NPC the native map was
shown and credited nothing (Discord 16/11, 0.6.5: Forest Temple map still "???").

"Got" is the saved ``IsGet.<actor>`` Bool the pouch writes for a generated actor (as
for the souls and the progressive tokens), not ``EventQueryIsExistInPouch``: in game
(Longshot, 16/11) a Forest Temple ring in the pouch left ``IsGet`` true but the pouch
query false, so the keys were never added.

A ring gives the AP number of keys of the dungeon (never fewer than the remake's
locked doors seen in the maps): an extra key is harmless. Not validated in game.
"""
import io

from oot_rando.game.remake_world import FOLDER_DUNGEON

from oot_rando.catalog.keys import (  # noqa: F401  (moved to oot_rando.catalog.keys, re-exported)
    RING_PREFIX,
    BOSS_PREFIX,
    MAP_PREFIX,
    COMPASS_PREFIX,
    BOOL_KINDS,
    PREFIX_KIND,
    APPLIED_PREFIX,
    SMALL_KEY_MODEL,
    BOSS_KEY_MODEL,
    RING_DUNGEONS,
    BOSS_KEY_DUNGEONS,
    MAP_DUNGEONS,
    DUNGEON_FOLDER,
    FRENCH_DUNGEONS,
    ENGLISH_DUNGEONS,
    total_keys,
    ring_item,
    small_key_item,
    is_ring,
    item_folder,
    SHORT_FOLDER,
    FOLDER_OF_SHORT,
    ring_actor,
    boss_actor,
    map_actor,
    compass_actor,
    dungeon_item_actor,
    actor_kind,
    specific_actor,
    actor_folder,
    key_actor_item,
    is_key_actor,
    TRACKED_BOSS_KEYS,
)
from oot_rando.formats.evfl_tools import params_by_event, parse_flow
ACTION_GUIDE_FLOW = 'Event/EventFlow/ActionGuide.bfevfl.zs'
ACTION_GUIDE_ENTRY = 'ActionGuide'


DUNGEON_ITEM_TEXTS = {
    'fr': {'map': ('Carte : {n}', 'La carte du donjon « {n} ».', 'Vous avez obtenu la carte du donjon : {n} !',
                   'Ouvrez la carte pour voir ses salles.'),
           'compass': ('Boussole : {n}', 'La boussole du donjon « {n} ».',
                       'Vous avez obtenu la boussole du donjon : {n} !',
                       'La carte montre maintenant ses coffres et le boss.')},
    'en': {'map': ('Map: {n}', 'The map of the {n}.', 'You got the {n} map!', 'Open the map to see its rooms.'),
           'compass': ('Compass: {n}', 'The compass of the {n}.', 'You got the {n} compass!',
                       'The map now shows its chests and its boss.')},
}


def key_texts(actor, language):
    folder = actor_folder(actor)
    ring = actor.startswith(RING_PREFIX)
    kind = actor_kind(actor)
    if kind in ('map', 'compass'):
        french = language.endswith('fr')
        texts = DUNGEON_ITEM_TEXTS['fr' if french else 'en'][kind]
        name = (FRENCH_DUNGEONS if french else ENGLISH_DUNGEONS)[folder]
        return dict(zip(('Name', 'Caption', 'GetMessage', 'GetCaption'), (t.format(n=name) for t in texts)))
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
            values[f'DungeonInfo.{folder}.SmallKeyTotalNum'] = count
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


def key_specs(actors):
    specs = []
    for actor in sorted(actors):
        name = 'RandoKey_' + actor[len('Item_'):] + '.event.root'
        kind = actor_kind(actor)
        specs.append({'actor': actor, 'model': SMALL_KEY_MODEL if kind == 'ring' else BOOL_KINDS[kind][2],
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
            actor = dungeon_item_actor(item) or boss_actor(folder)
            kind = actor_kind(actor)
            records.append({'kind': kind, 'actor': actor, 'folder': folder,
                            'gamedata': f'DungeonInfo.{folder}.{BOOL_KINDS[kind][1]}'})
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


def got_flag(actor):
    """Saved Bool the pouch sets once ``actor`` is got (``soul_adapter.FLAG_PREFIX``)."""
    return 'IsGet.' + actor


def check_dungeon_data(gamedata_raw, records):
    """Every GameData name written by the hook exists (saved) in the game."""
    from oot_rando.formats.inspect_resources import Byml
    from oot_rando.patching.soul_adapter import murmur3
    data = Byml(gamedata_raw).root['Data']
    types = {'ring': 'Int', 'boss': 'Bool', 'map': 'Bool', 'compass': 'Bool'}
    for record in records:
        entries = {e['Hash']: e for e in data[types[record['kind']]]}
        names = [record['gamedata']] + ([total_keys(record['gamedata'])] if record['kind'] == 'ring' else [])
        for name in names:
            entry = entries.get(murmur3(name))
            if entry is None or entry.get('SaveFileIndex') != 0:
                raise ValueError('Dungeon data not found: ' + name)


def check_got_flags(gamedata_raw, records):
    """The hook's ``IsGet.<actor>`` tests are saved Bools of the seed's GameData."""
    from oot_rando.formats.inspect_resources import Byml
    from oot_rando.patching.soul_adapter import murmur3
    saved = {e['Hash'] for e in Byml(gamedata_raw).root['Data']['Bool'] if e.get('SaveFileIndex') == 0}
    for record in records:
        if murmur3(got_flag(record['actor'])) not in saved:
            raise ValueError('Get flag of a key item not saved: ' + got_flag(record['actor']))


def add_key_hook(raw, records):
    """Prepend the key checks to ``ActionGuide/ActionGuide``. Returns (bytes, report).

    Bool switches: case 0 = true (as the vanilla flows).
    """
    from evfl.actor import Actor
    from evfl.common import ActorIdentifier, StringHolder
    from evfl.container import Container
    from evfl.event import Event, ActionEvent, SwitchEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS
    flow = parse_flow(raw)
    chart = flow.flowchart
    expected = params_by_event(flow)
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

    # A named actor without its parameter container crashes the game (seen with
    # GameDataActor at the end of the intro): vanilla parameters.
    gamedata = system_actor('GameDataActor', GAMEDATA_ACTOR_PARAMS)
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
            # Keys found too (SmallKeyTotalNum), as the native key get credits them:
            # held keys alone did not show in the dungeon (15/11, Discord report).
            found = action(f'RandoKeyFound_{stem}', gamedata, add_int,
                           {'GameDataName': total_keys(record['gamedata']), 'Value': record['count'], 'Index': -1})
            found.data.nxt = make_index(mark)
            give = action(f'RandoKeyGive_{stem}', gamedata, add_int,
                          {'GameDataName': record['gamedata'], 'Value': record['count'], 'Index': -1})
            give.data.nxt = make_index(found)
            done = switch(f'RandoKeyDone_{stem}', gamedata, is_bool,
                          {'GameDataName': record['applied'], 'Index': -1}, following, give)
            first = switch(f'RandoKeyHeld_{stem}', gamedata, is_bool,
                           {'GameDataName': got_flag(record['actor']), 'Index': -1}, done, following)
        else:
            give = action(f'RandoKeyGive_{stem}', gamedata, set_bool,
                          {'GameDataName': record['gamedata'], 'Value': True, 'Index': -1})
            give.data.nxt = make_index(following)
            first = switch(f'RandoKeyHeld_{stem}', gamedata, is_bool,
                           {'GameDataName': got_flag(record['actor']), 'Index': -1}, give, following)
        report.append({'actor': record['actor'], 'start': first.name})
        following = first
    entry.main_event = make_index(following)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = parse_flow(result)
    if params_by_event(checked) != expected:
        raise ValueError('Dungeon keys changed other parameters.')
    start = {e.name: e for e in checked.flowchart.entry_points}[ACTION_GUIDE_ENTRY].main_event.v
    if records and start.name != f"RandoKeyHeld_{records[0]['actor'][len('Item_'):]}":
        raise ValueError('ActionGuide entry wrongly attached to the keys.')
    return result, list(reversed(report))


def dungeon_keys(rows, snapshot):
    """``[(dungeon, (found, total) or None, has boss key or None)]`` from a save snapshot."""
    ints, bools = (snapshot or {}).get('int', {}), (snapshot or {}).get('bool', {})
    result = []
    for row in rows or ():
        small = row.get('small')
        if small:
            found = max(int(ints.get(int(small['found']), 0) or 0), int(ints.get(int(small['held']), 0) or 0))
            if small['all'] or (small['ring'] and bools.get(int(small['ring']))):
                found = max(found, small['total'])
            small = (found, max(small['total'], found))
        boss = row.get('boss')
        if boss:
            boss = bool(boss['all'] or bools.get(int(boss['hash'])))
        result.append((row['dungeon'], small, boss))
    return result
