"""Fake item traps (``fake_item_traps``): an item that looks real, but freezes Link.

Each trap is a pouch actor ``Item_Trap_<code>`` built like the souls
(``soul_adapter.build_item_files``: Forest Medallion key-item template) with the
model, pose and name of the item it imitates (``catalog.traps.TRAPPED``). Its get
text says it is a trap. Traps go into chests and ground checks (``item_forms.can_take``):
the pouch writes their ``IsGet`` flag on their get event there, as for the souls
(``soul_adapter``: IsGet struct members); gifts and shops may skip that event.

The freeze reuses two vanilla mechanisms (verified on the local data, 27/11):

* the ice-trap chest ``Obj_TBox_A_04`` hits Link with an attack whose damage
  element is ``Frozen`` (its ``GameBalance/AttackParam``);
* the Sun's Song spawns ``SongOfTheSunSensorActor`` from an event flow
  (``Dm_SY_Ocarina``: ``GameSystemActor.EventTriggerRequestCreateConditionSensor``
  with ``ActorName``), a ``ConditionSensorActor`` whose only AI node is
  ``ExecuteSensorHitSetupAttack`` with its own attack parameters.

``RandoIceTrapSensor`` is a copy of the Sun's Song sensor with the trap chest's
attack and a small cylinder around Link. It hits the player as an enemy attack
does without any AI help (``Enemy_BabyDodongo``'s attack sensor: ``EnemyAttack``
layer, ``HitToPlayer`` mask, ``EnemyAttackReceipt`` contacts), and it is an
object, not one of Link's own attacks (``ObjectCommon`` affiliation, as the trap
chest and Twinrova's ice field). Its own AI (:func:`sensor_ai`, after Volvagia's
fire-breath field) waits :data:`SENSOR_WAIT_FRAMES` before attacking, attacks for
:data:`SENSOR_ATTACK_FRAMES`, then removes the sensor: hit at once, at the end of
the get event, Link only took damage. In game (27/11): first version (Sun's Song
hit setup) did not touch Link; second one (no wait) hurt him without freezing.
Child Link cannot be frozen in the vanilla game (``Player_Child``'s
``ConditionParam``: ``IsEnableFrozen: false``, the adult one is true): with traps,
:func:`enable_child_freeze` turns it on, so every ice attack freezes him too (the
trap hits only hurt child Link in game, 27/11, the cause of the misses above), and
:func:`child_ice_shell` gives him adult Link's ice shell effects (frozen without a
shell in game, 27/11: his ELink calls are blank). Every
item get ends in ``ActionGuide/ActionGuide`` (``key_adapter``): the hook checks each
trap of the seed; got and not sprung yet → saved ``RandoTrap.<code>`` set, sensor
created. Each trap freezes once. **Not validated in game.**
"""
import copy
import io

from oot_rando.catalog.traps import (ACTOR_PREFIX, SENSOR_ACTOR, actor_trap, model_actor, sprung_flag,
                                     trap_actor)
from oot_rando.formats import byml_codec, xlink
from oot_rando.formats.evfl_tools import params_by_event, parse_flow
from oot_rando.formats.inspect_resources import sarc

