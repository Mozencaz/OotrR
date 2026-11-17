"""First-collection rewards for repeatable physical sources.

Generated pickups retain the real item's PouchActor. Their private event AINB
sets a saved check flag only after the native add-to-pouch action. The source
itself is left as in the game, but for its drop, so it breaks and respawns like
the vanilla one (on a scene change). Once the check is collected, the pickup it
drops deletes itself when it spawns: its own AI (a clone of the native
``DropItem`` one) checks the flag. Gameplay validation remains required.

Shop shelves holding a shuffled item (``Shop_Rando_*``) are bought once the same
way: each gets its own actor whose shop AI writes the check flag when the item is
bought, and reads that flag as its "sold out" state: the item at rest then
deletes itself. The map is unchanged (no Presence: some shelves, like the Kokiri
shop's, already have one).
"""
import copy
import hashlib
import math
import struct
import uuid

from oot_rando.formats import byml_codec
from oot_rando.formats.inspect_resources import sarc
from oot_rando.game.item_forms import (WORLD_CANONICAL, DROP_PREFIX, SHOP_PREFIX, build_pack, canonical_of,
                        is_derived, add_rsdb_rows, resolve_components)
from oot_rando.patching.soul_adapter import FLAG_PREFIX as SOUL_FLAG_PREFIX, murmur3

REPEATABLE = frozenset(('pots', 'bushes', 'rocks', 'crates', 'beehives'))
EVENT_PACK = 'Pack/AI.Global.Product.111.pack.zs'
EVENT_MEMBER = 'AI/PouchContent.event.root.ainb'
DROP_AI_MEMBER = 'AI/DropItem.root.ainb'
DROP_AI_INFO = '?AI/AIInfo/DropItem.engine__actor__AIInfo.bgyml'
LARGE_GET_TYPE = 1746592023
# Short get (the game's own for gold tokens, heart pieces and the gold rupee on the
# ground): no long held-up pose, but Link still shows the item.
MEDIUM_GET_TYPE = 1027255402
# Minor rewards keep their native pickup (no GetType: rupees, arrows, seeds, nuts,
# sticks, bombs, magic jars, hearts all have none), as on the ground. Forcing Medium
# on them still played a pose (Discord 15/11, 0.6.1). Only the bombchu packs are
# Large natively (key-item style): they take Medium.
MINOR_LARGE_PREFIXES = ('Item_BombchuBundle_',)
MINOR_PREFIXES = ('TBox_Rupee_', 'TBox_ArrowBundle_', 'TBox_DekuNutBundle', 'TBox_DekuSeedBundle',
                  'Item_BombBundle_', 'Item_DekuStickBundle_', 'Item_BombchuBundle_', 'Tbox_MagicJar_',
                  'Item_ScrubBusinessSeed')
MINOR_ACTORS = frozenset(('Obj_Heart',))   # recovery heart (not a piece nor a container)
SHOP_ONCE_PREFIX = 'Shop_RandoOnce_'
SHOP_AI_MEMBER = 'AI/Shop_Item_Base.root.ainb'


def is_minor_reward(canonical):
    """Rupees, ammunition and recovery hearts: picked up with the short get."""
    return canonical in MINOR_ACTORS or canonical.startswith(MINOR_PREFIXES)


def get_type(canonical):
    """GetType given to a first-collection pickup (None: the item's native one)."""
    if is_minor_reward(canonical):
        return MEDIUM_GET_TYPE if canonical.startswith(MINOR_LARGE_PREFIXES) else None
    return LARGE_GET_TYPE


def pickup_pouch_settings(canonical):
    """PouchContentParam overrides of a first-collection pickup dropping ``canonical``.

    A key reward plays its get event every time (the check's own message). A minor
    one keeps the native pickup behaviour: the get window only the first time this
    kind of item is ever got (a green rupee from every pot showed "You got a Green
    Rupee!", Discord 17/11), the short pick-up display after. The derived drop
    inherits PlayGetEventManyTimes from the world pickups (item_forms.WORLD_POUCH_FLAGS):
    it is turned off explicitly. Whether the check flag is still written on the short
    pick-up (its event AINB) is not validated in game: if not, the pot keeps dropping
    that minor item.
    """
    settings = {'PlayGetEventManyTimes': not is_minor_reward(canonical), 'IsAutoSaveAfterPlayGet': True}
    if get_type(canonical) is not None:
        settings['GetType'] = byml_codec.U32(get_type(canonical))
    return settings


def _guid(text):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'oot-randomizer/' + text))


