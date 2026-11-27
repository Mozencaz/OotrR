"""Save-driven tracker: observed collection, inventory and spoiler-safe availability."""
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import threading

from oot_rando.logic.rules import split_age_member
from oot_rando.randomizer.artifact import read_artifact
from oot_rando.tracker.manual_tracker import ManualTracker
from oot_rando.formats.save_file import load_snapshot
from oot_rando.paths import state_dir
from oot_rando.pc_port import KNOWN_EXES, port_exe
from oot_rando.game.remake_world import ZONE_LABELS
from oot_rando.patching.key_adapter import dungeon_keys
from oot_rando.patching.soul_adapter import soul_name


NAND_SAVE = ('nand', 'user', 'save')


def emulator_save_root(path):
    """NAND save folder of a portable emulator whose mods folder holds ``path``, or None.

    Portable yuzu-family emulators (Ryuchii, Eden...) keep ``load/<title>`` (mods) and
    ``nand/user/save`` side by side in their ``user`` folder."""
    for folder in (Path(path), *Path(path).parents):
        if folder.name.lower() == 'load' and (folder.parent / 'nand').is_dir():
            return folder.parent.joinpath(*NAND_SAVE)
    return None


def port_appdata_names(root):
    """Names of the %APPDATA% folders a PC port may keep its saves in: its exe's, then the known ports'.

    Both spellings are kept (``longshot`` from the exe, ``Longshot`` as the port writes it): they
    are one folder on Windows (find_save_slots merges them) but two on case-sensitive systems."""
    exe = port_exe(root) if root.is_dir() else None
    names = [exe.stem] if exe else []
    for known in KNOWN_EXES:
        name = Path(known).stem.capitalize()
        if name not in names:
            names.append(name)
    return names


def linux_data_home():
    """``$XDG_DATA_HOME``, else ``~/.local/share`` (None on Windows)."""
    if os.name == 'nt':
        return None
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')


def save_roots(hookshot_root=None, mods=None):
    """Save folders of a PC port (``<game>/user/save``, or ``%APPDATA%/<Port>/save`` where Longshot
    moves them on import, renaming the old folder ``save.moved-<date>``; Longshot's Linux build:
    ``~/.local/share/longshot/save``), of a portable emulator holding ``mods`` (its mods folder or
    a seed in it), and of Eden in %APPDATA% (NAND user saves)."""
    roots = []
    appdata = os.environ.get('APPDATA')
    if hookshot_root:
        root = Path(hookshot_root)
        if root.name.lower() == 'mods':
            root = root.parent
        roots.append(root / 'user' / 'save')
        if appdata:
            roots.extend(Path(appdata) / name / 'save' for name in port_appdata_names(root))
        data = linux_data_home()
        if data:
            names = dict.fromkeys(name.lower() for name in port_appdata_names(root))
            roots.extend(data / name / 'save' for name in names)

    portable = emulator_save_root(mods) if mods else None
    if portable:
        roots.append(portable)
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


def default_port_save_roots():
    """Standard OS save folders for known PC ports when no port root is specified."""
    roots = []
    appdata = os.environ.get('APPDATA')
    names = port_appdata_names(Path("."))
    if appdata:
        roots.extend(Path(appdata) / name / 'save' for name in names)
    data = linux_data_home()
    if data:
        for name in dict.fromkeys(n.lower() for n in names):
            roots.append(data / name / 'save')
    return roots

def resolve_party_save_root(recorded_saves, mods=None, fallback_saves=None):
    """Resolve a party save folder across PCs, usernames, and moved/extracted builds."""
    candidates = []
    if recorded_saves:
        rec = Path(recorded_saves)
        candidates.append(rec)
        if rec.name and not rec.name.startswith("slot_"):
            for root in save_roots(mods, mods):
                if root.is_dir():
                    account_cand = root / rec.name
                    if account_cand.is_dir() and any(account_cand.glob("slot_*/progress.sav")):
                        candidates.append(account_cand)
    search_roots = list(save_roots(mods, mods))
    for r in default_port_save_roots():
        if r not in search_roots:
            search_roots.append(r)
    for root in search_roots:
        if not root.is_dir():
            continue
        if any(root.glob("slot_*/progress.sav")):
            candidates.append(root)
        try:
            for child in sorted(root.iterdir()):
                if child.is_dir() and any(child.glob("slot_*/progress.sav")):
                    candidates.append(child)
        except OSError:
            pass
    if fallback_saves:
        candidates.append(Path(fallback_saves))
    for cand in candidates:
        if cand.is_dir() and any(cand.rglob("progress.sav")):
            return cand
    for cand in candidates:
        if cand.is_dir():
            return cand
    return Path(recorded_saves) if recorded_saves else Path(fallback_saves or ".")