SENSOR_TEMPLATE = 'SongOfTheSunSensorActor'
TRAP_CHEST = 'Obj_TBox_A_04'
ATTACK_PARAM = 'GameBalance/AttackParam/{}.game__gamebalance__AttackParam.bgyml'
PLAYER_CONTACT = 'Phive/ContactCollectionSensorParam/EnemyAttackReceipt.phive__ContactCollectionSensorParam.bgyml'
CONTACT_LENDER = 'Enemy_BabyDodongo'       # an enemy attack sensor that hits Link with static parameters
SENSOR_LAYERS = {'EnableLayerHitMask': 'HitToPlayer', 'LayerSensor': 'EnemyAttack'}
AFFILIATION = '?Component/AffiliationParam/ObjectCommon.game__component__AffiliationParam.bgyml'
TEMPLATE_CONTACT = 'Phive/ContactCollectionSensorParam/HitToCharacterAndObject.phive__ContactCollectionSensorParam.bgyml'
SENSOR_PARAM = 'Phive/RigidBodySensorParam/{}_Atk.phive__RigidBodySensorParam.bgyml'
SHAPE_PARAM = 'Phive/ShapeParam/{}.phive__ShapeParam.bgyml'
CONTROLLER_SET = 'Phive/ControllerSetParam/{}.phive__ControllerSetParam.bgyml'
ELINK_PARAM = 'Component/ELink/{}.engine__component__ELinkParam.bgyml'
# Around Link only (the Sun's Song sensor reaches 12 m around him).
SENSOR_RADIUS, SENSOR_HALF_HEIGHT = 2.0, 1.5
# The get event ends a few steps after ActionGuide (auto-save request, item effect
# stop); Link is frozen only once he is back in play.
SENSOR_WAIT_FRAMES, SENSOR_ATTACK_FRAMES = 30.0, 30.0
SENSOR_AI = 'AI/{}.root.ainb'
SENSOR_AI_INFO = 'AI/AIInfo/{}.engine__actor__AIInfo.bgyml'
TEMPLATE_AI = 'AI/ConditionSensorActor.root.ainb'
TEMPLATE_AI_INFO = SENSOR_AI_INFO.format('ConditionSensorActor')
DEATH = '?Component/DeathParam/Default.game__component__DeathParam.bgyml'
FROZEN_ELEMENT = 2817341698          # murmur3('Frozen'), damage element of the trap chest attack
RSDB_TABLES = ('ActorInfo', 'GameActorInfo')
CREATE_SENSOR = 'EventTriggerRequestCreateConditionSensor'
HOOK_PREFIX = 'RandoTrap'
CHILD_PACK = 'Pack/Actor/Player_Child.pack.zs'
CHILD_CONDITION = 'Component/ConditionParam/Player_Child.game__component__ConditionParam.bgyml'
CHILD_CONDITION_PARENT = 'Work/Component/ConditionParam/Player.game__component__ConditionParam.gyml'
ELINK = 'ELink2/elink2.Product.110.belnk.zs'   # the copy the game loads (100 is the older one)
# ELink users of adult and child Link (their ELinkParam); the child's frozen calls play @Blank.
ADULT_EFFECTS, CHILD_EFFECTS = 'Player_Adult', 'Player'
# Child call -> adult tree it plays. The adult shell is a grid on the equipped weapon and
# its kind, adult items only (Master Sword, Hylian Shield, Hookshot...): child Link's
# match no cell, so he gets its whole-body branch, the one most adult items pick.
FROZEN_CALLS = {'Condition_Frozen': ('Condition_Frozen', '全身凍結'),
                'Condition_Frozen_End': ('Condition_Frozen_End',)}

TRAP_TEXTS = {
    'fr': ('Dommage, c’est un piège !', 'Brrr… Link est gelé !'),
    'en': ('Too bad, it’s a trap!', 'Brrr… Link is frozen!'),
}


def trap_texts(language):
    """(GetMessage, GetCaption) of every trap in ``language``."""
    return TRAP_TEXTS['fr' if language.endswith('fr') else 'en']


def pouch_name(read_raw, actor):
    """Pouch ActorName of a native item actor (its messages use it: Item_HoverBoot → Armor_Adult_HoverBoot)."""
    from oot_rando.patching.soul_adapter import RSDB_FILES
    rows = byml_codec.load(read_raw(RSDB_FILES['ActorInfo']))['root']
    row = next((r for r in rows if r.get('__RowId') == actor), None)
    if row is None or not isinstance(row.get('ActorName'), str):
        raise ValueError('Item actor not found for a trap: ' + actor)
    return row['ActorName']


def model_lender(read_raw, actor):
    """Actor whose pack holds the model information of ``actor`` (itself, or its pouch actor)."""
    for candidate in (actor, pouch_name(read_raw, actor)):
        path = f'Pack/Actor/{candidate}.pack.zs'
        try:
            pack = sarc(read_raw(path))
        except (KeyError, ValueError, FileNotFoundError):
            continue
        if f'Component/ModelInfo/{candidate}.engine__component__ModelInfo.bgyml' in pack:
            return candidate
    raise ValueError('No model for a trap: ' + actor)


