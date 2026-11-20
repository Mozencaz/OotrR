"""New-game values written as defaults of the GameData list.

A new game starts from the ``DefaultValue`` of every GameData entry
(``GameData/GameDataList.Product.110.byml.zs``). Changing the default of a saved
entry therefore sets a value from the very first frame of a new game, before any
event flow runs, without touching a flow. This is the base of the world openings
and story skips (a flag, a counter or a quest step that the game reads later).

Only entries that are safe to change are accepted:

* saved in the main save file (``SaveFileIndex`` 0), so the value survives a reload;
* reset only when a new game starts (``ResetTypeValue`` 8, the mask of 9,338 of the
  11,292 bools of the 1.1.1 list). Other masks also reset the entry at other times
  (bit 0: on map change, …): the game would undo the value, so they are refused
  unless the caller lists the mask in ``allow_reset``.

Supported kinds: ``Bool`` (Python ``bool``), ``Int`` (``int``) and ``Enum`` (the
value name as ``str``, stored as its murmur3 hash). Quest steps are saved enums
too, but their entry names are not known yet: move a quest with the native
``EventExecuteProgressChallengeStep`` action instead. Not validated in game.
"""
from oot_rando.formats import byml_codec
from oot_rando.patching.soul_adapter import murmur3

GAMEDATA = 'GameData/GameDataList.Product.110.byml.zs'
NEW_GAME_RESET = 8
INT_RANGE = (-2 ** 31, 2 ** 31 - 1)


def _kind(value):
    if type(value) is bool:
        return 'Bool'
    if type(value) is int:
        return 'Int'
    if type(value) is str:
        return 'Enum'
    raise ValueError(f'Unsupported default value type: {type(value).__name__}')


def _entries(data, kind):
    return {int(entry['Hash']): entry for entry in data.get(kind, ()) if 'Hash' in entry}


def _check(name, entry, kind, value, allow_reset):
    if entry is None:
        raise ValueError(f'No {kind} GameData entry named {name}')
    if entry.get('SaveFileIndex') != 0:
        raise ValueError(f'{name} is not saved: a new game default would be lost on reload')
    if entry.get('ResetTypeValue') not in allow_reset:
        raise ValueError(f'{name} is reset by the game (mask {entry.get("ResetTypeValue")}): '
                         'the default would be undone')
    if kind == 'Int' and not INT_RANGE[0] <= value <= INT_RANGE[1]:
        raise ValueError(f'{name}: {value} does not fit a 32-bit Int')
    if kind == 'Enum' and value not in entry.get('RawValues', ()):
        raise ValueError(f'{name} has no value {value}')


def check_defaults(gamedata_raw, values, allow_reset=(NEW_GAME_RESET,)):
    """Raise ValueError unless every value can be written as a new game default."""
    data = byml_codec.load(gamedata_raw)['root']['Data']
    tables = {}
    for name, value in values.items():
        kind = _kind(value)
        table = tables.setdefault(kind, _entries(data, kind))
        _check(name, table.get(murmur3(name)), kind, value, tuple(allow_reset))


def set_new_game_defaults(gamedata_raw, values, allow_reset=(NEW_GAME_RESET,)):
    """GameData list bytes where each ``values`` entry starts with the given value.

    ``values``: {GameData name: bool | int | enum value name}. Every name is checked
    before anything is written (all or nothing). Returns new bytes; the input is
    returned unchanged when ``values`` is empty.
    """
    if not values:
        return gamedata_raw
    document = byml_codec.load(gamedata_raw)
    data = document['root']['Data']
    tables, planned = {}, []
    for name, value in sorted(values.items()):
        kind = _kind(value)
        table = tables.setdefault(kind, _entries(data, kind))
        entry = table.get(murmur3(name))
        _check(name, entry, kind, value, tuple(allow_reset))
        planned.append((entry, kind, value))
    for entry, kind, value in planned:
        if kind == 'Enum':
            entry['DefaultValue'] = byml_codec.U32(murmur3(value))
        else:
            entry['DefaultValue'] = value
    return byml_codec.dump(document)


def read_defaults(gamedata_raw, names):
    """{name: default} as written in the list (enum defaults as value names)."""
    data = byml_codec.load(gamedata_raw)['root']['Data']
    result = {}
    for name in names:
        hashed = murmur3(name)
        for kind in ('Bool', 'Int', 'Enum'):
            entry = _entries(data, kind).get(hashed)
            if entry is None:
                continue
            value = entry['DefaultValue']
            if kind == 'Enum':
                value = next(raw for raw, h in zip(entry['RawValues'], entry['Values']) if int(h) == int(value))
            result[name] = value
            break
        else:
            raise ValueError('No GameData entry named ' + name)
    return result