def soul_zones(metadata, counts):
    """Souls of a seed by zone: ``[(zone label, [(soul name, owned)])]``, in map order.

    A family soul is listed in every zone where its enemies appear. Seeds tracked
    before the zones were recorded show their souls under a single group.
    """
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
    def __init__(self, directory, slot, save_path='', live=None, manual_directory=None):
        self.directory = Path(directory)
        self.live, self.live_status = live, ''   # live_memory.LiveGameData, optional
        self.live_bool64 = False
        self.manifest, catalogue = read_artifact(directory)
        self.seed_id, self.slot = self.manifest['seed_id'], slot
        self.checks = catalogue['checks']
        self.save_path = str(save_path)
        self.manual = ManualTracker(manual_directory if manual_directory is not None else state_dir() / 'tracker',
                                    self.seed_id, slot, [c['id'] for c in self.checks])
        self.metadata = None
        if self.manifest.get('tracking'):
            self.metadata = json.loads((self.directory / 'tracking.json').read_text(encoding='utf-8'))
            self.metadata['_known64'] = set(self.metadata.get('known_bool64', []))
        self._lock = threading.RLock()
        self._automatic, self._access = set(), {}
        self._soul_reasons = {}
        self._inventory = (Counter(), set())
        self._keys = dungeon_keys((self.metadata or {}).get('keys'), None)   # 0 found until a save is read
        self._fingerprint = None
        self._logic, self._logic_error = None, ''
        self._observed, self._goal = False, False
        self._link = 'none'   # see ``link``
        self._source_path = ''
        self._good_summary = None
        self._summary = {'status': 'Choose a save to enable automatic tracking.',
                         'updated_at': '', 'automatic': 0, 'available': 0, 'blocked': 0,
                         'unknown': len(self.checks)}

    @property
    def link(self):
        """How the save relates to the seed at the latest read: 'linked' (a save of this seed),
        'other' (a save of another seed or of the vanilla game) or 'none' (no save read yet)."""
        with self._lock:
            return self._link

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
            # No saved flag to read (an NPC gift, a shop refill, a source left in place
            # that keeps no flag): only a manual tick completes the row.
            untracked = self.metadata is not None and not row.get('collection')
            return {'completed': completed, 'access': self._access.get(ident, 'unknown'),
                    'reward': reward, 'source': 'save' if automatic else (
                        'manual' if completed else ''), 'observed': automatic,
                    'untracked': untracked, 'missing_souls': tuple(self._soul_reasons.get(ident, ()))}

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
            tracked = {rule['item'] for rule in (self.metadata or {}).get('inventory', [])}
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
        for rule in metadata.get('inventory', []):
            key, item = int(rule['hash']), rule['item']
            if key in snapshot['bool']:
                known.add(item)
                if snapshot['bool'][key]:
                    counts[item] = max(counts[item], rule.get('count', 1))
        return counts, known

    def _availability(self, snapshot, metadata):
        self._soul_reasons = {}
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
        self._soul_reasons = self._missing_souls(logic, placements, counts, known, metadata, result)
        return result

    def _missing_souls(self, logic, placements, counts, known, metadata, access):
        """Check id → souls (items) still missing for a check the souls alone would open.

        Only checks reachable with the current inventory plus every missing soul are
        explained; a soul is named when that check stays closed without it. Cached by
        inventory: the result only depends on the counts.
        """
        souls = sorted({s['item'] for s in metadata.get('souls') or []}
                       | {i for i in logic.referenced if i.startswith('Soul (')})
        missing = [s for s in souls if not counts.get(s) and (s in known or not known)]
        if not missing:
            return {}
        key = (tuple(sorted(counts.items())), tuple(missing))
        cached = getattr(self, '_soul_cache', None)
        if cached and cached[0] == key:
            return cached[1]
        candidates = {gid: self.logic_location(gid, metadata['checks'][gid])
                      for gid, value in access.items() if value != 'available'}
        candidates = {gid: loc for gid, loc in candidates.items() if loc in placements}
        reasons = {}
        if candidates:
            def reachable(extra):
                with_souls = Counter(counts)
                with_souls.update({s: 1 for s in extra})
                return logic.sweep(placements, logic.new_state(dict(with_souls)))[1]
            opened = reachable(missing)
            candidates = {gid: loc for gid, loc in candidates.items() if loc in opened}
            for soul in missing if candidates else ():
                still = reachable([s for s in missing if s != soul])
                for gid, loc in candidates.items():
                    if loc not in still:
                        reasons.setdefault(gid, []).append(soul)
        self._soul_cache = (key, reasons)
        return reasons

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
            with self._lock:
                self._link = 'none'
            return self._failure('Choose the progress.sav file of the game to track.')
        try:
            snapshot = load_snapshot(path)
            marker = self.metadata.get('seed_marker')
            if not marker or snapshot['bool'].get(int(marker)) is not True:
                with self._lock:
                    self._link = 'other'
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
                self._link = 'linked'
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
                self._automatic, self._access, self._soul_reasons = set(), {}, {}
                self._inventory = (Counter(), set())
                self._goal = False
                self._fingerprint, self._observed, self._source_path = None, False, ''
                self._good_summary = None
                self._summary.update(updated_at='', automatic=0, available=0, blocked=0, unknown=len(self.checks))
            self._summary['status'] = message + (' • last state kept' if self._observed else '')
            return dict(self._summary)