def trap_specs(read_raw, traps):
    """``build_item_files`` specs of the trap actors (texts are written by :func:`patch_trap_messages`)."""
    from oot_rando.patching.progressive import actor_pose_parts
    specs = []
    for trap in sorted(traps):
        actor, lender = trap_actor(trap), model_actor(trap)
        name = HOOK_PREFIX + '_' + actor[len(ACTOR_PREFIX):] + '.event.root'
        spec = {'actor': actor, 'model': model_lender(read_raw, lender), 'event_name': name,
                'event_member': 'AI/' + name + '.ainb', 'event_ain': 'Work/AI/Root/Event/' + name + '.ain',
                'texts': None}
        pose = actor_pose_parts(read_raw, lender)
        if pose is not None:
            spec['files'], spec['components'], spec['actor_info'] = pose
        specs.append(spec)
    return specs


def patch_trap_messages(raw_archive, language, names):
    """Trap texts: name and description of the imitated item, trap get texts.

    ``names``: trap actor → pouch name of the imitated item."""
    from oot_rando.formats import msbt
    from oot_rando.patching.soul_adapter import MESSAGE_FILE
    files = dict(sarc(raw_archive))
    if MESSAGE_FILE not in files:
        raise ValueError('Item messages missing from the archive ' + language)
    message = msbt.load(files[MESSAGE_FILE])
    get_message, get_caption = trap_texts(language)
    for actor, pouch in sorted(names.items()):
        message.add_copy(f'{actor}_Name', f'{pouch}_Name')
        # Songs have no description: their name stands in.
        caption = f'{pouch}_Caption' if message.get(f'{pouch}_Caption') is not None else f'{pouch}_Name'
        message.add_copy(f'{actor}_Caption', caption)
        message.add(f'{actor}_GetMessage', get_message)
        message.add(f'{actor}_GetCaption', get_caption)
    files[MESSAGE_FILE] = msbt.dump(message)
    return byml_codec.build_sarc(files)


def _renamed(value, old, new):
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, dict):
        return {_renamed(k, old, new) if isinstance(k, str) else k: _renamed(v, old, new) for k, v in value.items()}
    if isinstance(value, list):
        return [_renamed(v, old, new) for v in value]
    return value


def _node(index, kind, name, properties=None, plugs=None, inputs=None, flags=()):
    import uuid
    return {'Node Type': kind, 'Node Index': index, 'Name': name,
            'GUID': str(uuid.uuid5(uuid.NAMESPACE_URL, f'oot-rando/{SENSOR_ACTOR}/{index}')),
            'Flags': list(flags), 'Queries': [], 'Attachments': [], 'Properties': properties or {},
            'Parameters': {'Inputs': inputs or {}, 'Outputs': {}}, 'XLink Actions': [], 'Plugs': plugs or {}}


def _counter(index, frames):
    """``ExecuteGenericCounter``: busy for ``frames``, then success (as in Volvagia's field)."""
    return _node(index, 'UserDefined', 'ExecuteGenericCounter', {
        'Int': [{'Name': 'ResultBeforeFinish', 'Default Value': 0, 'Flags': []},
                {'Name': 'ResultOnFinish', 'Default Value': 2, 'Flags': []}],
        'Float': [{'Name': 'BaseFrameTime', 'Default Value': frames, 'Flags': []},
                  {'Name': 'RandomTimeMax', 'Default Value': 0.0, 'Flags': []}]})