def instrument_pickup_event(raw, flag, filename, canonical=None, also_set=()):
    """Clone an event AI and sequence a GameData write AFTER native pouch push.

    All commands and original nodes are retained. No setter is attached to actor
    death, jar destruction, event entry, animation completion or item possession.
    ``also_set`` lists further saved Bool flags written after ``flag`` (a soul
    picked from a pot also sets its ``IsGet.Item_Soul_*`` flag).
    """
    try:
        import ainb
    except ImportError as error:
        raise ValueError('Install ainb==0.2.17 for first-collection rewards.') from error
    script = ainb.AINB.from_binary(raw)
    original = script.as_dict()
    document = copy.deepcopy(original)
    if document['Version'] != 0x408:
        raise ValueError('Unexpected AINB version for first collection.')
    nodes = document['Nodes']
    pushes = [n for n in nodes if n['Name'] == 'OneShotPouchContentPushToPouchOwnInEvent']
    if len(pushes) != 1:
        raise ValueError('Native pickup action ambiguous or missing.')
    push = pushes[0]['Node Index']
    parents = [(n, plug) for n in nodes for plug in n.get('Plugs', {}).get('Child', [])
               if plug['Node Index'] == push]
    if not parents:
        raise ValueError('Pickup action without an executable parent.')
    # A native sequential template from this very graph preserves its policies.
    sequential = next((copy.deepcopy(n) for n in nodes if n['Node Type'] == 'Element_Sequential'), None)
    if sequential is None:
        raise ValueError('Sequential template missing from the get graph.')
    sequence_index, setter_index = len(nodes), len(nodes) + 1
    query_index, selector_index = len(nodes) + 2, len(nodes) + 3
    for _, plug in parents:
        plug['Node Index'] = selector_index if canonical else sequence_index
    sequential.update({'Node Index': sequence_index, 'GUID': _guid(flag + '/sequence'),
                       'Queries': [], 'Attachments': [], 'Flags': [],
                       'Parameters': {'Inputs': {}, 'Outputs': {}}, 'XLink Actions': [],
                       'Plugs': {'Child': [{'Node Index': push, 'Name': ''},
                                           {'Node Index': setter_index, 'Name': ''}]}})
    for prop in sequential.get('Properties', {}).get('Bool', []):
        if prop['Name'] == 'IsLoop':
            prop['Default Value'] = False
    def default(name, value):
        return {'Name': name, 'Default Value': value, 'Node Index': -1,
                'Output Index': 0, 'Flags': ['Uses Default']}
    setter = {'Node Type': 'UserDefined', 'Node Index': setter_index,
              'Name': 'OneShotSetNonStructGameDataBool', 'GUID': _guid(flag + '/setter'),
              'Flags': [], 'Queries': [], 'Attachments': [],
              'Properties': {'Bool': [{'Name': 'ExecuteEveryFrame', 'Default Value': False, 'Flags': []}]},
              'Parameters': {'Inputs': {'Int': [default('GameDataIndex', -1)],
                                        'Bool': [default('Value', True)],
                                        'String': [default('GameDataFullName', flag)]}, 'Outputs': {}},
              'XLink Actions': [], 'Plugs': {}}
    document['Filename'] = filename
    nodes.extend([sequential, setter])
    if canonical:
        query = copy.deepcopy(next(n for n in nodes[:sequence_index] if n['Name'] == 'QueryPouchMgrIsEnablePushToPouch'))
        query.update({'Node Index': query_index, 'GUID': _guid(flag + '/can-add'), 'Queries': [], 'Plugs': {}})
        query['Parameters']['Inputs'] = {'String': [default('ActorName', canonical)]}
        selector = copy.deepcopy(next(n for n in nodes[:sequence_index] if n['Node Type'] == 'Element_BoolSelector'))
        noop = next(n['Node Index'] for n in nodes[:sequence_index] if n['Name'] == 'OneshotDoNothing')
        selector.update({'Node Index': selector_index, 'GUID': _guid(flag + '/guard'), 'Queries': [query_index],
                         'Attachments': [], 'Flags': [], 'XLink Actions': []})
        selector['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Input', 'Default Value': False,
                                 'Node Index': query_index, 'Output Index': 0, 'Flags': []}]}, 'Outputs': {}}
        selector['Plugs'] = {'Generic': [{'Node Index': query_index, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
                             'Child': [{'Node Index': sequence_index, 'Name': 'True'}, {'Node Index': noop, 'Name': 'False'}]}
        nodes.extend([query, selector])
    # A drop may already exist when another copy of the same location is
    # collected. Recheck the saved per-check flag at native pickup execution,
    # rather than relying only on the source actor's Presence condition.
    flag_query_index, flag_selector_index = len(nodes), len(nodes) + 1
    flag_query = copy.deepcopy(next(n for n in nodes[:sequence_index]
                                   if n['Name'] == 'QueryGetNonStructGameDataBool'))
    flag_query.update({'Node Index': flag_query_index, 'GUID': _guid(flag + '/already-collected'),
                       'Queries': [], 'Plugs': {}})
    flag_query['Parameters']['Inputs']['String'] = [default('GameDataFullName', flag)]
    flag_selector = copy.deepcopy(next(n for n in nodes[:sequence_index]
                                      if n['Node Type'] == 'Element_BoolSelector'))
    noop = next(n['Node Index'] for n in nodes[:sequence_index] if n['Name'] == 'OneshotDoNothing')
    eligible = selector_index if canonical else sequence_index
    flag_selector.update({'Node Index': flag_selector_index, 'GUID': _guid(flag + '/first-only'),
                          'Queries': [flag_query_index], 'Attachments': [], 'Flags': [], 'XLink Actions': []})
    flag_selector['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Input', 'Default Value': False,
                                      'Node Index': flag_query_index, 'Output Index': 0, 'Flags': []}]}, 'Outputs': {}}
    flag_selector['Plugs'] = {
        'Generic': [{'Node Index': flag_query_index, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
        'Child': [{'Node Index': noop, 'Name': 'True'}, {'Node Index': eligible, 'Name': 'False'}]}
    for _, plug in parents:
        plug['Node Index'] = flag_selector_index
    nodes.extend([flag_query, flag_selector])
    for extra in also_set:
        extra_setter = copy.deepcopy(setter)
        extra_setter.update({'Node Index': len(nodes), 'GUID': _guid(flag + '/also/' + extra)})
        extra_setter['Parameters']['Inputs']['String'] = [default('GameDataFullName', extra)]
        sequential['Plugs']['Child'].append({'Node Index': len(nodes), 'Name': ''})
        nodes.append(extra_setter)
    result = ainb.AINB.from_dict(document).to_binary()
    checked = ainb.AINB.from_binary(result).as_dict()
    if checked != document:
        raise ValueError('The modified get graph does not read back identically.')
    # Strong invariant: every original command is untouched and additions occur
    # only at child references to the native pouch-push action.
    if checked['Commands'] != original['Commands']:
        raise ValueError('Get commands changed unexpectedly.')
    return result


def _default(name, value):
    return {'Name': name, 'Default Value': value, 'Node Index': -1, 'Output Index': 0, 'Flags': ['Uses Default']}


def _retarget(value, old, new):
    """Replace every ``'Node Index': old`` reference inside a node description."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'Node Index' and item == old:
                value[key] = new
            else:
                _retarget(item, old, new)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if item == old and isinstance(item, int) and not isinstance(item, bool):
                value[index] = new
            else:
                _retarget(item, old, new)


def _refers(value, index):
    """Whether a node description holds a ``'Node Index': index`` reference."""
    if isinstance(value, dict):
        return value.get('Node Index') == index or any(_refers(item, index) for item in value.values())
    if isinstance(value, list):
        return any(_refers(item, index) for item in value)
    return False


def as_command(node):
    """``ASCommand`` of an ``ExecuteASPlay`` node (a property or a default input), or None."""
    values = list(node.get('Properties', {}).get('String', []))
    values += node.get('Parameters', {}).get('Inputs', {}).get('String', [])
    return next((p.get('Default Value') for p in values if p['Name'] == 'ASCommand'), None)


def instrument_shop_ai(raw, flag, filename):
    """Clone the shop item AI so that a shelf is bought once.

    * the saved ``flag`` is set by a node added to the two branches a bought item
      goes through: the get demo (``ExecuteASPlay`` ``Rotate_GetDemo``, the item
      held up by Link: checked in game, bought items take this one) and
      ``ExecuteShopItemPutInPouch``;
    * every reader of the native ``QueryShopItemIsSoldOut`` (model hidden, sold
      out message to the linked ``Shop_Board_SoldOut``) reads ``flag`` instead;
    * once bought, the hidden branch asks the native sold out state: sold out
      (StockNum 1, see ``limit_shop_stock``), the shelf is only hidden and stays
      selectable; not sold out (stock restored on reload), it deletes itself,
      since the shop still sells a hidden shelf, not an absent one.
    """
    try:
        import ainb
    except ImportError as error:
        raise ValueError('Install ainb==0.2.17 for single purchases in shops.') from error
    script = ainb.AINB.from_binary(raw)
    original = script.as_dict()

    def build(document):
        # ainb 0.2.17 drops this graph's blackboard in as_dict(): restore it (no
        # node refers to it by index), else the written file is unreadable.
        result = ainb.AINB.from_dict(document)
        result.blackboard = script.blackboard
        return result.to_binary()
    if build(original) != script.to_binary():
        raise ValueError('The shop item AI cannot be rewritten faithfully.')
    document = copy.deepcopy(original)
    if document['Version'] != 0x408:
        raise ValueError('Unexpected AINB version for the shop item AI.')
    nodes = document['Nodes']

    def only(name):
        found = [n for n in nodes if n['Name'] == name]
        if len(found) != 1:
            raise ValueError(f'Shop item AI: {name} ambiguous or missing.')
        return found[0]
    put = only('ExecuteShopItemPutInPouch')['Node Index']
    sold_out = only('QueryShopItemIsSoldOut')['Node Index']
    template = only('QueryGetNonStructGameDataBool')
    def parent_of(index):
        found = [n for n in nodes if any(p['Node Index'] == index for p in n.get('Plugs', {}).get('Child', []))]
        if len(found) != 1 or found[0]['Node Type'] != 'Element_Simultaneous':
            raise ValueError('Shop item AI: purchase step without a simultaneous parent.')
        return found[0]

    demo = [n['Node Index'] for n in nodes if n['Name'] == 'ExecuteASPlay' and as_command(n) == 'Rotate_GetDemo']
    if len(demo) != 1:
        raise ValueError('Shop item AI: get demo ambiguous or missing.')
    parents = [parent_of(demo[0]), parent_of(put)]
    setter_index, query_index = len(nodes), len(nodes) + 1
    setter = {'Node Type': 'UserDefined', 'Node Index': setter_index,
              'Name': 'OneShotSetNonStructGameDataBool', 'GUID': _guid(flag + '/bought'),
              'Flags': [], 'Queries': [], 'Attachments': [],
              'Properties': {'Bool': [{'Name': 'ExecuteEveryFrame', 'Default Value': False, 'Flags': []}]},
              'Parameters': {'Inputs': {'Int': [_default('GameDataIndex', -1)],
                                        'Bool': [_default('Value', True)],
                                        'String': [_default('GameDataFullName', flag)]}, 'Outputs': {}},
              'XLink Actions': [], 'Plugs': {}}
    readers = [n for n in nodes if n['Node Index'] != sold_out
               and (sold_out in n.get('Queries', []) or _refers(n.get('Parameters'), sold_out))]
    if not readers:
        raise ValueError('Shop item AI: sold out state not read.')
    for node in readers:
        _retarget(node.get('Queries', []), sold_out, query_index)
        _retarget(node.get('Parameters', {}), sold_out, query_index)
        _retarget(node.get('Plugs', {}), sold_out, query_index)
    query = copy.deepcopy(template)
    query.update({'Node Index': query_index, 'GUID': _guid(flag + '/sold-out'), 'Queries': [], 'Plugs': {}})
    query['Parameters']['Inputs']['String'] = [_default('GameDataFullName', flag)]
    for parent in parents:
        parent['Plugs']['Child'].append({'Node Index': setter_index, 'Name': ''})
    # The shop sells a shelf as long as its actor exists, whatever the sold out
    # message says (checked in game): once bought, the item at rest deletes itself.
    # Its visibility selector is the "sold out" one; it no longer runs while the item
    # is put in the pouch, so the deletion never cuts that short.
    selectors = [n for n in readers if n['Node Type'] == 'Element_BoolSelector']
    if len(selectors) != 1:
        raise ValueError('Shop item AI: sold out visibility ambiguous or missing.')
    selector = selectors[0]
    branch = next((p for p in selector['Plugs'].get('Child', []) if p['Name'] == 'True'), None)
    if branch is None or nodes[branch['Node Index']]['Name'] != 'OneShotGameModelControllerSetVisible':
        raise ValueError('Shop item AI: sold out branch not recognised.')
    put_parent = parents[1]
    put_parent['Plugs']['Child'] = [p for p in put_parent['Plugs']['Child'] if p['Node Index'] != selector['Node Index']]
    delete_index, native_index = len(nodes) + 2, len(nodes) + 3
    delete = {'Node Type': 'UserDefined', 'Node Index': delete_index, 'Name': 'OneShotGenericDeleteThisActor',
              'GUID': _guid(flag + '/delete'), 'Flags': [], 'Queries': [], 'Attachments': [],
              'Properties': {'Bool': [{'Name': 'ExecuteEveryFrame', 'Default Value': False, 'Flags': []},
                                      {'Name': 'IsFade', 'Default Value': False, 'Flags': []}]},
              'Parameters': {'Inputs': {}, 'Outputs': {}}, 'XLink Actions': [], 'Plugs': {}}
    # Bought: while the shop's own stock (StockNum 1) says sold out, the shelf only
    # hides its model and stays selectable (the native sold out state, the shop
    # refuses a second sale). Only if that stock came back (not saved) is the
    # shelf deleted, so that a hidden shelf is never sold again.
    native = copy.deepcopy(selector)
    native.update({'Node Index': native_index, 'GUID': _guid(flag + '/native-sold-out'), 'Queries': [sold_out],
                   'Attachments': [], 'Flags': [], 'XLink Actions': []})
    native['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Input', 'Default Value': False, 'Node Index': sold_out,
                                                 'Output Index': 0, 'Flags': []}]}, 'Outputs': {}}
    native['Plugs'] = {'Generic': [{'Node Index': sold_out, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
                       'Child': [{'Node Index': branch['Node Index'], 'Name': 'True'},
                                 {'Node Index': delete_index, 'Name': 'False'}]}
    branch['Node Index'] = native_index
    nodes.extend([setter, query, delete, native])
    document['Filename'] = filename
    binary = build(document)
    result = ainb.AINB.from_binary(binary).as_dict()
    if result != document:
        raise ValueError('The modified shop item AI does not read back identically.')
    if result['Commands'] != original['Commands']:
        raise ValueError('Shop item AI commands changed unexpectedly.')
    return binary


def instrument_drop_ai(raw, flag, filename, event_raw):
    """Clone the native drop AI so that a pickup spawned after its check deletes itself.

    The start-up sequence of the root (one frame of nothing, then the rotation AS)
    first asks the saved ``flag``: set, the pickup deletes itself, before it can be
    touched; not set, nothing changes. The query only outputs on entering, and that
    sequence runs once, at spawn: the first pickup is never deleted while its own
    get event writes the flag. The query and deletion are copies of the native nodes
    of the get event graph ``event_raw``.
    """
    try:
        import ainb
    except ImportError as error:
        raise ValueError('Install ainb==0.2.17 for first-collection rewards.') from error
    script = ainb.AINB.from_binary(raw)
    original = script.as_dict()

    def build(document):
        # As for the shop AI, the blackboard must be restored after as_dict().
        result = ainb.AINB.from_dict(document)
        result.blackboard = script.blackboard
        return result.to_binary()
    if build(original) != script.to_binary():
        raise ValueError('The drop AI cannot be rewritten faithfully.')
    document = copy.deepcopy(original)
    if document['Version'] != 0x408:
        raise ValueError('Unexpected AINB version for the drop AI.')
    nodes = document['Nodes']
    roots = [c['Root Node Index'] for c in document['Commands'] if c['Name'] == 'Root']
    if len(roots) != 1 or nodes[roots[0]]['Node Type'] != 'Element_Simultaneous':
        raise ValueError('Drop AI: root not recognised.')
    starts = [nodes[p['Node Index']] for p in nodes[roots[0]]['Plugs']['Child']
              if nodes[p['Node Index']]['Node Type'] == 'Element_Sequential']
    if len(starts) != 1 or any(prop['Name'] == 'IsLoop' and prop['Default Value']
                               for prop in starts[0]['Properties'].get('Bool', [])):
        raise ValueError('Drop AI: start-up sequence ambiguous or missing.')
    templates = ainb.AINB.from_binary(event_raw).as_dict()['Nodes']

    def native(source, name):
        found = [n for n in source if n['Name'] == name]
        if len(found) != 1:
            raise ValueError(f'Drop AI: {name} ambiguous or missing.')
        return copy.deepcopy(found[0])
    query_index, delete_index, noop_index, selector_index = range(len(nodes), len(nodes) + 4)
    query = native(templates, 'QueryGetNonStructGameDataBool')
    query.update({'Node Index': query_index, 'GUID': _guid(flag + '/drop-collected'), 'Queries': [], 'Plugs': {}})
    query['Parameters']['Inputs']['String'] = [_default('GameDataFullName', flag)]
    for prop in query['Properties']['Bool']:
        if prop['Name'] == 'OutputOnlyOnEnter':
            prop['Default Value'] = True
    delete = native(templates, 'OneShotGenericDeleteThisActor')
    delete.update({'Node Index': delete_index, 'GUID': _guid(flag + '/drop-delete')})
    for prop in delete['Properties']['Bool']:
        if prop['Name'] == 'IsFade':
            prop['Default Value'] = False
    noop = copy.deepcopy(next(n for n in nodes if n['Name'] == 'OneshotDoNothing'))
    noop.update({'Node Index': noop_index, 'GUID': _guid(flag + '/drop-keep')})
    selector = copy.deepcopy(next(n for n in nodes if n['Node Type'] == 'Element_BoolSelector'))
    selector.update({'Node Index': selector_index, 'GUID': _guid(flag + '/drop-once'), 'Queries': [query_index],
                     'Attachments': [], 'Flags': [], 'XLink Actions': []})
    selector['Parameters'] = {'Inputs': {'Bool': [{'Name': 'Input', 'Default Value': False, 'Node Index': query_index,
                                                   'Output Index': 0, 'Flags': []}]}, 'Outputs': {}}
    selector['Plugs'] = {'Generic': [{'Node Index': query_index, 'Name': 'Input', 'Unknown 1': 0, 'Unknown 2': 0}],
                         'Child': [{'Node Index': delete_index, 'Name': 'True'},
                                   {'Node Index': noop_index, 'Name': 'False'}]}
    starts[0]['Plugs']['Child'].insert(0, {'Node Index': selector_index, 'Name': ''})
    nodes.extend([query, delete, noop, selector])
    document['Filename'] = filename
    binary = build(document)
    result = ainb.AINB.from_binary(binary).as_dict()
    if result != document:
        raise ValueError('The modified drop AI does not read back identically.')
    if result['Commands'] != original['Commands']:
        raise ValueError('Drop AI commands changed unexpectedly.')
    return binary


def prepare_repeatables(plan, maps):
    """Rename selected repeatable world rewards; return generation descriptors.

    Must run BEFORE the normal placement map patches are composed. Original
    placements keep their AP item/spoiler actor; only the physical pickup changes.
    """
    records = []
    for placement in plan['placements']:
        previous = placement['after']
        # A shelf holding a shuffled item (not a native shop refill) is bought once.
        shop = placement.get('source') == 'shop' and previous.startswith(SHOP_PREFIX)
        if placement.get('source') not in REPEATABLE and not shop:
            continue
        canonical = canonical_of(previous) if is_derived(previous) else WORLD_CANONICAL.get(previous)
        if canonical is None:
            raise ValueError('Repeatable reward without a known native form: ' + previous)
        key = hashlib.sha256(placement['id'].encode('utf-8')).hexdigest()[:16]
        actor = (SHOP_ONCE_PREFIX if shop else 'Obj_RandoOnce_') + key
        flag = 'Rando.Check.' + key
        variants = []
        for patch in ([] if shop else placement['patches']):
            if 'event' in patch or tuple(patch['path'][:1]) != ('Actors',):
                raise ValueError('Repeatable source without a proven physical actor.')
            resource, index = patch['resource'], patch['path'][1]
            original = maps[resource]['root']['Actors'][index]
            # Sources under a condition of their own stay vanilla, but for a native
            # one-shot jar, removed by its own persistent IsCrushed condition.
            presence = original.get('Presence')
            native_once = bool(presence and presence.get('IsNegation') is True
                               and presence.get('FlagName', '').endswith('_IsCrushed'))
            if presence and not native_once:
                raise ValueError('Conditional presence cannot be combined for ' + placement['id'])
            variants.append({'resource': resource, 'index': index, 'native_once': native_once})
        record = {'id': placement['id'], 'actor': actor, 'canonical': canonical, 'kind': 'shop' if shop else 'pickup',
                  'original_reward_actor': previous, 'flag': flag, 'flag_hash': murmur3(flag),
                  'event_filename': 'RandoOnce_' + key + '.event.root', 'variants': variants}
        if shop:
            record['shelves'] = [{'resource': patch['resource'], 'index': patch['path'][1], 'shelf': placement['before'],
                                  'board_hash': int.from_bytes(hashlib.sha256(
                                      f"{placement['id']}/sold-out/{patch['resource']}/{patch['path'][1]}".encode()).digest()[:8],
                                      'little')}
                                 for patch in placement['patches']
                                 if 'event' not in patch and tuple(patch['path'][:1]) == ('Actors',)]
        placement['after'] = actor
        placement['reward_actor'] = previous
        placement['first_collect_flag'] = flag
        records.append(record)
        match = plan.get('matches', {}).get(placement['id'])
        if match is not None:
            match['first_collect_flag'] = flag
    return records


def build_repeatable_packs(records, read_pack, read_raw, tables):
    """Build unique pickups and event graphs, and append their RSDB rows.

    ``read_pack`` sees normal/generated soul packs. ``read_raw`` returns raw
    game resources. ``tables`` are current RSDB row arrays, edited in place.
    Returns new-resource mapping of path -> (raw, compression_template_path).
    Saved Bool flags must be added separately by the caller (8 bytes each).
    """
    if not records:
        return {}
    event = None
    new = {}
    for record in records:
        if record.get('kind') == 'shop':
            standard = record['original_reward_actor']
            raw, template = build_pack(standard, read_pack, byml_codec)
            files = sarc(raw)
            document = byml_codec.load(files.pop(f'Actor/{standard}.engine__actor__ActorParam.bgyml'))
            if SHOP_AI_MEMBER not in files:
                raise ValueError('Shop item AI missing from the shop model.')
            root = record['actor'] + '.root'
            ai_info = f'AI/AIInfo/{record["actor"]}.engine__actor__AIInfo.bgyml'
            files['AI/' + root + '.ainb'] = instrument_shop_ai(files[SHOP_AI_MEMBER], record['flag'], root)
            files[ai_info] = byml_codec.dump({'endian': '<', 'version': 7,
                                              'root': {'RootAIRef': 'Work/AI/Root/' + root + '.ain'}})
            document['root']['Components']['AIInfoRef'] = '?' + ai_info
            files[f'Actor/{record["actor"]}.engine__actor__ActorParam.bgyml'] = byml_codec.dump(document)
            new['Pack/Actor/' + record['actor'] + '.pack.zs'] = (byml_codec.build_sarc(files), template)
            _alias_rows(tables, standard, record['actor'])
            continue
        if event is None:
            global_ai = sarc(read_raw(EVENT_PACK))
            event, drop_ai = global_ai[EVENT_MEMBER], global_ai[DROP_AI_MEMBER]
        # Dropped by its source: a falling pickup, not the standing token.
        standard = DROP_PREFIX + record['canonical']
        raw, template = build_pack(standard, read_pack, byml_codec)
        files = sarc(raw)
        old_path = f'Actor/{standard}.engine__actor__ActorParam.bgyml'
        document = byml_codec.load(files.pop(old_path))
        components = document['root']['Components']
        pouch_path = components['PouchContentRef'][1:]
        pouch = byml_codec.load(files[pouch_path])
        pouch['root'].update(pickup_pouch_settings(record['canonical']))
        # The PouchActor remains the canonical reward: no unique inventory item
        # or duplicate bundle is introduced just to track a check.
        files[pouch_path] = byml_codec.dump(pouch)
        event_name = record['event_filename']
        event_member = 'AI/' + event_name + '.ainb'
        event_param = f'Component/EventPerformerParam/{record["actor"]}.engine__component__EventPerformerParam.bgyml'
        files[event_param] = byml_codec.dump({'endian': '<', 'version': 7, 'root': {
            '$parent': 'Work/Component/EventPerformerParam/PouchContent_PickUpItem.engine__component__EventPerformerParam.gyml',
            'AlwaysEventMember': True, 'UseEventUniqueAin': True,
            'EventUniqueAin': 'Work/AI/Root/Event/' + event_name + '.ain'}})
        components['EventPerformerRef'] = '?' + event_param
        also = (SOUL_FLAG_PREFIX + record['canonical'],) if record['canonical'].startswith('Item_Soul_') else ()
        files[event_member] = instrument_pickup_event(event, record['flag'], event_name, record['canonical'], also)
        # A respawned source drops nothing more once the check is collected.
        behaviour = resolve_components({**files, old_path: byml_codec.dump(document)}, standard, byml_codec)
        if behaviour.get('AIInfoRef') != DROP_AI_INFO:
            raise ValueError('First-collection pickup without the native drop AI: ' + record['actor'])
        root = record['actor'] + '.root'
        ai_info = f'AI/AIInfo/{record["actor"]}.engine__actor__AIInfo.bgyml'
        files['AI/' + root + '.ainb'] = instrument_drop_ai(drop_ai, record['flag'], root, event)
        files[ai_info] = byml_codec.dump({'endian': '<', 'version': 7,
                                          'root': {'RootAIRef': 'Work/AI/Root/' + root + '.ain'}})
        components['AIInfoRef'] = '?' + ai_info
        files[f'Actor/{record["actor"]}.engine__actor__ActorParam.bgyml'] = byml_codec.dump(document)
        new['Pack/Actor/' + record['actor'] + '.pack.zs'] = (byml_codec.build_sarc(files), template)
        _alias_rows(tables, standard, record['actor'])
    return new


def _alias_rows(tables, standard, actor):
    """RSDB rows of ``actor``: those of the derived reward ``standard``, renamed."""
    # Reuse the existing derived-row builder under a temporary name, then
    # rename only those freshly appended rows. Their reward metadata stays.
    existing = {name: {row['__RowId'] for row in rows} for name, rows in tables.items()}
    if any(standard in ids for ids in existing.values()):
        # A standard derived reward might already be needed by another
        # location. Build rows in an isolated copy and copy only the alias.
        scratch = {name: [copy.deepcopy(row) for row in rows if row['__RowId'] != standard]
                   for name, rows in tables.items()}
        add_rsdb_rows(scratch, [standard])
        for name, rows in scratch.items():
            row = copy.deepcopy(next(row for row in rows if row['__RowId'] == standard))
            row['__RowId'] = actor
            tables[name].append(row)
    else:
        add_rsdb_rows(tables, [standard])
        for rows in tables.values():
            row = next(row for row in rows if row['__RowId'] == standard)
            row['__RowId'] = actor
    for rows in tables.values():
        rows.sort(key=lambda row: row['__RowId'])


SOLD_OUT_BOARD = 'Shop_Board_SoldOut'
BOARD_BACK = 0.25   # vanilla sold-out boards sit about this far behind their shelf


def add_sold_out_board(actors, index, ident):
    """Put a native ``Shop_Board_SoldOut`` behind shelf ``actors[index]``, linked to it.

    As in the Kokiri shop before the Deku Tree: the shelf's AI tells the board
    linked by ``Reference`` whether it is sold out (board shown or hidden).
    """
    shelf = actors[index]
    boards = {int(actor['Hash']) for actor in actors if actor.get('Gyaml') == SOLD_OUT_BOARD}
    if any(link.get('Name') == 'Reference' and int(link.get('Dst', 0)) in boards for link in shelf.get('Links', [])):
        return None   # a native one already (Kokiri shop before the Deku Tree)
    used = {int(actor['Hash']) for actor in actors if 'Hash' in actor}
    if ident in used:
        raise ValueError('Sold out board hash collision.')
    rotate = list(shelf.get('Rotate', [0.0, 0.0, 0.0]))
    x, y, z = shelf['Translate']
    yaw = rotate[1]
    def f32(value):   # as stored in the map, so that a replay compares equal
        return struct.unpack('<f', struct.pack('<f', value))[0]
    board = {'Gyaml': SOLD_OUT_BOARD, 'Hash': byml_codec.U64(ident),
             'Translate': [f32(x - math.sin(yaw) * BOARD_BACK), y, f32(z - math.cos(yaw) * BOARD_BACK)]}
    if 'Rotate' in shelf:
        board['Rotate'] = rotate
    if 'SRTHash' in shelf:
        board['SRTHash'] = shelf['SRTHash']
    if 'Presence' in shelf:   # present with its shelf (Kokiri full or short stock)
        board['Presence'] = copy.deepcopy(shelf['Presence'])
    shelf.setdefault('Links', []).append({'Dst': byml_codec.U64(ident), 'Gyaml': 'Reference', 'Name': 'Reference',
                                          'Src': shelf['Hash']})
    actors.append(board)
    return board


def shop_stock_edits(records, maps):
    """{shopkeeper actor: {ShopItemIndex: vanilla shelf actor}} of the shuffled shelves.

    The shopkeeper is the actor whose ``ForSale`` link reaches the shelf.
    """
    edits = {}
    for record in records:
        for shelf in record.get('shelves', []):
            actors = maps[shelf['resource']]['root']['Actors']
            target = actors[shelf['index']]
            sellers = {actor['Gyaml'] for actor in actors for link in actor.get('Links', [])
                       if link.get('Name') == 'ForSale' and link.get('Dst') == target['Hash']}
            if not sellers:
                raise ValueError('Shop shelf without a shopkeeper: ' + record['id'])
            slot = (target.get('Dynamic') or {}).get('ShopItemIndex', 0)
            for seller in sellers:
                old = edits.setdefault(seller, {}).setdefault(slot, shelf['shelf'])
                if old != shelf['shelf']:
                    raise ValueError(f'Two shelves share slot {slot} of {seller}.')
    return edits


def limit_shop_stock(pack_raw, slots):
    """Shopkeeper pack whose ShopParam goods at ``slots`` are sold once (StockNum 1).

    ``slots`` maps ShopItemIndex -> vanilla shelf actor; a good is only changed
    if its Actor is that shelf. Returns (new SARC bytes, changed slots).
    """
    files = dict(sarc(pack_raw))
    changed = set()
    for name in sorted(files):
        if not (name.startswith('Component/ShopParam/') and name.endswith('.bgyml')):
            continue
        document = byml_codec.load(files[name])
        goods = document['root'].get('GoodsList', [])
        touched = False
        for slot, shelf in slots.items():
            if slot < len(goods) and goods[slot].get('Actor', '').endswith(
                    '/' + shelf + '.engine__actor__ActorParam.gyml'):
                goods[slot]['StockNum'] = 1
                changed.add(slot)
                touched = True
        if touched:
            files[name] = byml_codec.dump(document)
    missing = set(slots) - changed
    if missing:
        raise ValueError(f'Shop goods not found for slots {sorted(missing)}.')
    return byml_codec.build_sarc(files), sorted(changed)


def patch_repeatable_sources(records, maps, raw_maps):
    """Add the sold out boards of shuffled shelves. Returns the changed maps.

    Shuffled pots, rocks and other sources keep their map entry as it is, but for
    their drop: no Presence and no vanilla copy. The game remembers a broken source
    by its hash (its Bool64bitKey) until the scene changes; a copy under another
    hash, or a source under a Presence condition, came back while the area stayed loaded.
    """
    documents = {}
    for record in records:
        for shelf in record.get('shelves', []):
            resource = shelf['resource']
            if resource not in documents:
                documents[resource] = byml_codec.load(raw_maps.get(resource, maps[resource]['raw']))
            add_sold_out_board(documents[resource]['root']['Actors'], shelf['index'], shelf['board_hash'])
    for resource, document in documents.items():
        raw_maps[resource] = byml_codec.dump(document)
    return sorted(documents)



def register_repeatable_flags(raw, records):
    """Add the saved collection flag of each record (an 8-byte typed Bool).

    Returns (raw_GameData, summary). No names or rewards are stored in saves.
    """
    if not records:
        return raw, {'bools': [], 'saved_bytes_added': 0}
    document = byml_codec.load(raw)
    data, meta = document['root']['Data'], document['root']['MetaData']
    previous_saved_size = meta['AllDataSaveSize']
    known = {int(e['Hash']) for entries in data.values() for e in entries if 'Hash' in e}
    bool_template = next((e for e in data['Bool'] if e.get('SaveFileIndex') == 0
                          and e.get('ResetTypeValue') == 8 and e.get('DefaultValue') is False), None)
    if bool_template is None:
        raise ValueError('Saved collection flag template missing.')
    added_bool = []
    for record in records:
        value = int(record['flag_hash'])
        if value != murmur3(record['flag']) or value in known:
            raise ValueError('Collection flag collision: ' + record['flag'])
        entry = copy.deepcopy(bool_template)
        entry['Hash'] = byml_codec.U32(value)
        data['Bool'].append(entry)
        known.add(value)
        index = entry['SaveFileIndex']
        meta['SaveDataSize'][index] += 8
        meta['SaveDataOffsetPos'][index] += 8
        meta['AllDataSaveSize'] += 8
        meta['AllDataSaveOffset'] += 8
        added_bool.append(value)
    return byml_codec.dump(document), {'bools': added_bool,
                                       'saved_bytes_added': meta['AllDataSaveSize'] - previous_saved_size}
