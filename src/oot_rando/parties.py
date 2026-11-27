"""Portable named games and recoverable seed/save installation transactions.

Only a game's account save directory and the randomizer's own mod are exchanged.
Other mods, NAND titles and emulator settings are never part of a transaction.
"""
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
from pathlib import Path
import os
import shutil
import stat
import subprocess
import threading
import uuid

from oot_rando.paths import app_dir
from oot_rando.pc_port import longshot_layout_root
from oot_rando.randomizer.artifact import read_artifact, is_randomizer_seed
from oot_rando.randomizer.mods_folder import validate_mod_directory
from oot_rando.randomizer.save_patch import GameRunning, running_game
from oot_rando.randomizer.mods_folder import conflicting_mods
from oot_rando.randomizer.mods_folder import qol_seed_warning


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2))
        handle.flush()
        # library.json is the commit point of every transaction: after a power cut it
        # must hold either the old or the new content, never an empty file.
        os.fsync(handle.fileno())
    temporary.replace(path)
    if os.name != 'nt':
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _plain_tree(path):
    """Do not follow symlinks/junctions while copying or exchanging user files."""
    path = Path(path)
    def linked(entry):
        try:
            attributes = getattr(entry.lstat(), 'st_file_attributes', 0)
            return entry.is_symlink() or bool(attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))
        except FileNotFoundError:
            return False
    for entry in (path, *path.parents):
        if linked(entry):
            raise ValueError('Linked folders cannot be used for parties: ' + str(entry))
    if path.exists():
        for entry in path.rglob('*'):
            if linked(entry):
                raise ValueError('Linked files cannot be used for parties: ' + str(entry))


def copy_verified(source, destination):
    from oot_rando.path_safety import fs_path, validate_file_path
    _plain_tree(source)
    shutil.copytree(fs_path(source), fs_path(destination))
    # Verify all files, including ancillary save files and AP delivery state.
    for original in Path(source).rglob("*"):
        if original.is_file():
            copied = Path(destination) / original.relative_to(source)
            validate_file_path(copied, label="Party file")
            with open(fs_path(original), "rb") as f_orig, open(fs_path(copied), "rb") as f_copy:
                if hashlib.sha256(f_orig.read()).digest() != hashlib.sha256(f_copy.read()).digest():
                    raise OSError("Copy verification failed: " + str(original))


def _hashes(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(directory).rglob('*') if p.is_file()}


def validate_save_root(path):
    """The directory directly containing slot_* (one account, one title)."""
    path = Path(path).absolute()
    _plain_tree(path)
    path = path.resolve()
    if path.exists():
        if not path.is_dir():
            raise ValueError('Choose the save account folder, not a file.')
        if any(p.is_dir() and not p.name.startswith('slot_') for p in path.iterdir()):
            raise ValueError('Choose the account folder directly containing slot_00, slot_01… '
                             'Do not choose the emulator NAND or the general save folder.')
    if path == path.parent or path.name.lower() in {'save', 'saves', 'nand', 'mods', 'load', 'user'}:
        raise ValueError('Choose a dedicated save account folder containing slot_* folders.')
    return path


def _operation(function):
    """Serialize writers, including recovery, across threads and application instances."""
    @wraps(function)
    def call(self, *args, **kwargs):
        with self._mutex:
            if self._lock_depth:
                return function(self, *args, **kwargs)
            with (self.root / '.lock').open('a+b') as handle:
                if handle.tell() == 0:
                    handle.write(b'0')
                    handle.flush()
                handle.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    raise ValueError('Another randomizer is updating My Games. Wait for it to finish.') from error
                self._lock_depth = 1
                try:
                    if function.__name__ != 'recover' and self.journal.exists():
                        self.recover()
                    return function(self, *args, **kwargs)
                finally:
                    self._lock_depth = 0
                    if os.name == 'nt':
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle, fcntl.LOCK_UN)
    return call