def sensor_ai(template_raw):
    """Root AI of the sensor: wait, attack for a while, then die.

    ``template_raw``: the vanilla ``ConditionSensorActor`` root AI (its only node is
    the attack). Same shape as ``DungeonBossVolvagia_FireBreathField.root``: a
    sequence of a counter, a simultaneous (counter + attack), then death."""
    import ainb
    from oot_rando.patching.ap_mailbox import ainb_to_binary
    document = ainb.AINB.from_binary(template_raw).as_dict()
    nodes = document['Nodes']
    if [n['Name'] for n in nodes] != ['ExecuteSensorHitSetupAttack']:
        raise ValueError('Unexpected condition sensor AI.')
    attack = copy.deepcopy(nodes[0])
    attack['Node Index'], attack['Flags'] = 4, []
    sequential = {'Int': [{'Name': n, 'Default Value': 0, 'Flags': []}
                          for n in ('BusyPolicy', 'NumLoop', 'PlayPolicy', 'ResultPolicy')],
                  'Bool': [{'Name': n, 'Default Value': False, 'Flags': []}
                           for n in ('IsDelayJudge', 'IsLoop', 'IsUpdateNextInFrame')]}
    simultaneous = {'Int': [{'Name': 'EndPolicy', 'Default Value': 0, 'Flags': []},
                            {'Name': 'ResultPolicy', 'Default Value': 1, 'Flags': []}]}
    death = {'Int': [{'Name': 'DeathReson', 'Default Value': 5, 'Node Index': -1, 'Output Index': 0,
                      'Flags': ['Uses Default']}]}
    document['Filename'] = f'{SENSOR_ACTOR}.root'
    document['Nodes'] = [
        _node(0, 'Element_Sequential', '', sequential,
              {'Child': [{'Node Index': i, 'Name': ''} for i in (1, 2, 5)]}, flags=['Is Root Node']),
        _counter(1, SENSOR_WAIT_FRAMES),
        _node(2, 'Element_Simultaneous', '', simultaneous,
              {'Child': [{'Node Index': i, 'Name': ''} for i in (3, 4)]}),
        _counter(3, SENSOR_ATTACK_FRAMES),
        attack,
        _node(5, 'UserDefined', 'OneShotDeathRequestDeath',
              {'Bool': [{'Name': 'ExecuteEveryFrame', 'Default Value': False, 'Flags': []}]}, inputs=death),
    ]
    result = ainb_to_binary(document)
    if ainb.AINB.from_binary(result).as_dict()['Nodes'] != document['Nodes']:
        raise ValueError('Trap sensor AI failed readback.')
    return result


