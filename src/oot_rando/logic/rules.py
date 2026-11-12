"""Glitchless logic engine of the remake world (:mod:`oot_rando.logic.world`).

The rule language is the OoTR/AP Python-like expression language. Helpers are
expanded as macros, setting names are folded to constants and the result is
compiled to Python closures evaluated against a :class:`State`.
"""
import ast
import copy
import re
from collections import defaultdict

from oot_rando.logic.world import REMAKE_LOCATION_REGIONS, REMAKE_LOCATION_RULES, World  # noqa: F401

TRIALS = ('Forest', 'Fire', 'Water', 'Shadow', 'Spirit', 'Light')
STONES = ('Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire')
MEDALLIONS = ('Forest Medallion', 'Fire Medallion', 'Water Medallion', 'Shadow Medallion',
              'Spirit Medallion', 'Light Medallion')

# Values of the AP options that describe the unmodified remake. Options the
# application does not patch must keep these values, both in game and in logic.
AP_VANILLA_SETTINGS = {
    'logic_rules': 'glitchless', 'open_forest': 'closed', 'open_kakariko': 'closed',
    'open_door_of_time': False, 'zora_fountain': 'closed', 'gerudo_fortress': 'normal',
    'bridge': 'vanilla', 'bridge_stones': 3, 'bridge_medallions': 6, 'bridge_rewards': 9,
    'bridge_tokens': 100, 'bridge_hearts': 20, 'trials': 6,
    'lacs_condition': 'vanilla', 'lacs_stones': 3, 'lacs_medallions': 6, 'lacs_rewards': 9,
    'lacs_tokens': 100, 'lacs_hearts': 20, 'shuffle_ganon_bosskey': 'vanilla',
    'ganon_bosskey_stones': 3, 'ganon_bosskey_medallions': 6, 'ganon_bosskey_rewards': 9,
    'ganon_bosskey_tokens': 100, 'ganon_bosskey_hearts': 20, 'triforce_goal_per_world': 20,
    'starting_age': 'child', 'bombchus_in_logic': False, 'damage_multiplier': 'normal',
    'deadly_bonks': 'normal', 'dungeon_shortcuts': [], 'entrance_shuffle': False,
    'shuffle_dungeon_entrances': False, 'shuffle_interior_entrances': False,
    'shuffle_overworld_entrances': False, 'warp_songs': False, 'plant_beans': False,
    'free_scarecrow': False, 'big_poe_count': 10, 'chicken_count': 7,
    'complete_mask_quest': False, 'disable_trade_revert': False, 'fix_broken_drops': False,
    'hints': 'none', 'keysanity': False, 'shuffle_scrubs': 'off', 'shuffle_pots': 'off',
    'shuffle_child_trade': 'vanilla', 'blue_fire_arrows': False, 'had_night_start': False,
}


# AP Rules.set_shop_rules: Python-only rules added to every location selling
# these items (wallet for the price, adult-only tunics, bottle, bombchu bag).
_SHOP_WALLET1 = ('Buy Arrows (50)', 'Buy Fish', 'Buy Goron Tunic', 'Buy Bombchu (20)', 'Buy Bombs (30)')
_SHOP_WALLET2 = ('Buy Zora Tunic', 'Buy Blue Fire')
_SHOP_ADULT = ('Buy Goron Tunic', 'Buy Zora Tunic')
_SHOP_BOTTLE = ('Buy Blue Fire', 'Buy Blue Potion', 'Buy Bottle Bug', 'Buy Fish', 'Buy Green Potion', 'Buy Poe',
                'Buy Red Potion [30]', 'Buy Red Potion [40]', 'Buy Red Potion [50]', "Buy Fairy's Spirit",
                'Buy Red Potion for 30 Rupees', 'Buy Red Potion for 40 Rupees', 'Buy Red Potion for 50 Rupees')
