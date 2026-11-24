"""Named-party library page and its integration with the desktop application."""
import json
from datetime import datetime
import os
from pathlib import Path
import logging
import secrets
import shutil
import tempfile
import uuid
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from oot_rando import native_dialogs as filedialog

from oot_rando.parties import PartyLibrary, validate_save_root
from oot_rando.randomizer.randomizer_services import is_randomizer_seed, validate_mod_directory, read_artifact
from oot_rando.gui.generation_worker import generate_isolated
from oot_rando.paths import data_dir, open_in_file_manager

_LOG = logging.getLogger(__name__)
from oot_rando.patching.randomize_kokiri import TITLE


class PartiesPage:
    def init_parties(self):
        self.party_context = None
        self.party_job_paused = False
        self.party_name = tk.StringVar()
        self.party_search = tk.StringVar()
        self.party_library = None
        self.party_library_error = ''
        try:
            self.party_library = PartyLibrary()
        except Exception as error:
            self.party_library_error = str(error)

    def build_parties(self):
        parent = self.scrollable(self.parties_tab)
        actions = ttk.Frame(parent, style='Page.TFrame')
        actions.pack(fill='x', pady=(0, 14))
        ttk.Button(actions, text='+ New party', style='Accent.TButton',
                   command=self.new_party).pack(side='left')
        ttk.Button(actions, text='Import a seed…', command=self.import_party).pack(side='left', padx=8)
        ttk.Button(actions, text='Keep the installed party…',
                   command=self.capture_party).pack(side='left')
        search = ttk.Frame(parent, style='Page.TFrame')
        search.pack(fill='x', pady=(0, 14))
        ttk.Label(search, text='Search by name', style='Page.TLabel').pack(side='left', padx=(0, 12))
        ttk.Entry(search, textvariable=self.party_search).pack(side='left', fill='x', expand=True)
        self.parties_rows = ttk.Frame(parent, style='Page.TFrame')
        self.parties_rows.pack(fill='both', expand=True)
        self.party_search.trace_add('write', lambda *args: self.render_parties())
        self.render_parties()
        box = self.card(self.settings_body, 'Party name',
                        'The seed and its progress are kept together in My Games.')
        ttk.Entry(box, textvariable=self.party_name).pack(fill='x')

    def parties_ready(self):
        if self.busy:
            self.status.set('An operation is already running.')
            return False
        if self.party_library is None:
            raise ValueError('Library unavailable: ' + self.party_library_error
                             + '\nClose the game, then restart the randomizer to resume the recovery.')
        return True

    def render_parties(self):
        if not hasattr(self, 'parties_rows'):
            return
        for child in self.parties_rows.winfo_children():
            child.destroy()
        try:
            if self.party_library is None:
                raise ValueError(self.party_library_error)
            parties = self.party_library.list()
            query = self.party_search.get().strip().casefold()
            shown = [p for p in parties if query in p['name'].casefold()]
            if not shown:
                self.card(self.parties_rows,
                          'No party found' if parties else 'Your next adventure starts here',
                          'Create a party, import a seed or keep the one already installed.'
                          if not parties else 'Try another name.')
            for party in shown:
                ident = party['id']
                active = ident == self.party_library.active_id
                bundle = self.party_library.bundle(party)
                manifest = json.loads((bundle / 'seed' / 'manifest.json').read_text(encoding='utf-8'))
                mode = 'Archipelago' if manifest['settings'].get('archipelago') else 'Solo'
                saves = Path(party['saves']) if active else bundle / 'save'
                started = any(saves.glob('slot_*/progress.sav'))
                status = 'ACTIVE' if active else 'In progress' if started else 'Not started yet'
                box = self.card(self.parties_rows)
                heading = self.buttons(box)
                ttk.Label(heading, text=party['name'], style='Heading.TLabel',
                          wraplength=360).pack(side='left', fill='x', expand=True)
                ttk.Label(heading, text=status, style='Chip.TLabel').pack(side='right')
                mods = Path(party['mods'])
                destination = f'Recomp ({mods.parent.name})' if mods.name.lower() == 'mods' else 'Emulator'
                ttk.Label(box, text=f'{mode} · {destination} · '
                          f'Seed {manifest["settings"].get("seed", "")}',
                          style='Muted.TLabel', wraplength=600).pack(anchor='w', pady=(6, 2))
                copied = datetime.fromisoformat(party['updated']).astimezone().strftime('%Y-%m-%d %H:%M')
                ttk.Label(box, text='Last copy: ' + copied,
                          style='Small.TLabel').pack(anchor='w')
                row = self.buttons(box, pady=(12, 0))
                ttk.Button(row, text='Continue' if active else 'Activate', style='Accent.TButton',
                           command=lambda key=ident: self.activate_party(key)).pack(side='left')
                ttk.Button(row, text='Rename', command=lambda key=ident: self.rename_party(key)).pack(side='left', padx=8)
                ttk.Button(row, text='Folder', command=lambda key=ident: self.party_folder(key)).pack(side='left')
                delete = ttk.Button(row, text='Delete', command=lambda key=ident: self.delete_party(key))
                delete.pack(side='right')
                if active:
                    delete.state(['disabled'])
        except Exception as error:
            self.card(self.parties_rows, 'Library unavailable', str(error))

    def new_party(self):
        if self.busy:
            return
        self.party_name.set('')
        self.seed.set(secrets.token_hex(8))
        self.show_page('newseed')

    def party_chip(self):
        name = self.party_context['name']
        return name if len(name) <= 32 else name[:31] + '…'

    def party_destination(self, mods):
        """Bind an exact save account once; never infer it again from timestamps."""
        active = self.party_library.get(self.party_library.active_id) if self.party_library.active_id else None
        if active and Path(active['mods']) == mods:
            return Path(active['saves'])
        initial = Path(self.save_path.get()).parent.parent if self.save_path.get() else None
        chosen = filedialog.askdirectory(parent=self.root,
                    title='Save account folder: the one directly containing slot_00, slot_01…',
                    initialdir=str(initial) if initial and initial.is_dir() else str(mods.parent))
        return validate_save_root(chosen) if chosen else None

    def party_display_name(self, initial=''):
        name = simpledialog.askstring('Party name', 'What would you like to call this party?',
                                     initialvalue=initial, parent=self.root)
        return name.strip() if name and name.strip() else None

    def capture_party(self):
        try:
            if not self.parties_ready():
                return
            if self.party_library.active_id:
                raise ValueError('A party is already managed. It is saved automatically at the next switch.')
            mods = validate_mod_directory(self.mods.get())
            installed = [p for p in mods.iterdir() if is_randomizer_seed(p)] if mods.exists() else []
            if len(installed) != 1:
                raise ValueError('There must be exactly one randomizer seed in the mods folder selected in Setup.')
            name = self.party_display_name(installed[0].name)
            if not name:
                return
            saves = self.party_destination(mods)
            if saves is None:
                return
            manual = self.tracker.manual.path if self.tracker and self.artifact == installed[0] else None
            address = self.ap_address.get()
            self.pause_party_services()
            self.run_job(lambda progress: self.party_library.create(
                name, installed[0], mods, saves, capture=True, tracker=manual, ap_address=address), self.party_opened)
        except Exception as error:
            self.error(error)

    def ensure_party_destination(self, mods):
        if not self.party_library.active_id and mods.exists() and any(is_randomizer_seed(p) for p in mods.iterdir()):
            messagebox.showinfo('Keep your party',
                'First keep the installed party, with its name and its save. '
                'You can then create or import another party.', parent=self.root)
            self.show_page('parties')
            return False
        return True

    def import_party(self):
        try:
            if not self.parties_ready():
                return
            mods = validate_mod_directory(self.mods.get())
            if not self.ensure_party_destination(mods):
                return
            seed = filedialog.askdirectory(title='Seed to import: folder containing manifest.json', parent=self.root)
            if not seed:
                return
            manifest, _ = read_artifact(seed)
            name = self.party_display_name(manifest['settings'].get('seed', ''))
            if not name:
                return
            saves = self.party_destination(mods)
            if saves is None:
                return
            address = self.ap_address.get()
            def job(progress):
                progress('Copying the seed into My Games…')
                return self.party_library.create(name, seed, mods, saves, ap_address=address)
            def done(party):
                self.render_parties()
                self.show_page('parties')
                self.status.set('Party imported. Click Activate to play.')
            self.run_job(job, done)
        except Exception as error:
            self.error(error)

    def pause_party_services(self):
        self.party_job_paused = True
        self.stop_archipelago()
        if self.turbo:
            self.turbo.stop()
        # Stale in-flight results are discarded by poll using tracker identity.
        self.tracker = None

    def _midna_stage_root(self):
        """Resolve where conflicting live mods are parked during party switches for Midna re-merging."""
        midna_host = getattr(self, "_midna_host", None)
        win = getattr(midna_host, "_window", None) if midna_host is not None else None
        cfg = getattr(win, "cfg", None) if win is not None else None
        staged = getattr(cfg, "staged_mods_dir", "") if cfg is not None else ""
        if staged:
            return Path(staged)
        return data_dir() / "staged_for_generation"

    def _party_seed_dir(self, party):
        """Return the live seed directory, falling back to its party snapshot if merged or migrated."""
        live_seed = Path(party["mods"]) / party["mod_name"]
        if live_seed.is_dir():
            return live_seed
        snapshot_seed = self.party_library.bundle(party) / "seed"
        if snapshot_seed.is_dir():
            return snapshot_seed
        return live_seed

    def _run_with_midna_bridge(self, target_mods, target_manifest, action, outgoing=None):
        """Prepare live mods/ for a party switch when Midna merged or standalone mods exist."""
        from oot_rando.parties import _copy
        from oot_rando.randomizer.randomizer_services import conflicting_mods

        self.party_library._closed()
        target_mods = Path(target_mods)
        if outgoing is None and self.party_library.active_id:
            outgoing = self.party_library.get(self.party_library.active_id)

        restored_outgoing = None
        parked_merged = []
        staged_moves = []
        self._last_midna_switch_note = ""

        try:
            # 1. If Midna archived the active seed into Merged_Zelda_Rando, restore a pristine
            #    copy from the party snapshot so PartyLibrary.refresh() can archive the latest saves.
            if outgoing:
                out_mods = Path(outgoing["mods"])
                out_seed = out_mods / outgoing["mod_name"]
                if out_mods.is_dir() and not out_seed.exists():
                    snap_seed = self.party_library.bundle(outgoing) / "seed"
                    if snap_seed.is_dir():
                        _copy(snap_seed, out_seed)
                        restored_outgoing = out_seed

            # 2. Park any stale Merged_Zelda_Rando outside mods/ (rollback-safe, instant rename).
            mods_dirs = []
            if outgoing:
                mods_dirs.append(Path(outgoing["mods"]))
            if target_mods not in mods_dirs:
                mods_dirs.append(target_mods)
            for mdir in mods_dirs:
                merged = mdir / "Merged_Zelda_Rando"
                if merged.is_dir():
                    park_parent = mdir.parent if mdir.parent != mdir else data_dir() / "party-midna-staging"
                    park_parent.mkdir(parents=True, exist_ok=True)
                    parked = park_parent / (".midna-merged-tmp-" + uuid.uuid4().hex)
                    shutil.move(str(merged), str(parked))
                    parked_merged.append((merged, parked))

            # 3. Auto-stage any remaining conflicting live mods so Midna can merge them cleanly.
            if target_mods.is_dir() and target_manifest is not None:
                skip = outgoing["mod_name"] if outgoing and Path(outgoing["mods"]) == target_mods else ""
                conflicts = conflicting_mods(target_mods, target_manifest, skip)
                if conflicts:
                    stage_root = self._midna_stage_root()
                    stage_root.mkdir(parents=True, exist_ok=True)
                    for mod_name in conflicts:
                        src_mod = target_mods / mod_name
                        if src_mod.is_dir():
                            dst_mod = stage_root / mod_name
                            prev_backup = None
                            if dst_mod.exists() or dst_mod.is_symlink():
                                prev_backup = stage_root / (".midna-stage-prev-" + uuid.uuid4().hex)
                                shutil.move(str(dst_mod), str(prev_backup))
                            shutil.move(str(src_mod), str(dst_mod))
                            staged_moves.append((src_mod, dst_mod, prev_backup))

            result = action()
        except Exception:
            # Isolate each rollback step so one filesystem error cannot strand Merged_Zelda_Rando or staged mods.
            for src_mod, dst_mod, prev_backup in reversed(staged_moves):
                try:
                    if (dst_mod.exists() or dst_mod.is_symlink()) and not (src_mod.exists() or src_mod.is_symlink()):
                        shutil.move(str(dst_mod), str(src_mod))
                except Exception:
                    _LOG.debug("Rollback failed restoring staged mod %s", src_mod, exc_info=True)
                try:
                    if prev_backup is not None and (prev_backup.exists() or prev_backup.is_symlink()) and not (dst_mod.exists() or dst_mod.is_symlink()):
                        shutil.move(str(prev_backup), str(dst_mod))
                except Exception:
                    _LOG.debug("Rollback failed restoring previous staged copy %s", dst_mod, exc_info=True)
            if restored_outgoing is not None and restored_outgoing.exists():
                shutil.rmtree(restored_outgoing, ignore_errors=True)
            for orig_merged, parked in reversed(parked_merged):
                try:
                    if parked.exists() and not orig_merged.exists():
                        shutil.move(str(parked), str(orig_merged))
                except Exception:
                    _LOG.debug("Rollback failed restoring parked merged mod %s", orig_merged, exc_info=True)
            raise

        # Commit cleanup: stale Merged_Zelda_Rando belonged to the previous seed.
        for _, parked in parked_merged:
            if parked.exists():
                shutil.rmtree(parked, ignore_errors=True)
        for _, _, prev_backup in staged_moves:
            if prev_backup is not None:
                if prev_backup.is_symlink() or prev_backup.is_file():
                    prev_backup.unlink(missing_ok=True)
                elif prev_backup.exists():
                    shutil.rmtree(prev_backup, ignore_errors=True)

        notes = []
        if parked_merged:
            notes.append("Cleared previous Merged_Zelda_Rando")
        if staged_moves:
            names = ", ".join(src.name for src, _, _ in staged_moves)
            notes.append("staged conflicting mods (" + names + ")")
        if notes:
            self._last_midna_switch_note = "; ".join(notes) + " — open Midna's Devotion and click Apply & Build to re-merge for this game."
        return result

    def activate_party(self, ident):
        try:
            if not self.parties_ready():
                return
            if ident == self.party_library.active_id:
                if not self.party_context or self.party_context["id"] != ident:
                    self.party_opened(self.party_library.get(ident))
                self.show_page("tracker")
                return
            self.party_library._closed()
            address = self.ap_address.get() if self.party_context else None
            self.pause_party_services()
            def job(progress):
                progress("Saving the outgoing party and installing the chosen one…")
                target = self.party_library.get(ident)
                manifest, _ = read_artifact(self.party_library.bundle(target) / "seed")
                return self._run_with_midna_bridge(
                    target["mods"],
                    manifest,
                    lambda: self.party_library.activate(ident, address),
                )
            self.run_job(job, self.party_opened)
        except Exception as error:
            self.error(error)

    def party_opened(self, party):
        self.party_job_paused = False
        party_mods = party["mods"]
        if not Path(party_mods).exists() and hasattr(self, "_resolve_stale_mods_path"):
            resolved = self._resolve_stale_mods_path(party_mods)
            if resolved:
                party_mods = resolved
        self.mods.set(party_mods)
        self.save_path.set("")
        self.auto_save.set(True)
        self.ap_password.set("")
        self.ap_address.set(party.get("ap_address") or "archipelago.gg:38281")
        self.slot.set("party-" + party["id"])
        self.use_artifact(self._party_seed_dir(party))
        midna_host = getattr(self, "_midna_host", None)
        if midna_host is not None and midna_host.is_mounted:
            midna_host.sync_from_randomizer(self.mods.get(), refresh_always=True)
        self.start_turbo()
        self.render_parties()
        self.update_home()
        note = getattr(self, "_last_midna_switch_note", "")
        if note:
            self.status.set("Active party: " + party["name"] + ". " + note)
        else:
            self.status.set("Active party: " + party["name"] + ". You can start the game.")

    def match_party(self, directory):
        self.party_context = None
        if self.party_library and self.party_library.active_id:
            party = self.party_library.get(self.party_library.active_id)
            resolved = Path(directory).resolve()
            candidates = {(Path(party["mods"]) / party["mod_name"]).resolve()}
            if (Path(party["mods"]) / "Merged_Zelda_Rando").is_dir():
                candidates.add((self.party_library.bundle(party) / "seed").resolve())
            if resolved in candidates:
                self.party_context = party
                self.slot.set("party-" + party["id"])
        if self.party_context is None and self.slot.get().startswith("party-"):
            self.slot.set("My game")

    def restore_party(self):
        if self.party_library and self.party_library.active_id:
            try:
                self.party_opened(self.party_library.get(self.party_library.active_id))
            except Exception as error:
                self.error(error)
            return True
        return False

    def rename_party(self, ident):
        try:
            if not self.parties_ready():
                return
            name = self.party_display_name(self.party_library.get(ident)['name'])
            if name:
                self.party_library.rename(ident, name)
                if self.party_context and self.party_context['id'] == ident:
                    self.party_context = self.party_library.get(ident)
                    self.seed_chip.set(self.party_chip())
                    self.update_home()
                self.render_parties()
        except Exception as error:
            self.error(error)

    def delete_party(self, ident):
        try:
            if not self.parties_ready():
                return
            party = self.party_library.get(ident)
            if messagebox.askyesno('Delete party', f'Remove “{party["name"]}” from My Games?\n\n'
                                  'A copy will remain in Parties/.deleted.', parent=self.root):
                self.party_library.delete(ident)
                self.render_parties()
        except Exception as error:
            self.error(error)

    def party_folder(self, ident):
        """Open the selected party's storage folder in the OS file manager."""
        try:
            open_in_file_manager(self.party_library.folder(ident))
        except Exception as error:
            self.error(error)

    def generate_party(self, nup, mods, settings, continuing=None):
        if not self.parties_ready() or not self.ensure_party_destination(mods):
            return
        initial = continuing["name"] + " (updated)" if continuing else settings.seed
        name = self.party_display_name(initial) if continuing else (
            self.party_name.get().strip() or self.party_display_name(initial))
        if not name:
            return
        self.party_library._name(name)
        saves = self.party_destination(mods)
        if saves is None:
            return
        self.party_library._closed()
        self.party_name.set(name)
        address = self.ap_address.get()
        outgoing_address = address if self.party_context else None
        previous = dict(self.artifact_manifest) if continuing else None
        manual = self.tracker.manual.path if continuing and self.tracker else None
        self.pause_party_services()
        def job(progress):
            staging = data_dir() / "party-generation"
            staging.mkdir(parents=True, exist_ok=True)
            # Generate away from installed files: even a generator crash leaves the
            # current seed/save pair intact. Failed activation leaves a selectable party.
            with tempfile.TemporaryDirectory(dir=staging) as temporary:
                temporary = Path(temporary)
                staging_mods = temporary / TITLE
                if continuing:
                    from oot_rando.parties import _copy
                    _copy(self._party_seed_dir(continuing), staging_mods / continuing["mod_name"])
                installed = generate_isolated(nup, staging_mods, settings, temporary / "archive", progress)
                manifest, _ = read_artifact(installed)
                def commit():
                    party = self.party_library.create(
                        name, installed, mods, saves, ap_address=address,
                        continue_active=bool(continuing), tracker=manual,
                    )
                    return self.party_library.activate(party["id"], outgoing_address)
                return self._run_with_midna_bridge(mods, manifest, commit)
        def done(party):
            self.party_generated(party, continued=bool(continuing))
            if continuing:
                self.offer_save_migration(self.artifact_manifest, previous)
        self.run_job(job, done)

    def party_generated(self, party, continued=False):
        self.party_opened(party)
        self.show_page("parties")
        text = ("The save was carried over. The original party stays available." if continued
                else "Start a new save in the game.")
        note = getattr(self, "_last_midna_switch_note", "")
        if note:
            text += chr(10) + chr(10) + note
        messagebox.showinfo("Party ready", f"“{party['name']}” is installed." + chr(10) + chr(10) + text, parent=self.root)