def build_sensor_pack(read_raw):
    """Pack of :data:`SENSOR_ACTOR`: the Sun's Song sensor carrying the trap chest's attack."""
    template = sarc(read_raw(f'Pack/Actor/{SENSOR_TEMPLATE}.pack.zs'))
    chest = sarc(read_raw(f'Pack/Actor/{TRAP_CHEST}.pack.zs'))
    for path in (ATTACK_PARAM.format(SENSOR_TEMPLATE), SENSOR_PARAM.format(SENSOR_TEMPLATE),
                 SHAPE_PARAM.format(SENSOR_TEMPLATE), CONTROLLER_SET.format(SENSOR_TEMPLATE), TEMPLATE_CONTACT,
                 TEMPLATE_AI, TEMPLATE_AI_INFO):
        if path not in template:
            raise ValueError('Unexpected Sun\'s Song sensor: ' + path)
    attack = byml_codec.load(chest[ATTACK_PARAM.format(TRAP_CHEST)])
    params = attack['root'].get('AttackParams') or []
    if len(params) != 1 or params[0].get('DamageElements') != [FROZEN_ELEMENT]:
        raise ValueError('Unexpected ice trap chest attack.')
    lender = sarc(read_raw(f'Pack/Actor/{CONTACT_LENDER}.pack.zs'))
    if PLAYER_CONTACT not in lender:
        raise ValueError('Player attack contacts not found.')
    files = {}
    for path, raw in template.items():
        target = path.replace(SENSOR_TEMPLATE, SENSOR_ACTOR)
        if path == ELINK_PARAM.format(SENSOR_TEMPLATE):
            continue               # the Sun's Song light and sound effects
        if path.endswith('.bgyml'):
            document = byml_codec.load(raw)
            document['root'] = _renamed(document['root'], SENSOR_TEMPLATE, SENSOR_ACTOR)
            raw = byml_codec.dump(document)
        files[target] = raw
    actor_param = f'Actor/{SENSOR_ACTOR}.engine__actor__ActorParam.bgyml'
    document = byml_codec.load(files[actor_param])
    components = document['root']['Components']
    if components.pop('ELinkRef', None) is None:
        raise ValueError("Sun's Song sensor effects not found.")
    components['AffiliationRef'] = AFFILIATION      # an object's attack, not Link's
    components['DeathRef'] = DEATH                  # its AI removes it after the attack
    components['AIInfoRef'] = '?' + SENSOR_AI_INFO.format(SENSOR_ACTOR)
    # Its own AI: the Sun's Song keeps the shared ConditionSensorActor one.
    files[SENSOR_AI.format(SENSOR_ACTOR)] = sensor_ai(template[TEMPLATE_AI])
    info = byml_codec.load(template[TEMPLATE_AI_INFO])
    info['root'] = {'RootAIRef': f'Work/AI/Root/{SENSOR_ACTOR}.root.ain'}
    files[SENSOR_AI_INFO.format(SENSOR_ACTOR)] = byml_codec.dump(info)
    files[actor_param] = byml_codec.dump(document)
    files[ATTACK_PARAM.format(SENSOR_ACTOR)] = byml_codec.dump(copy.deepcopy(attack))
    # Hits the player as an enemy attack does (the Sun's Song sensor only hits enemies).
    path = SENSOR_PARAM.format(SENSOR_ACTOR)
    document = byml_codec.load(files[path])
    root = document['root']
    if root.get('EnableLayerHitMask') != 'HitToEnemy':
        raise ValueError("Unexpected Sun's Song sensor mask.")
    root.pop('SubLayerSensor', None)
    root.update(SENSOR_LAYERS)
    files[path] = byml_codec.dump(document)
    files[PLAYER_CONTACT] = lender[PLAYER_CONTACT]
    path = CONTROLLER_SET.format(SENSOR_ACTOR)
    document = byml_codec.load(files[path])
    old, new = 'Work/' + TEMPLATE_CONTACT[:-len('.bgyml')] + '.gyml', 'Work/' + PLAYER_CONTACT[:-len('.bgyml')] + '.gyml'
    contacts = document['root']['CColSensorNamePathAry']
    if [c['FilePath'] for c in contacts] != [old]:
        raise ValueError("Unexpected Sun's Song sensor contacts.")
    contacts[0]['FilePath'] = new
    files[path] = byml_codec.dump(document)
    del files[TEMPLATE_CONTACT]
    path = SHAPE_PARAM.format(SENSOR_ACTOR)
    document = byml_codec.load(files[path])
    cylinders = document['root'].get('Cylinder') or []
    if len(cylinders) != 1:
        raise ValueError('Unexpected Sun\'s Song sensor shape.')
    cylinders[0]['Radius'] = SENSOR_RADIUS
    cylinders[0]['CenterA']['Y'], cylinders[0]['CenterB']['Y'] = SENSOR_HALF_HEIGHT, -SENSOR_HALF_HEIGHT
    calc = document['root']['AutoCalc']
    calc['Max'] = {'X': SENSOR_RADIUS, 'Y': SENSOR_HALF_HEIGHT, 'Z': SENSOR_RADIUS}
    calc['Min'] = {'X': -SENSOR_RADIUS, 'Y': -SENSOR_HALF_HEIGHT, 'Z': -SENSOR_RADIUS}
    files[path] = byml_codec.dump(document)
    return byml_codec.build_sarc(files)


def enable_child_freeze(raw_pack):
    """``Player_Child`` pack where child Link can be frozen (vanilla: adult only)."""
    files = dict(sarc(raw_pack))
    if CHILD_CONDITION not in files:
        raise ValueError('Child Link condition parameters not found.')
    document = byml_codec.load(files[CHILD_CONDITION])
    root = document['root']
    if root == {'$parent': CHILD_CONDITION_PARENT, 'IsEnableFrozen': True}:
        return raw_pack
    if root != {'$parent': CHILD_CONDITION_PARENT, 'IsEnableFrozen': False}:
        raise ValueError('Unexpected child Link condition parameters.')
    root['IsEnableFrozen'] = True
    files[CHILD_CONDITION] = byml_codec.dump(document)
    return byml_codec.build_sarc(files)