_SHOP_BOMBCHU = ('Buy Bombchu (10)', 'Buy Bombchu (20)', 'Buy Bombchu (5)')
# AP item group ``logic_bottles`` (Ruto's letter and a Big Poe only count once
# delivered / sold).
LOGIC_BOTTLES = ('Bottle', 'Bottle with Milk', 'Bottle with Red Potion', 'Bottle with Green Potion',
                 'Bottle with Blue Potion', 'Bottle with Fairy', 'Bottle with Fish', 'Bottle with Blue Fire',
                 'Bottle with Bugs', 'Bottle with Poe', 'Deliver Letter', 'Sell Big Poe')


def shop_rule(item):
    """AP ``set_shop_rules`` requirement for a location selling ``item``."""
    parts = []
    if item in _SHOP_WALLET1:
        parts.append('Progressive_Wallet')
    elif item in _SHOP_WALLET2:
        parts.append('(Progressive_Wallet, 2)')
    if item in _SHOP_ADULT:
        parts.append('is_adult')
    if item in _SHOP_BOTTLE:
        parts.append('has_bottle')
    if item in _SHOP_BOMBCHU:
        parts.append('found_bombchus')
    return ' and '.join(parts) or None


def escape_name(name):
    return re.sub(r"['()\[\]-]", '', name.replace(' ', '_'))


class State:
    __slots__ = ('counts', 'reached', 'tod')

    def __init__(self, counts=None):
        self.counts = dict(counts or {})
        self.reached = {'child': set(), 'adult': set()}
        self.tod = {'child': False, 'adult': False}

    def has(self, item, count=1):
        return self.counts.get(item, 0) >= count

    def add(self, item, count=1):
        self.counts[item] = self.counts.get(item, 0) + count

    def count(self, item):
        return self.counts.get(item, 0)


