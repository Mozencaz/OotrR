"""Native combat dependencies, read from map AI groups rather than AP room names.

The AP graph and the remake do not have identical room boundaries. Dungeon
dependencies are deliberately enforced at the entrance; physical reward actors
are guarded individually. Only overworld passage battles need named AP regions.
"""
from collections import defaultdict


DEATH_OUTPUTS = frozenset(('Dead', 'AllDestroyed', 'IsDeadNotDelay',
                           'IsDeadPerforming', 'Request_Event_BossOut'))

# These fights open a passage, not just a chest included in the AI group.
# All locations AND events in the region must wait for the fight's soul.
PASSAGE_REGIONS = {
    'RoyalFamilyTomb_Common_eea8': ('Graveyard Royal Familys Tomb',),
    'Gimmick_DefeatEnemy_Open_03_c235': ('Sacred Forest Meadow',),
}


def module_path(logic):
    return 'Logic/' + logic.rsplit('/', 1)[-1].removesuffix('.ain') + '.ainb'


def death_signals(module):
    """Used defeat outputs in a native logic module (including module nodes)."""
    def enemy_node(node):
        return ('Enemy' in node.get('Name', '') or any(
            prop.get('Name') == 'InstanceName' and prop.get('Default Value', '').startswith('Enemy_')
            for prop in node.get('Properties', {}).get('String', ())))

    return sorted({node['Name'] + '.' + output['Name']
                   for node in module.get('Nodes', []) if enemy_node(node)
                   for outputs in node.get('Parameters', {}).get('Outputs', {}).values()
                   for output in outputs
                   if output.get('Is Output') and output['Name'] in DEATH_OUTPUTS})


def module_signals(logic, read_module, visited=None):
    """Include defeat conditions internal to nested native room modules."""
    visited = visited if visited is not None else set()
    if logic in visited:
        return []
    visited.add(logic)
    module = read_module(logic)
    signals = [logic + ':' + signal for signal in death_signals(module)]
    for node in module.get('Nodes', ()):
        name = node.get('Name', '')
        if 'Is Module' in node.get('Flags', ()) and '.logic.' in name:
            signals.extend(module_signals(module_path(name), read_module, visited))
    return sorted(set(signals))


def combat_dependencies(path, root, read_module):
    """Enemy hash -> native room evidence, including AI-only defeat conditions.

    An AI group is a conservative room boundary: if a fight drives a result,
    all its soul-bound enemies must be present. Counters and direct map links
    remain authoritative even when the AI is nested. No game data is modified.
    """
    by_hash = {a['Hash']: a for a in root.get('Actors', []) if type(a.get('Hash')) is int}
    result = defaultdict(list)
    for group in root.get('AiGroups', []):
        actors = {ref['Reference']: by_hash[ref['Reference']]
                  for ref in group.get('References', []) if ref.get('Reference') in by_hash}
        # Some modules only reference a counter; its enemies live in another
        # group (Water Temple room 17 controls the spikes of room 18).
        for counter in list(actors.values()):
            if counter.get('Gyaml', '').startswith('Obj_EnemyCounter'):
                for link in counter.get('Links', ()):
                    target = by_hash.get(link.get('Dst'), {})
                    if target.get('Gyaml', '').startswith('Enemy_'):
                        actors[target['Hash']] = target
        enemies = [a for a in actors.values() if a.get('Gyaml', '').startswith('Enemy_')]
        if not enemies:
            continue
        logic = module_path(group['Logic'])
        visited = set()
        signals = module_signals(logic, read_module, visited)
        counters = [a for a in actors.values() if a.get('Gyaml', '').startswith('Obj_EnemyCounter')]
        shutters = [a for a in actors.values() if 'Shutter' in a.get('Gyaml', '')]
        # Many script-created chests have NO SpawnType field (Wolfos,
        # Dinolfos, the scrub brothers). The AI group supplies their condition.
        chests = [a for a in actors.values() if a.get('Gyaml', '').startswith('Obj_TBox')]
        if not (signals or counters or shutters or chests):
            continue
        name = logic.removeprefix('Logic/').split('.logic.')[0]
        evidence = {'id': path + '#' + str(group['Hash']), 'logic': logic,
                    'signals': signals, 'logic_modules': sorted(visited),
                    'regions': list(PASSAGE_REGIONS.get(name, ())),
                    'targets': [str(h) for h in sorted(actors) if actors[h] not in enemies]}
        for enemy in enemies:
            result[enemy['Hash']].append(evidence)
    return dict(result)