def child_ice_shell(raw_elink):
    """ELink table where child Link shows adult Link's ice shell and its break.

    The child user's ``Condition_Frozen``/``_End`` are blank assets; the adult's are the
    shell tree (whole/lower body, 16 poses, cap; see :data:`FROZEN_CALLS`) and the shatter (``Ply_Frozen_*_Adult``
    emitter sets, the only ones in the game: the shell is adult-sized)."""
    for key, source in FROZEN_CALLS.items():
        if xlink.call_tree(raw_elink, CHILD_EFFECTS, (key,)) != xlink.call_tree(raw_elink, ADULT_EFFECTS, source):
            raw_elink = xlink.graft_call(raw_elink, ADULT_EFFECTS, CHILD_EFFECTS, key, source)
    return raw_elink


def add_sensor_rows(read_raw, modified):
    """RSDB rows of the sensor, cloned from the Sun's Song sensor."""
    from oot_rando.patching.soul_adapter import RSDB_FILES
    for table in RSDB_TABLES:
        path = RSDB_FILES[table]
        raw = modified.get(path)
        document = byml_codec.load(raw if raw is not None else read_raw(path))
        rows = document['root']
        by_id = {row['__RowId']: row for row in rows}
        if SENSOR_TEMPLATE not in by_id or SENSOR_ACTOR in by_id:
            raise ValueError(f'Unexpected {table} table for the trap sensor.')
        row = copy.deepcopy(by_id[SENSOR_TEMPLATE])
        row['__RowId'] = SENSOR_ACTOR
        row.pop('ELinkUserName', None)
        rows.append(row)
        rows.sort(key=lambda r: r['__RowId'])
        modified[path] = byml_codec.dump(document)


def trap_records(traps):
    """Hook records of the traps of a seed (planner names), as stored in the manifest."""
    return [{'actor': trap_actor(trap), 'item': trap, 'flag': sprung_flag(trap_actor(trap))}
            for trap in sorted(set(traps), key=trap_actor)]


def build_trap_files(read_raw, traps, message_archives=()):
    """``(modified, new)`` resources of the trap actors, their sensor, texts and saved flags.

    ``read_raw`` returns the current (possibly modified) raw resources."""
    from oot_rando.game.tracking_metadata import add_saved_flags
    from oot_rando.patching.soul_adapter import GAMEDATA, build_item_files
    if not traps:
        return {}, {}
    modified, new = build_item_files(read_raw, trap_specs(read_raw, traps), ())

    def current(path):
        return modified[path] if path in modified else read_raw(path)

    names = {trap_actor(trap): pouch_name(read_raw, model_actor(trap)) for trap in traps}
    for path in message_archives:
        language = path.split('/')[-1].split('.')[0]
        modified[path] = patch_trap_messages(current(path), language, names)
    modified[GAMEDATA] = add_saved_flags(current(GAMEDATA), {r['flag']: False for r in trap_records(traps)})
    add_sensor_rows(current, modified)
    modified[CHILD_PACK] = enable_child_freeze(current(CHILD_PACK))
    modified[ELINK] = child_ice_shell(current(ELINK))
    new[f'Pack/Actor/{SENSOR_ACTOR}.pack.zs'] = (build_sensor_pack(read_raw), f'Pack/Actor/{SENSOR_TEMPLATE}.pack.zs')
    return modified, new