class Logic:
    """Compiled AP world. ``extra_exit_requirements`` gates region entries."""

    SPECIAL_NAMES = {'has_bottle', 'at_night', 'at_day', 'at_dampe_time',
                     'current_spot_child_access', 'current_spot_adult_access',
                     'current_spot_starting_age_access'}

    def __init__(self, data, settings=None, extra_exit_requirements=None, extra_location_requirements=None):
        self.data = data
        self.settings = dict(AP_VANILLA_SETTINGS)
        self.settings.update(settings or {})
        trials = self.settings['trials']
        self.settings['skipped_trials'] = {name: index >= trials for index, name in enumerate(TRIALS)}
        self.helpers = {}
        self._cache = {}
        for key, body in data.helpers.items():
            match = re.fullmatch(r'(\w+)(?:\((\w+(?:,\s*\w+)*)\))?', key)
            params = [p.strip() for p in match.group(2).split(',')] if match.group(2) else []
            self.helpers[match.group(1)] = (params, self._parse(body))
        names = {}
        for item in data.item_table:
            names[escape_name(item)] = item
        events = set()
        for region in data.regions:
            for event in region.get('events', {}):
                events.add(event)
        for event in events:
            names.setdefault(escape_name(event), event)
        self.names = names
        self.bottles = tuple(item for item in LOGIC_BOTTLES if item in data.item_table or item in events)
        self.time_regions = set()
        self.regions = {}
        self.region_dungeon = {}
        extra_exit_requirements = extra_exit_requirements or {}
        extra_location_requirements = extra_location_requirements or {}
        self.extra_exit_requirements = extra_exit_requirements
        self.extra_location_requirements = extra_location_requirements
        self.location_region = {}
        self.location_rules = {}
        self.virtual = {}
        # item -> (item it stands for, count): a key ring counts as all its keys.
        self.bundles = {}
        self.referenced = set()
        self._region = None  # region being compiled (for here())
        for region in data.regions:
            name = region['region_name']
            self.region_dungeon[name] = region.get('dungeon')
            if region.get('time_passes'):
                self.time_regions.add(name)
        moved = defaultdict(dict)
        for region in data.regions:
            for location, rule in region.get('locations', {}).items():
                source, target = REMAKE_LOCATION_REGIONS.get(location, (None, None))
                if source == region['region_name']:
                    moved[target][location] = rule
        for region in data.regions:
            name = region['region_name']
            self._region = name
            compiled = {'exits': [], 'locations': [], 'events': []}
            for target, rule in region.get('exits', {}).items():
                requirement = extra_exit_requirements.get((name, target))
                compiled['exits'].append((target, self.compile(rule, requirement)))
            own = {l: r for l, r in region.get('locations', {}).items()
                   if REMAKE_LOCATION_REGIONS.get(l, (None,))[0] != name}
            for location, rule in dict(own, **moved.get(name, {})).items():
                rule = REMAKE_LOCATION_RULES.get(location, rule)
                extra_rule = shop_rule(data.vanilla_item(location))
                if extra_rule:
                    rule = f'({rule}) and ({extra_rule})'
                compiled_rule = self.compile(rule, extra_location_requirements.get(location))
                compiled['locations'].append((location, compiled_rule))
                self.location_region.setdefault(location, name)
                self.location_rules.setdefault(location, []).append((name, compiled_rule))
            for event, rule in region.get('events', {}).items():
                compiled['events'].append((event, self.compile(rule)))
            self.regions[name] = compiled
        self._region = None
        missing = {t for r in self.regions.values() for t, _ in r['exits']} - set(self.regions)
        if missing:
            raise ValueError('Unknown AP regions: ' + ', '.join(sorted(missing)))

    # ------------------------------------------------------------------ rules
    @staticmethod
    def _parse(text):
        return ast.parse(' '.join(text.split()), mode='eval').body

    def _setting(self, name):
        return name in self.settings

    def _substitute(self, node, env):
        class Sub(ast.NodeTransformer):
            def visit_Name(inner, n):
                return copy.deepcopy(env[n.id]) if n.id in env else n
        node = Sub().visit(copy.deepcopy(node))

        logic = self

        class Fold(ast.NodeTransformer):
            def visit_Compare(inner, n):
                inner.generic_visit(n)
                if (len(n.ops) == 1 and isinstance(n.left, ast.Name) and isinstance(n.comparators[0], ast.Name)
                        and not logic._setting(n.left.id) and not logic._setting(n.comparators[0].id)
                        and isinstance(n.ops[0], (ast.Eq, ast.NotEq))):
                    same = n.left.id == n.comparators[0].id
                    return ast.Constant(same if isinstance(n.ops[0], ast.Eq) else not same)
                return n
        return Fold().visit(node)

    def _expand(self, node, depth=0):
        if depth > 60:
            raise ValueError('Rule expansion too deep.')
        if isinstance(node, ast.BoolOp):
            node.values = [self._expand(v, depth) for v in node.values]
            return node
        if isinstance(node, ast.UnaryOp):
            node.operand = self._expand(node.operand, depth)
            return node
        if isinstance(node, ast.Constant):
            return node
        if isinstance(node, ast.Name):
            if node.id in self.helpers and not self.helpers[node.id][0]:
                key = ('alias', node.id)
                if key not in self._cache:
                    self._cache[key] = self._expand(copy.deepcopy(self.helpers[node.id][1]), depth + 1)
                return copy.deepcopy(self._cache[key])
            if node.id in self.settings:
                return ast.Constant(self.settings[node.id])
            if node.id.startswith('logic_'):
                # Tricks: AP glitchless default is an empty logic_tricks list.
                return ast.Constant(node.id in self.settings.get('logic_tricks', ()))
            if node.id in ('True', 'False'):
                return ast.Constant(node.id == 'True')
            return node
        if isinstance(node, ast.Tuple):
            item, amount = node.elts
            amount = self._expand(amount, depth)
            if isinstance(item, ast.Name) and item.id in self.helpers and not self.helpers[item.id][0]:
                body = self.helpers[item.id][1]
                if isinstance(body, ast.Name):
                    item = body
            return ast.Tuple([item, amount], ast.Load())
        if isinstance(node, ast.Subscript):
            value = self._expand(node.value, depth)
            key = node.slice
            if isinstance(value, ast.Constant) and isinstance(value.value, dict) and isinstance(key, ast.Name):
                return ast.Constant(value.value[key.id])
            raise ValueError('Unsupported rule indexing.')
        if isinstance(node, ast.Compare):
            left = self._expand(node.left, depth)
            right = [self._expand(c, depth) for c in node.comparators]
            if isinstance(left, ast.Constant) and len(right) == 1 and isinstance(right[0], ast.Constant):
                a, b, op = left.value, right[0].value, node.ops[0]
                result = {ast.Eq: lambda: a == b, ast.NotEq: lambda: a != b, ast.In: lambda: a in b,
                          ast.NotIn: lambda: a not in b, ast.Lt: lambda: a < b, ast.Gt: lambda: a > b,
                          ast.LtE: lambda: a <= b, ast.GtE: lambda: a >= b}[type(op)]()
                return ast.Constant(bool(result))
            raise ValueError('Unresolved rule comparison: ' + ast.unparse(node))
        if isinstance(node, ast.Call):
            name = node.func.id
            if name == 'here':
                # OoTR: here(X) = X checked in this region by either age. Only the
                # bean case is opened to both ages (the child plants, the adult
                # rides): whether other changes (broken rocks…) persist across
                # ages is not proven in the remake, so they stay at the current age.
                if self._region and 'can_plant_bean' in ast.unparse(node.args[0]):
                    return ast.Call(ast.Name('at', ast.Load()),
                                    [ast.Constant(self._region), self._expand(node.args[0], depth)], [])
                return self._expand(node.args[0], depth)
            if name == 'at':
                node.args = [node.args[0], self._expand(node.args[1], depth)]
                return node
            if name.startswith('_oot_has_'):
                node.args = [self._expand(a, depth) for a in node.args]
                return node
            if name == 'region_has_shortcuts':
                return ast.Constant(False)
            if name in ('at_night',):
                return ast.Name(name, ast.Load())
            if name in self.helpers:
                params, body = self.helpers[name]
                if len(params) != len(node.args):
                    raise ValueError('Invalid rule call: ' + name)
                key = ('call', name, tuple(ast.dump(arg) for arg in node.args))
                if key not in self._cache:
                    self._cache[key] = self._expand(self._substitute(body, dict(zip(params, node.args))), depth + 1)
                return copy.deepcopy(self._cache[key])
            raise ValueError('Unknown rule function: ' + name)
        raise ValueError('Unsupported rule element: ' + type(node).__name__)

    def _item(self, name):
        if name in self.names:
            self.referenced.add(self.names[name])
            return self.names[name]
        raise ValueError('Unknown rule item or event: ' + name)

    def _code(self, node):
        if isinstance(node, ast.BoolOp):
            joiner = ' and ' if isinstance(node.op, ast.And) else ' or '
            return '(' + joiner.join(self._code(v) for v in node.values) + ')'
        if isinstance(node, ast.UnaryOp):
            return '(not ' + self._code(node.operand) + ')'
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return repr(node.value)
            if isinstance(node.value, str):
                self.referenced.add(node.value)
                return f'c.get({node.value!r},0)>=1'
            raise ValueError('Unexpected rule constant: ' + repr(node.value))
        if isinstance(node, ast.Name):
            special = {
                'has_bottle': 's.has_bottle()',
                'at_night': "(s.tod[a] or (c.get('Ocarina',0)>=1 and c.get('Suns Song',0)>=1))",
                'at_day': "(s.tod[a] or (c.get('Ocarina',0)>=1 and c.get('Suns Song',0)>=1))",
                'at_dampe_time': "(s.tod[a] or (c.get('Ocarina',0)>=1 and c.get('Suns Song',0)>=1))",
                '_oot_has_beans': "(c.get('Magic Bean',0)>=1 or c.get('Magic Bean Pack',0)>=1 or c.get('Buy Magic Bean',0)>=1)",
                'current_spot_child_access': "(a=='child')",
                'current_spot_adult_access': "(a=='adult')",
                'current_spot_starting_age_access': f"(a=={self.settings['starting_age']!r})",
            }
            if node.id in special:
                if node.id.startswith('at_'):
                    self.referenced.update(('Ocarina', 'Suns Song'))
                if node.id == 'has_bottle':
                    self.referenced.update(self.bottles)
                if node.id == '_oot_has_beans':
                    self.referenced.update(('Magic Bean', 'Magic Bean Pack', 'Buy Magic Bean'))
                return special[node.id]
            return f'c.get({self._item(node.id)!r},0)>=1'
        if isinstance(node, ast.Tuple):
            item, amount = node.elts
            if not isinstance(amount, ast.Constant):
                raise ValueError('Non-constant rule quantity.')
            name = item.value if isinstance(item, ast.Constant) else self._item(item.id)
            self.referenced.add(name)
            return f'c.get({name!r},0)>={int(amount.value)}'
        if isinstance(node, ast.Call):
            name = node.func.id
            if name == 'at':
                region = node.args[0].value
                if region not in {r['region_name'] for r in self.data.regions}:
                    raise ValueError('Unknown at() region: ' + region)
                return f's.at({region!r},lambda s,c,a:{self._code(node.args[1])})'
            amount = node.args[0].value if node.args else 0
            self.referenced.update({'_oot_has_stones': STONES, '_oot_has_medallions': MEDALLIONS,
                                    '_oot_has_dungeon_rewards': STONES + MEDALLIONS,
                                    '_oot_has_hearts': ('Heart Container', 'Piece of Heart',
                                                        'Piece of Heart (Treasure Chest Game)')}.get(name, ()))
            if name == '_oot_has_stones':
                return f's.reward_count({STONES!r})>={amount}'
            if name == '_oot_has_medallions':
                return f's.reward_count({MEDALLIONS!r})>={amount}'
            if name == '_oot_has_dungeon_rewards':
                return f's.reward_count({STONES + MEDALLIONS!r})>={amount}'
            if name == '_oot_has_hearts':
                return f's.hearts()>={amount}'
            if name == '_oot_has_beans':
                return "(c.get('Magic Bean',0)>=1 or c.get('Magic Bean Pack',0)>=1 or c.get('Buy Magic Bean',0)>=1)"
        if isinstance(node, ast.Name) and node.id == '_oot_has_beans':
            return "(c.get('Magic Bean',0)>=1 or c.get('Magic Bean Pack',0)>=1 or c.get('Buy Magic Bean',0)>=1)"
        raise ValueError('Cannot generate rule: ' + ast.unparse(node))

    def compile(self, rule, extra_items=None):
        try:
            code = self._code(self._expand(self._parse(rule)))
        except ValueError as error:
            raise ValueError(f'{error} — rule: {" ".join(rule.split())[:200]}') from None
        if extra_items:
            self.referenced.update(extra_items)
            code = '(' + code + ' and ' + ' and '.join(f'c.get({i!r},0)>=1' for i in sorted(extra_items)) + ')'
        return eval('lambda s,c,a:' + code, {'__builtins__': {}})

    # ----------------------------------------------------------------- search
    def new_state(self, counts=None):
        counts = dict(counts or {})
        for item, (key, number) in self.bundles.items():
            if counts.get(item):
                counts[key] = counts.get(key, 0) + number * counts[item]
        state = _SearchState(self, counts)
        return state

    def sweep(self, placements, state=None, record_spheres=False):
        """Collect everything reachable. ``placements`` maps location → item.

        Locations absent from ``placements`` hold nothing. Returns
        ``(state, collected, spheres)``.
        """
        state = state or self.new_state()
        collected = set()
        spheres = []
        while True:
            self._expand_regions(state)
            new = []
            for region_name in sorted(state.reached['child'] | state.reached['adult']):
                for location, rule in self.regions[region_name]['locations']:
                    if location in collected or location not in placements:
                        continue
                    for age in ('child', 'adult'):
                        if region_name in state.reached[age] and rule(state, state.counts, age):
                            new.append(location)
                            break
            # The state does not change during this pass: memoize member access
            # (area-wide virtual locations share hundreds of AP members).
            access = {}

            def reachable(member):
                if member not in access:
                    access[member] = self.accessible(state, member)
                return access[member]

            for name, members in self.virtual.items():
                if name in collected or name not in placements:
                    continue
                if all(reachable(member) for member in members):
                    new.append(name)
            new = sorted(set(new))
            if not new:
                break
            spheres.append(new)
            for location in new:
                collected.add(location)
                item = placements[location]
                if item:
                    state.add(item)
            if not record_spheres:
                # Faster when spheres are not needed: keep collecting greedily.
                pass
        return state, collected, spheres

    def _expand_regions(self, state):
        changed = True
        if not state.reached['child'] and not state.reached['adult']:
            state.reached['child'].add('Root')
            state.reached['adult'].add('Root')
        while changed:
            changed = False
            for age in ('child', 'adult'):
                reached = state.reached[age]
                frontier = list(reached)
                while frontier:
                    region_name = frontier.pop()
                    if region_name in self.time_regions:
                        state.tod[age] = True
                    for target, rule in self.regions[region_name]['exits']:
                        if target not in reached and rule(state, state.counts, age):
                            reached.add(target)
                            frontier.append(target)
                            changed = True
            for age in ('child', 'adult'):
                for region_name in list(state.reached[age]):
                    for event, rule in self.regions[region_name]['events']:
                        if state.counts.get(event, 0) < 1 and rule(state, state.counts, age):
                            state.counts[event] = 1
                            changed = True
            if changed:
                continue
            # Exits blocked earlier may now pass thanks to new events or tod.
            for age in ('child', 'adult'):
                for region_name in list(state.reached[age]):
                    for target, rule in self.regions[region_name]['exits']:
                        if target not in state.reached[age] and rule(state, state.counts, age):
                            state.reached[age].add(target)
                            changed = True

    def accessible(self, state, location):
        if location.startswith('Souls|'):
            return all(state.counts.get(item, 0) >= 1 for item in location.split('|')[1:])
        for region_name, rule in self.location_rules.get(location, ()):
            for age in ('child', 'adult'):
                if region_name in state.reached[age] and rule(state, state.counts, age):
                    return True
        return False

    def location_names(self):
        return set(self.location_region)


