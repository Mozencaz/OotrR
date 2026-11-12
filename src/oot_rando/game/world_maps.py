"""Experimental, conservative world-wide native map reward adapter.

Only expendable loot is shuffled. Progression, unknown reward paths, nonempty
drop tables, special chest events and substitution/repeat mechanics are retained
and counted. This adapter makes no beatability or persistence claim.
"""
from collections import Counter, defaultdict
import hashlib

from oot_rando.formats.byml_writer import patch_strings
from oot_rando.formats.inspect_resources import Byml, decompress, sarc
from oot_rando.patching.randomize_kokiri import CHESTS
from oot_rando.game.randomizer_categories import candidate_category, CATEGORIES

SUPPORTED_CATEGORIES = frozenset({'world_chests', 'pots', 'trees', 'bushes', 'crates',
                                  'rocks', 'beehives', 'enemies', 'loose_items', 'scrubs'})
SAFE_CATEGORIES = frozenset({'world_chests', 'pots', 'bushes', 'rocks'})
ENVIRONMENT = frozenset({'pots', 'trees', 'bushes', 'crates', 'rocks', 'beehives', 'enemies'})
NATIVE_POOL = ('Obj_Rupee_Green', 'Obj_Rupee_Blue', 'Obj_Rupee_Red', 'Obj_Rupee_Purple', 'Obj_Heart')
SAFE_NATIVE = frozenset(NATIVE_POOL) | {'Obj_Rupee_Gold', 'Obj_MagicJar_Small', 'Obj_Fairy',
    'Obj_Bomb', 'Obj_ArrowBundle_Small', 'Obj_DekuStick', 'Obj_DekuSeed', 'Animal_Insect'}
SAFE_CHESTS = frozenset({'TBox_Rupee_Green', 'TBox_Rupee_Blue', 'TBox_Rupee_Red',
    'TBox_Rupee_Purple', 'TBox_Rupee_Gold'})
SAFE_SCRUBS = frozenset({'Shop_DekuNutBundle_01', 'Shop_BombBundle_01', 'Shop_BombBundle_02',
    'Shop_BombchuBundle_01', 'Shop_ArrowBundle_01', 'Shop_ArrowBundle_02',
    'Shop_DekuSeedBundle_01', 'Shop_DekuSeedBundle_02', 'Shop_Heart_Bundle',
    'Item_Bottle_RedPotion', 'Item_Bottle_GreenPotion'})


def effective_members(nup):
    result = {}
    for package in ('0', '1'):
        prefix = package + '/romfs/'
        for member in sorted(nup.entries):
            if member.startswith(prefix):
                result[member[len(prefix):]] = member
    return result


def _pick(values, key):
    choices = sorted(values)
    limit = (1 << 256) - (1 << 256) % len(choices)
    counter = 0
    while True:
        sample = int.from_bytes(hashlib.sha256(key.encode('utf-8') + counter.to_bytes(8, 'big')).digest(), 'big')
        if sample < limit:
            return choices[sample % len(choices)]
        counter += 1