class PartyLibrary:
    def __init__(self, root=None):
        self.root = Path(root or app_dir() / 'Parties').resolve()
        self.index_path = self.root / 'library.json'
        self.journal = self.root / 'transaction.json'
        self._mutex = threading.RLock()
        self._lock_depth = 0
        self.unreadable = []        # (folder, error) of the parties ``list`` could not read
        self.root.mkdir(parents=True, exist_ok=True)
        self.recover()

    def index(self):
        if not self.index_path.exists():
            return {'version': 1, 'active': None}
        value = json.loads(self.index_path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('version') != 1:
            raise ValueError('Unsupported party library.')
        return value

    @property
    def active_id(self):
        return self.index()['active']

    def folder(self, ident):
        if not isinstance(ident, str) or len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident):
            raise ValueError('Invalid party identifier.')
        return self.root / ident

    def get(self, ident):
        value = json.loads((self.folder(ident) / 'party.json').read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('id') != ident:
            raise ValueError('Inconsistent party metadata.')
        if value.get('mod_name') != 'OoT_Randomizer_' + value.get('seed_id', '')[:16]:
            raise ValueError('Invalid party mod folder.')
        return value

    def list(self):
        """Readable parties, the active one first. A damaged ``party.json`` is left out
        (and named in ``unreadable``) instead of blocking every other party."""
        parties, self.unreadable = [], []
        for path in self.root.iterdir():
            if path.is_dir() and (path / 'party.json').is_file():
                try:
                    parties.append(self.get(path.name))
                except (OSError, ValueError) as error:   # JSONDecodeError is a ValueError
                    self.unreadable.append((path.name, str(error)))
        active = self.active_id
        return sorted(parties, key=lambda p: (p['id'] != active, p['name'].casefold()))

    def bundle(self, party):
        revision = party['revision']
        if len(revision) != 32 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('Invalid party revision.')
        return self.folder(party['id']) / 'snapshots' / revision

    def tracker_dir(self, ident):
        return self.folder(ident) / 'tracker'

    def _closed(self):
        processes = None
        if os.name != "nt":
            try:
                processes = subprocess.check_output(["ps", "-axo", "comm="], text=True).splitlines()
            except (OSError, subprocess.SubprocessError):
                processes = []
        game = running_game(processes)
        if game:
            raise GameRunning(f"Save and close the game / emulator first ({game} is running).")

    def _targets(self, mods, saves):
        from oot_rando.path_safety import SAVE_ACCOUNT_HEADROOM, SEED_ROMFS_HEADROOM, validate_path_headroom
        _plain_tree(mods)
        mods = validate_mod_directory(mods)
        saves = validate_save_root(saves)
        validate_path_headroom(mods, max_relative_len=SEED_ROMFS_HEADROOM, label="Mods folder")
        validate_path_headroom(saves, max_relative_len=SAVE_ACCOUNT_HEADROOM, label="Save account folder")
        validate_path_headroom(self.root, max_relative_len=195, label="Parties library folder", enforce_win_classic=False)
        for a, b in ((mods, saves), (mods, self.root), (saves, self.root)):
            if a == b or a in b.parents or b in a.parents:
                raise ValueError("The library, mods and save folders must be separate.")
        return mods, saves

    @_operation
    def preflight_generation(self, name, mods, saves, settings, *, continuing=False):
        "Run every party creation & activation sanity check BEFORE generating a seed."
        from oot_rando.randomizer.randomizer_core import Settings, settings_identity
        self._closed()
        self._name(name)
        mods, saves = self._targets(mods, saves)
        outgoing = self.get(self.active_id) if self.active_id else None
        if continuing:
            if not self.active_id or outgoing is None:
                raise ValueError("There is no active party to continue.")
            old_manifest, _ = read_artifact(self.bundle(outgoing) / "seed")
            if (Path(outgoing["mods"]) != mods or Path(outgoing["saves"]) != saves
                    or Settings.from_dict(old_manifest["settings"]).to_dict() != Settings.from_dict(settings.to_dict()).to_dict()):
                raise ValueError("Only a regeneration with the same settings can continue the active save.")
        if outgoing and Path(outgoing["mods"]).exists():
            out_seed = Path(outgoing["mods"]) / outgoing["mod_name"]
            if out_seed.exists():
                out_manifest, _ = read_artifact(out_seed)
                if out_manifest.get("seed_id") != outgoing["seed_id"]:
                    raise ValueError("The installed seed changed outside My Games. Restore it before switching.")
            else:
                snap_seed = self.bundle(outgoing) / "seed"
                snap_manifest, _ = read_artifact(snap_seed)
                if snap_manifest.get("seed_id") != outgoing["seed_id"]:
                    raise ValueError("The stored seed belongs to another party.")
        owned_mod = Path(outgoing["mods"]) / outgoing["mod_name"] if outgoing else None
        if mods.exists():
            for path in mods.iterdir():
                if is_randomizer_seed(path) and path != owned_mod:
                    raise ValueError("An unmanaged seed is installed here. Preserve it as a party first.")
        owns_save = bool(outgoing and Path(outgoing["saves"]) == saves)
        if saves.exists() and any(saves.iterdir()) and not owns_save:
            raise ValueError(
                "This destination already contains saves. Preserve its installed game first "
                "or choose an empty save account folder."
            )
        if qol_seed_warning(mods):
            raise ValueError("Move OoT_QoL out of this mods folder before activating a randomizer party.")
        target_mod = mods / ("OoT_Randomizer_" + settings_identity(settings)[:16])
        if target_mod.exists() and target_mod != owned_mod:
            raise ValueError("The target mod folder already exists and is not managed by this party.")
        repl_paths = []
        if outgoing:
            if Path(outgoing["mods"]).exists() and owned_mod is not None:
                repl_paths.append(owned_mod)
            if Path(outgoing["saves"]).exists():
                repl_paths.append(Path(outgoing["saves"]))
        for p in (target_mod, saves):
            if p not in repl_paths:
                repl_paths.append(p)
        if any(a in b.parents or b in a.parents for i, a in enumerate(repl_paths) for b in repl_paths[i + 1:]):
            raise ValueError("Party destinations overlap. Choose separate save accounts and mods folders.")
        return mods, saves

    def _name(self, name, ident=None):
        name = name.strip()
        if not name or len(name) > 100 or any(ord(c) < 32 for c in name):
            raise ValueError('Give the party a name (1–100 characters).')
        if any(p['id'] != ident and p['name'].casefold() == name.casefold() for p in self.list()):
            raise ValueError('A party already has this name.')
        return name

    def _snapshot(self, party, seed, saves=None):
        revision = uuid.uuid4().hex
        destination = self.folder(party['id']) / 'snapshots' / revision
        destination.mkdir(parents=True)
        try:
            copy_verified(Path(seed), destination / 'seed')
            manifest, _ = read_artifact(destination / 'seed')
            if saves is not None and Path(saves).exists():
                copy_verified(Path(saves), destination / 'save')
            else:
                (destination / 'save').mkdir()
            _write(destination / 'snapshot.json', {'version': 1, 'saves': _hashes(destination / 'save')})
            updated = dict(party, revision=revision, seed_id=manifest['seed_id'],
                           updated=datetime.now(timezone.utc).isoformat())
            _write(self.folder(party['id']) / 'party.json', updated)
        except Exception:
            from oot_rando.path_safety import fs_path
            shutil.rmtree(fs_path(destination))
            raise
        # Once the pointer is committed, cleanup must never remove that snapshot.
        previous = party.get('revision')
        try:
            for old in destination.parent.iterdir():
                if old.name not in {revision, previous} and old.is_dir():
                    try:
                        shutil.rmtree(old)
                    except OSError:
                        pass
        except OSError:
            pass
        return updated

    @_operation
    def create(self, name, seed, mods, saves, *, capture=False, tracker=None, ap_address='', continue_active=False):
        """Import a seed, optionally adopting the currently installed seed/save pair."""
        self._closed()
        name = self._name(name)
        mods, saves = self._targets(mods, saves)
        seed = Path(seed).resolve()
        manifest, _ = read_artifact(seed)
        continued_saves = None
        if continue_active:
            if not self.active_id:
                raise ValueError('There is no active party to continue.')
            active = self.refresh()
            old_manifest, _ = read_artifact(self.bundle(active) / 'seed')
            from oot_rando.randomizer.randomizer_core import Settings
            if (Path(active['mods']) != mods or Path(active['saves']) != saves
                    or Settings.from_dict(old_manifest['settings']).to_dict() != Settings.from_dict(manifest['settings']).to_dict()):
                raise ValueError('Only a regeneration with the same settings can continue the active save.')
            continued_saves = self.bundle(active) / 'save'
        if capture:
            if self.active_id or seed.parent != mods:
                raise ValueError('Only an unmanaged installed seed can be adopted.')
            installed = [p for p in mods.iterdir() if is_randomizer_seed(p)]
            if installed != [seed]:
                raise ValueError('Keep exactly one randomizer seed in this mods folder before adopting it.')
            if manifest.get('tracking'):
                from oot_rando.formats.save_file import load_snapshot
                tracking = json.loads((seed / 'tracking.json').read_text(encoding='utf-8'))
                marker = int(tracking['seed_marker'])
                for path in saves.glob('slot_*/progress.sav'):
                    if load_snapshot(path)['bool'].get(marker) is not True:
                        raise ValueError('This save account contains a save from another seed: '
                                         + str(path) + '. Choose the account of the installed seed.')
        party = {'id': uuid.uuid4().hex, 'name': name, 'mods': str(mods), 'saves': str(saves),
                 'mod_name': 'OoT_Randomizer_' + manifest['seed_id'][:16], 'ap_address': ap_address}
        if capture:
            party['mod_name'] = seed.name
        folder = self.folder(party['id'])
        folder.mkdir()
        try:
            if tracker and Path(tracker).is_file():
                # The UI imports these checks into the party's independent tracker profile.
                shutil.copy2(tracker, folder / 'imported-tracker.json')
                if continue_active:
                    imported = json.loads((folder / 'imported-tracker.json').read_text(encoding='utf-8'))
                    imported['seed_id'] = manifest['seed_id']
                    _write(folder / 'imported-tracker.json', imported)
            party = self._snapshot(party, seed, saves if capture else continued_saves)
            if capture:
                _write(self.index_path, {'version': 1, 'active': party['id']})
            return party
        except Exception:
            shutil.rmtree(folder)
            raise

    @_operation
    def refresh(self, ap_address=None):
        """Store the active installation before switching. Old revisions remain recoverable."""
        self._closed()
        if not self.active_id:
            return None
        party = self.get(self.active_id)
        mods, saves = self._targets(party['mods'], party['saves'])
        seed = mods / party['mod_name']
        manifest, _ = read_artifact(seed)
        if manifest['seed_id'] != party['seed_id']:
            raise ValueError('The installed seed changed outside My Games. Restore it before switching.')
        if ap_address is not None:
            party['ap_address'] = ap_address
        return self._snapshot(party, seed, saves)

    @_operation
    def rename(self, ident, name):
        party = self.get(ident)
        party['name'] = self._name(name, ident)
        _write(self.folder(ident) / 'party.json', party)

    @_operation
    def set_address(self, ident, address):
        party = self.get(ident)
        party['ap_address'] = address.strip()
        _write(self.folder(ident) / 'party.json', party)

    @_operation
    def migrate_mods_directory(self, new_mods, *, old_mods=None, root=None):
        """Point at ``new_mods`` the games whose mods folder vanished: ``old_mods``, and any other
        of the same Longshot root (``root``, else the one of ``new_mods``). A folder which still
        exists is never moved: an older build is the player's choice.

        A Longshot update can delete the version folder a game was installed in. The active game
        then gets its stored seed installed again in ``new_mods`` (same transaction as a switch),
        unless another randomizer seed already sits there. Returns the names of the moved games.
        """
        target = validate_mod_directory(new_mods)
        old = Path(os.path.abspath(old_mods)) if old_mods else None
        if root:
            root = Path(root).resolve()
        else:
            layout = longshot_layout_root(target)
            root = layout[0].resolve() if layout else None
        moved = []
        for party in self.list():
            mods = Path(os.path.abspath(party['mods']))
            if mods.exists() or _same_path(mods, target):
                continue
            layout = longshot_layout_root(mods) if root is not None else None
            same_root = layout is not None and layout[0].resolve() == root
            if not same_root and not (old is not None and _same_path(mods, old)):
                continue
            record = self.folder(party['id']) / 'party.json'
            _write(record, dict(party, mods=str(target)))   # recovery checks this owner
            if party['id'] == self.active_id:
                seed = target / party['mod_name']
                installed = target.is_dir() and any(is_randomizer_seed(p) for p in target.iterdir())
                if not seed.exists() and not installed:
                    try:
                        self._install({seed: self.bundle(party) / 'seed'}, party['id'])
                    except Exception:
                        _write(record, party)
                        raise
            moved.append(party['name'])
        return moved

    @_operation
    def delete(self, ident):
        if ident == self.active_id:
            raise ValueError('Activate another party before deleting this one.')
        self.get(ident)
        # Reversible removal: retained beside the library, outside the displayed list.
        trash = self.root / ".deleted"
        trash.mkdir(exist_ok=True)
        self.folder(ident).rename(trash / (ident + "-" + uuid.uuid4().hex[:8]))

    @_operation
    def activate(self, ident, ap_address=None):
        self._closed()
        if ident == self.active_id:
            return self.get(ident)
        target = self.get(ident)
        mods, saves = self._targets(target['mods'], target['saves'])
        incoming = self.bundle(target)
        manifest, _ = read_artifact(incoming / 'seed')
        if manifest['seed_id'] != target['seed_id']:
            raise ValueError('The stored seed belongs to another party.')
        _plain_tree(incoming)
        integrity = json.loads((incoming / 'snapshot.json').read_text(encoding='utf-8'))
        if (integrity.get('version') != 1 or not (incoming / 'save').is_dir()
                or _hashes(incoming / 'save') != integrity.get('saves')):
            raise ValueError('The stored saves are incomplete or modified. Restore the previous snapshot before switching.')
        outgoing = self.get(self.active_id) if self.active_id else None
        owned_mod = Path(outgoing['mods']) / outgoing['mod_name'] if outgoing else None
        if mods.exists():
            for path in mods.iterdir():
                if is_randomizer_seed(path) and path != owned_mod:
                    raise ValueError('An unmanaged seed is installed here. Preserve it as a party first.')
        owns_save = outgoing and Path(outgoing['saves']) == saves
        if saves.exists() and any(saves.iterdir()) and not owns_save:
            raise ValueError('This destination already contains saves. Preserve its installed game first '
                             'or choose an empty save account folder.')
        conflicts = conflicting_mods(mods, manifest,
                                     outgoing['mod_name'] if outgoing and Path(outgoing['mods']) == mods else '') if mods.exists() else []
        if conflicts:
            raise ValueError('Conflicting mods: ' + ', '.join(conflicts))
        if qol_seed_warning(mods):
            raise ValueError('Move OoT_QoL out of this mods folder before activating a randomizer party.')
        outgoing_mods_missing = bool(outgoing and not Path(outgoing['mods']).exists())
        if outgoing:
            if outgoing_mods_missing:
                # Outgoing port folder was removed (e.g. Longshot version update); archive saves
                # with the existing party snapshot seed so switching does not fail on missing old mods.
                if ap_address is not None:
                    outgoing['ap_address'] = ap_address
                out_saves = Path(outgoing['saves'])
                outgoing = self._snapshot(outgoing, self.bundle(outgoing) / 'seed', out_saves if out_saves.is_dir() else None)
            else:
                outgoing = self.refresh(ap_address)
        # One transaction can exchange two distinct destinations. Outgoing destinations
        # are emptied only after being archived, so every installed pair has one owner.
        replacements = {}
        if outgoing:
            if not outgoing_mods_missing:
                replacements[Path(outgoing['mods']) / outgoing['mod_name']] = None
            if Path(outgoing['saves']).exists():
                replacements[Path(outgoing['saves'])] = None
        replacements[mods / target['mod_name']] = incoming / 'seed'
        replacements[saves] = incoming / 'save'
        paths = list(replacements)
        if any(a in b.parents or b in a.parents for i, a in enumerate(paths) for b in paths[i + 1:]):
            raise ValueError('Party destinations overlap. Choose separate save accounts and mods folders.')
        if (mods / target['mod_name']).exists() and mods / target['mod_name'] != owned_mod:
            raise ValueError('The target mod folder already exists and is not managed by this party.')
        self._install(replacements, ident)
        return target

    def _install(self, replacements, ident):
        """Write intent before renames; library.json is the commit point."""
        transaction = uuid.uuid4().hex
        operations = []
        try:
            for destination, source in replacements.items():
                _plain_tree(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                stage = destination.with_name('.party-stage-' + uuid.uuid4().hex)
                backup = destination.with_name('.party-backup-' + uuid.uuid4().hex)
                operations.append({'destination': str(destination), 'stage': str(stage),
                                   'backup': str(backup), 'had_original': destination.exists(), 'prepared': False})
            # Persist intent before staging too: a crash while copying must not leave
            # an orphan mod which would later conflict with every seed installation.
            journal = {'id': transaction, 'operations': operations}
            _write(self.journal, journal)
            for op, source in zip(operations, replacements.values()):
                if source is not None:
                    copy_verified(source, Path(op['stage']))
                    op['prepared'] = True
                    _write(self.journal, journal)
            self._closed()
            for op in operations:
                destination, stage, backup = (Path(op[key]) for key in ('destination', 'stage', 'backup'))
                if op['had_original']:
                    destination.rename(backup)
                if stage.exists():
                    stage.rename(destination)
            _write(self.index_path, {'version': 1, 'active': ident, 'transaction': transaction})
        except Exception:
            if self.journal.exists():
                self.recover()
            else:
                for op in operations:
                    stage = Path(op['stage'])
                    if stage.exists():
                        shutil.rmtree(stage)
            raise
        self.recover()

    @_operation
    def recover(self):
        if not self.journal.exists():
            return
        # The game must stay closed during restart recovery, too.
        self._closed()
        journal = json.loads(self.journal.read_text(encoding='utf-8'))
        committed = self.index().get('transaction') == journal['id']
        allowed = {path for party in self.list() for path in
                   (Path(party['mods']) / party['mod_name'], Path(party['saves']))}
        for op in journal['operations']:
            destination = Path(op['destination'])
            if destination not in allowed:
                raise ValueError('Recovery destination is not owned by a party: ' + str(destination))
            for key, prefix in (('stage', '.party-stage-'), ('backup', '.party-backup-')):
                path = Path(op[key])
                suffix = path.name.removeprefix(prefix)
                if (path.parent != destination.parent or not path.name.startswith(prefix)
                        or len(suffix) != 32 or any(c not in '0123456789abcdef' for c in suffix)):
                    raise ValueError('Invalid recovery path: ' + str(path))
                _plain_tree(path)
            _plain_tree(destination)
        for op in reversed(journal['operations']):
            destination, stage, backup = (Path(op[key]) for key in ('destination', 'stage', 'backup'))
            if not committed:
                if backup.exists():
                    if destination.exists():
                        shutil.rmtree(destination)
                    backup.rename(destination)
                elif (not op['had_original'] and op.get('prepared', True)
                      and not stage.exists() and destination.exists()):
                    shutil.rmtree(destination)
            for temporary in (stage, backup):
                if temporary.exists():
                    shutil.rmtree(temporary)
        self.journal.unlink()