class _SearchState(State):
    __slots__ = ('logic',)

    def __init__(self, logic, counts=None):
        super().__init__(counts)
        self.logic = logic

    def add(self, item, count=1):
        super().add(item, count)
        bundle = self.logic.bundles.get(item)
        if bundle:   # key ring: every small key of its dungeon at once
            super().add(bundle[0], bundle[1] * count)

    def has_bottle(self):
        return any(self.counts.get(b, 0) for b in self.logic.bottles)

    def reward_count(self, names):
        return sum(1 for n in names if self.counts.get(n, 0))

    def hearts(self):
        pieces = self.counts.get('Piece of Heart', 0) + self.counts.get('Piece of Heart (Treasure Chest Game)', 0)
        return 3 + self.counts.get('Heart Container', 0) + pieces // 4

    def at(self, region, rule):
        for age in ('child', 'adult'):
            if region in self.reached[age] and rule(self, self.counts, age):
                return True
        return False

    def copy(self):
        other = _SearchState(self.logic, self.counts)
        other.reached = {k: set(v) for k, v in self.reached.items()}
        other.tod = dict(self.tod)
        return other


def vanilla_placements(data, logic, locations=None):
    """Vanilla items for every AP location present in the compiled regions."""
    result = {}
    for location in locations if locations is not None else logic.location_names():
        item = data.vanilla_item(location)
        kind = data.location_type(location)
        if kind in ('HintStone', 'Hint') or item is None:
            result[location] = None
            continue
        result[location] = item
    return result