def add_trap_hook(raw, records):
    """Prepend the trap checks to ``ActionGuide/ActionGuide``. Returns (bytes, report).

    Bool switches: case 0 = true (as the vanilla flows)."""
    from evfl.event import Event, ActionEvent, SwitchEvent
    from evfl.util import make_index, make_rindex
    from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS
    from oot_rando.patching.key_adapter import ACTION_GUIDE_ENTRY, got_flag
    flow = parse_flow(raw)
    chart = flow.flowchart
    expected = params_by_event(flow)
    entries = {e.name: e for e in chart.entry_points}
    if ACTION_GUIDE_ENTRY not in entries or entries[ACTION_GUIDE_ENTRY].main_event.v is None:
        raise ValueError('Unexpected ActionGuide flow.')
    if any(e.name.startswith(HOOK_PREFIX) for e in chart.events):
        raise ValueError('ActionGuide flow already has the traps.')

    def system_actor(name):
        found = next((a for a in chart.actors if a.identifier.name == name and a.identifier.sub_name == ''), None)
        if found is None or dict(found.params.data) != GAMEDATA_ACTOR_PARAMS:
            raise ValueError('ActionGuide actor missing or unexpected: ' + name)
        return found

    def holder(collection, name):
        from evfl.common import StringHolder
        found = next((h for h in collection if h.v == name), None)
        if found is None:
            found = StringHolder(name)
            collection.append(found)
        return found

    gamedata, system = system_actor('GameDataActor'), system_actor('GameSystemActor')
    is_bool = holder(gamedata.queries, 'EventQueryIsGameDataBool')
    set_bool = holder(gamedata.actions, 'EventTriggerSetGameDataBool')
    create = holder(system.actions, CREATE_SENSOR)

    def event(name, data):
        e = Event()
        e.name, e.data = name, data
        chart.events.append(e)
        return e

    def action(name, actor, act, params, following):
        from evfl.container import Container
        data = ActionEvent()
        data.actor, data.actor_action = make_rindex(actor), make_rindex(act)
        data.params = Container()
        data.params.data = dict(params)
        data.nxt = make_index(following)
        expected[name] = dict(params)
        return event(name, data)

    def switch(name, params, true, false):
        from evfl.container import Container
        data = SwitchEvent()
        data.actor, data.actor_query = make_rindex(gamedata), make_rindex(is_bool)
        data.params = Container()
        data.params.data = dict(params)
        data.cases = {0: make_index(true), 1: make_index(false)}
        expected[name] = dict(params)
        return event(name, data)

    entry = entries[ACTION_GUIDE_ENTRY]
    following = entry.main_event.v
    report = []
    for record in reversed(records):
        stem = record['actor'][len(ACTOR_PREFIX):]
        freeze = action(f'{HOOK_PREFIX}Freeze_{stem}', system, create, {'ActorName': SENSOR_ACTOR}, following)
        mark = action(f'{HOOK_PREFIX}Sprung_{stem}', gamedata, set_bool,
                      {'GameDataName': record['flag'], 'Value': True, 'Index': -1}, freeze)
        done = switch(f'{HOOK_PREFIX}Done_{stem}', {'GameDataName': record['flag'], 'Index': -1}, following, mark)
        first = switch(f'{HOOK_PREFIX}Got_{stem}', {'GameDataName': got_flag(record['actor']), 'Index': -1},
                       done, following)
        report.append({'actor': record['actor'], 'start': first.name})
        following = first
    entry.main_event = make_index(following)
    stream = io.BytesIO()
    flow.write(stream)
    result = stream.getvalue()
    checked = parse_flow(result)
    if params_by_event(checked) != expected:
        raise ValueError('Fake item traps changed other parameters.')
    start = {e.name: e for e in checked.flowchart.entry_points}[ACTION_GUIDE_ENTRY].main_event.v
    if records and start.name != f"{HOOK_PREFIX}Got_{records[0]['actor'][len(ACTOR_PREFIX):]}":
        raise ValueError('ActionGuide entry wrongly attached to the traps.')
    return result, list(reversed(report))


def placed_traps(placements):
    """Planner names of the traps placed in a plan's placements (chests and pickups)."""
    from oot_rando.catalog.traps import is_trap_actor
    from oot_rando.game.item_forms import canonical_of, is_derived
    actors = (canonical_of(p['after']) if is_derived(p['after']) else p['after'] for p in placements)
    return sorted({actor_trap(actor) for actor in actors if is_trap_actor(actor)})
