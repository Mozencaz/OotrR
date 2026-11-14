"""Save-driven tracker: observed collection, inventory and spoiler-safe availability."""
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import threading

from oot_rando.game.tracking_metadata import inventory_rules
from oot_rando.logic.rules import split_age_member
from oot_rando.randomizer.randomizer_services import ManualTracker, read_artifact
from oot_rando.tracker.save_reader import load_snapshot
from oot_rando.paths import state_dir


NAND_SAVE = ('nand', 'user', 'save')


def emulator_save_root(path):
    """NAND save folder of a portable emulator whose mods folder holds ``path``, or None.

    Portable yuzu-family emulators (Ryuchii, Eden...) keep ``load/<title>`` (mods) and
    ``nand/user/save`` side by side in their ``user`` folder."""
    for folder in (Path(path), *Path(path).parents):
        if folder.name.lower() == 'load' and (folder.parent / 'nand').is_dir():
            return folder.parent.joinpath(*NAND_SAVE)
    return None


def save_roots(hookshot_root=None, mods=None):
    """Save folders of Hookshot, of a portable emulator holding ``mods`` (its mods folder or
    a seed in it), and of the Eden emulator in %APPDATA% (NAND user saves)."""
    roots = []
    if hookshot_root:
        root = Path(hookshot_root)
        if root.name.lower() == 'mods':
            root = root.parent
        roots.append(root / 'user' / 'save')
    portable = emulator_save_root(mods) if mods else None
    if portable:
        roots.append(portable)
    appdata = os.environ.get('APPDATA')
    if appdata:
        roots.append(Path(appdata) / 'eden' / 'nand' / 'user' / 'save')
    unique = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def find_save_slots(hookshot_root=None, title=None, mods=None):
    """Every slot_*/progress.sav below the known save folders (any depth)."""
    found = {}
    for save in save_roots(hookshot_root, mods):
        if not save.is_dir():
            continue
        # The emulator NAND holds every game: keep this title's folders only.
        emulator = tuple(part.lower() for part in save.parts[-3:]) == NAND_SAVE
        for path in save.rglob('progress.sav'):
            if not path.parent.name.startswith('slot_'):
                continue
            if emulator and title and title.upper() not in (part.upper() for part in path.parts):
                continue
            found.setdefault(path.resolve(), path)   # one entry when two roots reach the same save
    return sorted(found.values())


def newest_save(hookshot_root=None, title=None, mods=None):
    """The progress.sav written most recently across every save and slot."""
    best, best_time = None, None
    for path in find_save_slots(hookshot_root, title, mods):
        try:
            written = path.stat().st_mtime
        except OSError:
            continue
        if best_time is None or written > best_time:
            best, best_time = path, written
    return best


def soul_zones(metadata, counts):
    """Souls of a seed by zone: ``[(zone label, [(soul name, owned)])]``, in map order.

    A family soul is listed in every zone where its enemies appear. Seeds tracked
    before the zones were recorded show their souls under a single group.
    """
    from oot_rando.game.remake_world import ZONE_LABELS
    from oot_rando.patching.soul_adapter import soul_name
    metadata = metadata or {}
    souls = metadata.get('souls')
    if souls is None:
        tracked = sorted({rule['item'] for rule in metadata.get('inventory', []) if rule['item'].startswith('Soul (')})
        souls = [{'item': item, 'zones': ['All zones']} for item in tracked]
    order = list(ZONE_LABELS)
    zones = {}
    for soul in souls:
        for zone in soul['zones'] or ['Other']:
            zones.setdefault(zone, []).append((soul_name(soul['item'], False), bool(counts.get(soul['item']))))
    return [(ZONE_LABELS.get(zone, zone), sorted(entries))
            for zone, entries in sorted(zones.items(), key=lambda z: (order.index(z[0]) if z[0] in order else -1, z[0]))]