def build_world(nup, dictionaries, categories, seed_key, avoid_vanilla=True, progress=None):
    """Return uncompressed maps plus explicit changed/preserved coverage.

    The caller owns build validation, composition with other adapters, compression
    and RESTBL allocation. No file is written by this function.
    """
    if not isinstance(seed_key, str) or not seed_key:
        raise ValueError('A versioned seed key is required.')
    if not isinstance(categories, dict) or set(categories) - set(CATEGORIES) or any(type(v) is not bool for v in categories.values()):
        raise ValueError('Invalid world categories.')
    if type(avoid_vanilla) is not bool:
        raise ValueError('avoid_vanilla must be boolean.')
    enabled = {name for name, value in categories.items() if value}
    if enabled - SAFE_CATEGORIES:
        raise ValueError('Categories disabled in the first prudent release: '
                         + ', '.join(sorted(enabled - SAFE_CATEGORIES)))
    report = progress or (lambda message: None)
    members = effective_members(nup)
    maps, packs = {}, {}
    groups = defaultdict(list)
    coverage = {category: {'status': 'experimental' if category in SUPPORTED_CATEGORIES else 'unsupported',
                           'candidate_instances': 0, 'candidate_groups': 0, 'changed_instances': 0,
                           'changed_groups': 0, 'skipped': {}}
                for category in sorted(enabled)}
    skipped = defaultdict(Counter)

    def pack(actor):
        if actor not in packs:
            path = 'Pack/Actor/' + actor + '.pack.zs'
            if path not in members:
                packs[actor] = None
            else:
                packs[actor] = sarc(decompress(nup.read(members[path]), dictionaries))
        return packs[actor]

    def exists(actor):
        data = pack(actor)
        expected = f'Actor/{actor}.engine__actor__ActorParam.bgyml'
        if data is None or expected not in data:
            return False
        Byml(data[expected])
        return True

    proof_cache = {}

    def instance_string(actor, field):
        cache_key = (actor, field)
        if cache_key not in proof_cache:
            data = pack(actor)
            proof_cache[cache_key] = False
            if data:
                for path, raw in data.items():
                    if 'BlackboardParamTable/' not in path or not path.endswith('.bgyml'):
                        continue
                    root = Byml(raw).root
                    if not isinstance(root, dict):
                        continue
                    for entry in root.get('BlackboardParamStringArray', []):
                        if entry.get('BBKey') == field and entry.get('IsInstanceParam') is True:
                            proof_cache[cache_key] = True
        return proof_cache[cache_key]

    map_names = sorted(p for p in members if p.startswith('Banc/') and p.endswith('.bcett.byml.zs'))
    for index, path in enumerate(map_names):
        report(f'Analysing world rewards: {index + 1}/{len(map_names)}')
        compressed = nup.read(members[path])
        raw = decompress(compressed, dictionaries)
        root = Byml(raw).root
        maps[path] = {'raw': raw, 'compressed_sha256': hashlib.sha256(compressed).hexdigest(), 'root': root}
        region = path.split('/')[1]
        for actor_index, actor in enumerate(root.get('Actors', [])):
            name = actor.get('Gyaml', '')
            category = candidate_category(actor)
            if name in NATIVE_POOL:
                category = 'loose_items'
            if category not in enabled or category not in SUPPORTED_CATEGORIES:
                continue
            if type(actor.get('Hash')) is not int:
                skipped[category]['missing_hash'] += 1
                continue
            dynamic = actor.get('Dynamic', {})
            if not isinstance(dynamic, dict):
                skipped[category]['invalid_dynamic'] += 1
                continue
            ident = str(actor['Hash'])
            coverage[category]['candidate_instances'] += 1
            if category == 'scrubs':
                fields = [key for key in dynamic if key.startswith('ScrubBusiness_ShopItemActorName')]
            elif category == 'loose_items':
                fields = ['Gyaml']
            else:
                fields = ['Drop__DropActor']
            if not fields:
                skipped[category]['no_native_reward_field'] += 1
            for field in sorted(fields):
                before = name if field == 'Gyaml' else dynamic.get(field)
                reason = None
                if region == 'KokiriForest' and actor['Hash'] in CHESTS:
                    reason = 'owned_by_kokiri_adapter'
                elif category == 'world_chests':
                    if name != 'Obj_TBox_A_01':
                        reason = 'chest_actor_not_validated'
                    elif before not in SAFE_CHESTS:
                        reason = 'progression_or_unknown_reward_preserved'
                    elif 'GetEventName' in dynamic:
                        reason = 'special_chest_event_preserved'
                    elif any(key in dynamic for key in ('Drop__CheckActor', 'Drop__DropActor_Substitute', 'IsEnableRepeatOpen')):
                        reason = 'substitution_or_repeat_preserved'
                elif category in ENVIRONMENT:
                    if any(dynamic.get(key) for key in ('Drop__DropTable', 'Drop__DropTableOverWrite')):
                        reason = 'nonempty_drop_table_priority_unknown'
                    elif any(key in dynamic for key in ('Drop__CheckActor', 'Drop__DropActor_Substitute', 'GetEventName')):
                        reason = 'special_drop_behavior_preserved'
                    elif not isinstance(before, str) or not before:
                        reason = 'no_explicit_native_reward'
                    elif before not in SAFE_NATIVE:
                        reason = 'progression_or_unknown_reward_preserved'
                    elif not instance_string(name, field):
                        reason = 'instance_parameter_not_proven'
                elif category == 'scrubs':
                    if before not in SAFE_SCRUBS:
                        reason = 'progression_or_unknown_reward_preserved'
                    elif not instance_string(name, field):
                        reason = 'instance_parameter_not_proven'
                elif name not in NATIVE_POOL:
                    reason = 'progression_or_unknown_reward_preserved'
                group_id = region + '#' + ident + '#' + field
                groups[group_id].append({'resource': path, 'index': actor_index, 'category': category,
                    'hash': ident, 'actor': name, 'field': field, 'before': before, 'reason': reason})

    edits, placements, checks = defaultdict(list), [], []
    pools = {'world_chests': [v for v in SAFE_CHESTS if exists(v)],
             'scrubs': [v for v in SAFE_SCRUBS if exists(v)]}
    native = [value for value in NATIVE_POOL if exists(value)]

    def reasons_for(variants):
        reasons = sorted({v['reason'] for v in variants if v['reason']})
        if len({v['category'] for v in variants}) != 1 or len({v['actor'] for v in variants}) != 1:
            reasons.append('variant_actor_mismatch')
        if len({v['before'] for v in variants}) != 1:
            reasons.append('variant_reward_mismatch')
        if len({v['resource'] for v in variants}) != len(variants):
            reasons.append('ambiguous_hash_in_resource')
        return reasons

    # Keep the exact rupee multiset per cross-age group. Rotating contiguous
    # equal-value blocks by the largest block gives a maximal derangement,
    # including unavoidable unchanged entries when one value is a majority.
    chest_candidates = [(ident, variants[0]['before']) for ident, variants in groups.items()
                        if variants[0]['category'] == 'world_chests' and not reasons_for(variants)]
    chest_assignments = {}
    if chest_candidates:
        keyed = lambda text: hashlib.sha256((seed_key + '\0' + text).encode()).digest()
        if avoid_vanilla:
            ordered = sorted(chest_candidates, key=lambda item: (keyed('value:' + item[1]), keyed('group:' + item[0])))
            values = [value for _, value in ordered]
            shift = max(Counter(values).values())
            shuffled = values[shift:] + values[:shift]
        else:
            ordered = sorted(chest_candidates)
            shuffled = [value for _, value in sorted(chest_candidates, key=lambda item: keyed('draw:' + item[0]))]
        chest_assignments = {ident: value for (ident, _), value in zip(ordered, shuffled)}
    for group_id, variants in sorted(groups.items()):
        category = variants[0]['category']
        coverage[category]['candidate_groups'] += 1
        reasons = reasons_for(variants)
        if reasons:
            for reason in sorted(set(reasons)):
                skipped[category][reason] += len(variants)
            continue
        before = variants[0]['before']
        pool = pools.get(category, native)
        choices = [v for v in pool if not avoid_vanilla or v != before]
        if not choices:
            skipped[category]['empty_compatible_pool'] += len(variants)
            continue
        after = chest_assignments[group_id] if category == 'world_chests' else _pick(choices, seed_key + '\0world-map-v1\0' + group_id)
        if after == before:
            skipped[category]['same_reward_drawn'] += len(variants)
            continue
        resources = []
        for variant in variants:
            path = ('Actors', variant['index'], 'Gyaml') if variant['field'] == 'Gyaml' else ('Actors', variant['index'], 'Dynamic', variant['field'])
            edits[variant['resource']].append({'path': path, 'before': before, 'after': after})
            resources.append(variant['resource'])
        repeated = category != 'world_chests'
        placements.append({'id': group_id, 'category': category, 'hash': variants[0]['hash'],
                           'before': before, 'after': after, 'resources': sorted(resources), 'repeatable': repeated})
        checks.append({'id': group_id, 'region': group_id.split('#')[0], 'category': category,
                       'name': variants[0]['actor'] + ' — ' + variants[0]['hash'],
                       'resources': sorted(resources), 'repeatable': repeated, 'randomized': True,
                       'collection_state': 'unverified'})
        coverage[category]['changed_groups'] += 1
        coverage[category]['changed_instances'] += len(variants)
    raw_maps, sources, source_members, original_sizes = {}, {}, {}, {}
    for path, changes in sorted(edits.items()):
        report('Composing drops: ' + path)
        raw_maps[path] = patch_strings(maps[path]['raw'], changes)
        sources[path] = maps[path]['compressed_sha256']
        source_members[path] = members[path]
        original_sizes[path] = len(maps[path]['raw'])
    for category, value in coverage.items():
        value['skipped'] = dict(sorted(skipped[category].items()))
        value['complete'] = False
    return {'raw_maps': raw_maps, 'sources': sources, 'source_members': source_members,
            'original_sizes': original_sizes, 'placements': placements, 'checks': checks,
            'coverage': coverage}