class TrackerSession:
    """A session observes one selected save; rollbacks replace its automatic state."""
    def __init__(self, directory, slot, save_path='', live=None):
        self.directory = Path(directory)
        self.live, self.live_status = live, ''   # live_memory.LiveGameData, optional
        self.live_bool64 = False
        self.manifest, catalogue = read_artifact(directory)
        self.seed_id, self.slot = self.manifest['seed_id'], slot
        self.checks = catalogue['checks']
        self.save_path = str(save_path)
        self.manual = ManualTracker(state_dir() / 'tracker',
                                    self.seed_id, slot, [c['id'] for c in self.checks])
        self.metadata = None
        if self.manifest.get('tracking'):
            self.metadata = json.loads((self.directory / 'tracking.json').read_text(encoding='utf-8'))
            self.metadata['_known64'] = set(self.metadata.get('known_bool64', []))
        self._lock = threading.RLock()
        self._automatic, self._access = set(), {}
        self._inventory = (Counter(), set())
        from oot_rando.patching.key_adapter import dungeon_keys
        self._keys = dungeon_keys((self.metadata or {}).get('keys'), None)   # 0 found until a save is read
        self._fingerprint = None
        self._logic, self._logic_error = None, ''
        self._observed, self._goal = False, False
        self._source_path = ''
        self._good_summary = None
        self._summary = {'status': 'Choose a save to enable automatic tracking.',
                         'updated_at': '', 'automatic': 0, 'available': 0, 'blocked': 0,
                         'unknown': len(self.checks)}

    @property
    def goal_reached(self):
        """Archipelago goal flag seen true (save or running game) for this save."""
        with self._lock:
            return self._goal

    @property
    def completed(self):
        with self._lock:
            return self._automatic | self.manual.completed

    def set_completed(self, ident, value):
        with self._lock:
            self.manual.set_completed(ident, value)

    def check_state(self, ident):
        with self._lock:
            automatic = ident in self._automatic
            completed = automatic or ident in self.manual.completed
            row = (self.metadata or {}).get('checks', {}).get(ident, {})
            # A manually checked row is not evidence that the planned reward was obtained.
            reward = row.get('reward', '') if automatic else ''
            return {'completed': completed, 'access': self._access.get(ident, 'unknown'),
                    'reward': reward, 'source': 'save' if automatic else (
                        'manual' if completed else ''), 'observed': automatic}

    def _get_logic(self):
        if self._logic is not None or self._logic_error:
            return self._logic
        graph = self.metadata.get('logic')
        if not graph:
            return None
        try:
            from oot_rando.logic.rules import Logic
            from oot_rando.logic.world import World
            data = World()
            if data.fingerprint() != self.metadata.get('logic_world_sha256'):
                raise ValueError('Seed generated with another logic version: regenerate it '
                                 'to filter accessibility.')
            exits = {(a, b): set(items) for a, b, items in graph['exits']}
            self._logic = Logic(data, graph['settings'], exits, graph['locations'])
            self._logic.virtual = graph['virtual']
        except (OSError, ValueError, KeyError, ImportError) as error:
            self._logic_error = str(error)
        return self._logic

    def inventory(self):
        """Observed inventory: ({item: level}, items readable in the save, items the seed tracks)."""
        with self._lock:
            counts, known = self._inventory
            tracked = {rule['item'] for rule in inventory_rules((self.metadata or {}).get('inventory'))}
            return dict(counts), set(known), tracked

    def keys(self):
        """``[(dungeon, (found, total) or None, boss key or None)]`` at the latest read."""
        with self._lock:
            return list(self._keys)

    def souls(self):
        """Souls of the seed by zone, with whether each one is owned (see :func:`soul_zones`)."""
        counts, _, _ = self.inventory()
        return soul_zones(self.metadata, counts)

    @staticmethod
    def observed_inventory(snapshot, metadata):
        counts, known = Counter(), set()
        for rule in inventory_rules(metadata.get('inventory')):
            key, item = int(rule['hash']), rule['item']
            if key in snapshot['bool']:
                known.add(item)
                if snapshot['bool'][key]:
                    counts[item] = max(counts[item], rule.get('count', 1))
        return counts, known

    def _availability(self, snapshot, metadata):
        logic = self._get_logic()
        if logic is None:
            return {}
        counts, known = self.observed_inventory(snapshot, metadata)
        # Observed, completed sources can confirm cumulative counts (e.g. keys already spent).
        # They must never add rewards from unchecked locations.
        observed_counts = Counter()
        for gid, row in metadata['checks'].items():
            ref = row.get('collection')
            if ref and self._collected(ref, snapshot, metadata) is True and row.get('item'):
                observed_counts[row['item']] += 1
        for item, amount in observed_counts.items():
            if item.startswith(('Small Key (', 'Boss Key (')) or item in (
                    'Gold Skulltula Token', 'Heart Container', 'Piece of Heart'):
                counts[item] = max(counts[item], amount)
        placements = {location: None for location in logic.location_names()}
        placements.update({location: None for location in logic.virtual})
        state, available, _ = logic.sweep(placements, logic.new_state(dict(counts)))
        # Missing counters/flags are uncertainty, not proof that a check is blocked.
        optimistic = dict(counts)
        for item in logic.referenced - known:
            optimistic[item] = max(99, optimistic.get(item, 0))
        best, possible, _ = logic.sweep(placements, logic.new_state(optimistic))
        result = {}
        known_locations = set(placements)
        for gid, row in metadata['checks'].items():
            location = self.logic_location(gid, row)
            if location not in known_locations:
                result[gid] = 'unknown'
            elif location in available:
                result[gid] = 'available'
            elif row.get('logic') == 'area':
                # An area-wide source is proven only when its whole area is. When
                # part of the area is reachable now, the source may be: "partial".
                if self._partly_reachable(logic, state, location):
                    result[gid] = 'partial'
                elif not self._partly_reachable(logic, best, location):
                    result[gid] = 'blocked'
                else:
                    result[gid] = 'unknown'
            elif location not in possible:
                result[gid] = 'blocked'
            else:
                result[gid] = 'unknown'
        return result

    @staticmethod
    def _partly_reachable(logic, state, location):
        members = logic.virtual.get(location, [])
        guards = [m for m in members if m.startswith('Souls|')]
        others = [m for m in members if not m.startswith('Souls|')]
        # A source of one age's maps: only the part of the area done at that age counts.
        aged = [m for m in others if split_age_member(m)[0]]
        return (all(logic.accessible(state, g) for g in guards)
                and any(logic.accessible(state, m) for m in aged or others))

    @staticmethod
    def logic_location(gid, row):
        """Logic node answering 'can I do this check?'.

        Remake sources use their virtual location (exact, group or area-wide
        prudent conjunction); untouched AP checks use their AP name directly.
        """
        if gid.startswith('ap#'):
            return gid[3:]
        if row.get('logic') in ('exact', 'group', 'area'):
            return row.get('location')
        return None

    @staticmethod
    def _collected(ref, snapshot, metadata):
        key = int(ref['hash'])
        if ref['type'] == 'bool64':
            if not snapshot.get('bool64_complete') or str(key) not in metadata.get('_known64', metadata.get('known_bool64', [])):
                return None
            return bool(snapshot['bool64'].get(key, False))
        if ref['type'] == 'bool':
            return snapshot['bool'].get(key)
        return None

    def refresh(self):
        """Called off the Tk thread. Invalid reads retain the last good display."""
        path = str(self.save_path).strip()
        if not self.metadata:
            return self._failure('This old seed has no tracking data. Generate a new seed.')
        if not path:
            return self._failure('Choose the progress.sav file of the game to track.')
        try:
            snapshot = load_snapshot(path)
            marker = self.metadata.get('seed_marker')
            if not marker or snapshot['bool'].get(int(marker)) is not True:
                return self._failure('This save is not linked to this seed. Start a new game with this seed.', reset=True)
            live_digest, self.live_status = None, ''
            if self.live is not None:
                live_digest = self._merge_live(snapshot, int(marker))
            token = (str(Path(path).resolve()), snapshot['sha256'], live_digest)
            if token == self._fingerprint:
                if self._good_summary:
                    self._summary = dict(self._good_summary)
                return dict(self._summary)
            automatic = {gid for gid, row in self.metadata['checks'].items()
                         if row.get('collection') and self._collected(row['collection'], snapshot, self.metadata) is True}
            goal_key = self.metadata.get('goal_marker')
            goal = bool(goal_key) and snapshot['bool'].get(int(goal_key)) is True
            access = self._availability(snapshot, self.metadata)
            inventory = self.observed_inventory(snapshot, self.metadata)
            from oot_rando.patching.key_adapter import dungeon_keys
            keys = dungeon_keys(self.metadata.get('keys'), snapshot)
            stamp = datetime.fromtimestamp(snapshot['mtime_ns'] / 1e9).strftime('%H:%M:%S')
            status = 'Synced with the latest save'
            if live_digest:
                stamp = datetime.now().strftime('%H:%M:%S')
                status = 'Real time (game memory)' + ('' if self.live_bool64 else ' • chests at the latest save')
            elif self.live_status:
                status += ' • real time unavailable: ' + self.live_status
            if self._logic_error:
                status += ' • accessibility unavailable: ' + self._logic_error
            elif not self.metadata.get('logic'):
                status += ' • accessibility not available for this seed'
            with self._lock:
                self._automatic, self._access = automatic, access
                self._goal = self._goal or goal
                self._inventory = inventory
                self._keys = keys
                self._fingerprint, self._observed, self._source_path = token, True, path
                self._summary = {'status': status, 'updated_at': stamp, 'automatic': len(automatic),
                                 'available': sum(v == 'available' for v in access.values()),
                                 'blocked': sum(v == 'blocked' for v in access.values()),
                                 'unknown': sum(access.get(c['id'], 'unknown') == 'unknown' for c in self.checks)}
                self._good_summary = dict(self._summary)
                return dict(self._summary)
        except (OSError, ValueError, KeyError) as error:
            return self._failure('Lecture indisponible : ' + str(error))

    def _merge_live(self, snapshot, marker):
        """Overlay the running game's bools on the save's; None when not usable.

        Live bools are used only when the running game also carries this seed's marker
        (title screen, another seed or a game not started: save only). The live Bool64bitKey
        flags replace the save's when they could be read; otherwise they stay from the save.
        """
        from oot_rando.tracker.live_memory import LiveUnavailable
        try:
            live = self.live.snapshot()
        except LiveUnavailable as error:
            self.live_status = str(error)
            return None
        if live['bool'].get(marker) is not True:
            self.live_status = 'the running game is not this seed\'s'
            return None
        snapshot['bool'] = {**snapshot['bool'], **live['bool']}
        self.live_bool64 = live.get('bool64_complete', False)
        if self.live_bool64:
            snapshot['bool64'] = live['bool64']
        return live['sha256']

    def _failure(self, message, reset=False):
        with self._lock:
            # A different slot must never inherit collection from the previous one.
            if reset or (self._source_path and str(self.save_path).strip() != self._source_path):
                self._automatic, self._access = set(), {}
                self._inventory = (Counter(), set())
                self._goal = False
                self._fingerprint, self._observed, self._source_path = None, False, ''
                self._good_summary = None
                self._summary.update(updated_at='', automatic=0, available=0, blocked=0, unknown=len(self.checks))
            self._summary['status'] = message + (' • last state kept' if self._observed else '')
            return dict(self._summary)
