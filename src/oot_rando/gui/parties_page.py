"""Named-party library page and its integration with the desktop application."""
import json
from datetime import datetime
from pathlib import Path
import logging
import secrets
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from oot_rando import native_dialogs as filedialog

from oot_rando.parties import PartyLibrary, validate_save_root
from oot_rando.randomizer.artifact import is_randomizer_seed, read_artifact
from oot_rando.randomizer.mods_folder import validate_mod_directory
from oot_rando.gui import theme
from oot_rando.gui.generation_worker import generate_isolated
from oot_rando.native_dialogs import open_in_file_manager
from oot_rando.paths import data_dir
from oot_rando.patching.randomize_kokiri import TITLE

_LOG = logging.getLogger(__name__)


class PartiesPage:
    def init_parties(self):
        self.party_context = None
        self.party_job_paused = False
        self.party_name = tk.StringVar()
        self.party_search = tk.StringVar()
        self.party_library = None
        self.party_library_error = ''
        # Opt-in: off unless the player turned it on in Setup (the menu entry appears then).
        self.parties_enabled = tk.BooleanVar(value=self.app_state.get('parties_enabled') is True)
        if self.parties_enabled.get():
            self.open_party_library()

    def open_party_library(self):
        self.party_library, self.party_library_error = None, ''
        try:
            self.party_library = PartyLibrary()
        except Exception as error:
            self.party_library_error = str(error)

    def parties_on(self):
        return self.parties_enabled.get()

    def toggle_parties(self):
        enabled = self.parties_enabled.get()
        self.write_app_state(parties_enabled=enabled)
        self.sidebar.set_visible('parties', enabled)
        if enabled:
            if self.party_library is None:
                self.open_party_library()
            notice = self.reconcile_longshot_installation()
            if notice:
                self.status.set(notice)
            self.restore_party()
        else:
            # The installed seed stays where it is; it is simply no longer managed.
            self.party_context = None
            if self.slot.get().startswith('party-'):
                self.slot.set('My game')
            if self.artifact:
                self.seed_chip.set('Seed  ' + self.seed_name)
            self.update_home()
            if self.current_page == 'parties':
                self.show_page('setup')
        self.sync_parties_page()

    def sync_parties_page(self):
        if not hasattr(self, 'parties_rows'):
            return
        enabled = self.parties_enabled.get()
        for widget in (self.parties_actions, self.parties_search):
            if enabled:
                widget.pack(fill='x', pady=(0, 14), before=self.parties_rows)
            else:
                widget.pack_forget()
        if enabled:
            self.party_name_box.pack(fill='x', pady=(0, 14))
        else:
            self.party_name_box.pack_forget()
        self.render_parties()

    def build_parties(self):
        parent = self.scrollable(self.parties_tab)
        actions = self.parties_actions = ttk.Frame(parent, style='Page.TFrame')
        ttk.Button(actions, text='+ New party', style='Accent.TButton',
                   command=self.new_party).pack(side='left')
        ttk.Button(actions, text='Import a seed…', command=self.import_party).pack(side='left', padx=8)
        ttk.Button(actions, text='Keep the installed party…',
                   command=self.capture_party).pack(side='left')
        search = self.parties_search = ttk.Frame(parent, style='Page.TFrame')
        theme.search_entry(search, self.party_search, 'Search a game by name…').pack(side='left', fill='x', expand=True)
        self.parties_rows = ttk.Frame(parent, style='Page.TFrame')
        self.parties_rows.pack(fill='both', expand=True)
        self.party_search.trace_add('write', lambda *args: self.render_parties())
        holder = ttk.Frame(self.settings_body, style='Page.TFrame')   # keeps the card at the top
        holder.pack(fill='x')
        box = self.party_name_box = self.card(holder, 'Party name',
                        'The seed and its progress are kept together in My Games.')
        ttk.Entry(box, textvariable=self.party_name).pack(fill='x')
        self.sync_parties_page()

    def parties_ready(self):
        if not self.parties_enabled.get():
            raise ValueError('Enable My Games first.')
        if self.busy:
            self.notify('An operation is already running.')
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
        if not self.parties_enabled.get():
            return
        if self.party_library is None:
            # Opening may have failed only because the game was still running while an
            # interrupted transaction waited for recovery: try again on every refresh.
            self.open_party_library()
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
            self._ensure_party_icons()
            for folder, error in self.party_library.unreadable:
                self.card(self.parties_rows, 'Unreadable party',
                          f'Parties/{folder}/party.json could not be read ({error}). '
                          'The other parties still work; restore that file or move the folder away.')
            for party in shown:
                ident = party['id']
                active = ident == self.party_library.active_id
                bundle = self.party_library.bundle(party)
                manifest = json.loads((bundle / 'seed' / 'manifest.json').read_text(encoding='utf-8'))
                mode = 'Archipelago' if manifest['settings'].get('archipelago') else 'Solo'
                from oot_rando.tracker.auto_tracker import resolve_party_save_root
                live_saves = resolve_party_save_root(party.get('saves'), party.get('mods'), bundle / 'save')
                snap_saves = bundle / 'save'
                if active and any(live_saves.rglob('progress.sav')):
                    saves = live_saves
                elif snap_saves.is_dir() and any(snap_saves.rglob('progress.sav')):
                    saves = snap_saves
                else:
                    saves = live_saves if active else snap_saves
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
                try:
                    from oot_rando.gui.party_save_card import render_party_save_card, summarize_party_save
                    summary = summarize_party_save(bundle / 'seed', saves)
                    render_party_save_card(box, summary, getattr(self, 'colors', {}))
                except Exception:
                    _LOG.debug('Failed rendering party save preview for %s', ident, exc_info=True)
                row = self.buttons(box, pady=(12, 0))
                ttk.Button(row, text='Continue' if active else 'Activate', style='Accent.TButton',
                           command=lambda key=ident: self.activate_party(key)).pack(side='left')
                ttk.Button(row, text='Rename', command=lambda key=ident: self.rename_party(key)).pack(side='left', padx=8)
                ttk.Button(row, text='Folder', command=lambda key=ident: self.party_folder(key)).pack(side='left')
                ttk.Button(row, text='Health', command=lambda key=ident: self.party_health_check(key)).pack(side='left', padx=(8, 0))
                delete = ttk.Button(row, text='Delete', command=lambda key=ident: self.delete_party(key))
                delete.pack(side='right')
                if active:
                    delete.state(['disabled'])
        except Exception as error:
            self.card(self.parties_rows, 'Library unavailable', str(error))

    def _ensure_party_icons(self):
        """Extract game item icons in the background on Linux/Windows/macOS so Party cards show real icons."""
        if getattr(self, "_party_icons_started", False):
            return
        try:
            from oot_rando.paths import state_dir
            from oot_rando.pc_port import is_port_folder
            from oot_rando.tracker.game_overlay import IconCache
            mods_val = self.mods.get().strip() if hasattr(self, "mods") else ""
            nup_val = self.nup.get().strip() if hasattr(self, "nup") else ""
            port = None
            if mods_val:
                mp = Path(mods_val)
                cand = mp.parent if mp.name.lower() == "mods" else mp
                if is_port_folder(cand):
                    port = cand
            romfs = (port / "romfs") if port else None
            cache = IconCache(state_dir() / "icons", romfs, nup_val or None)
            if not cache.missing():
                self._party_icons_started = True
                return
            self._party_icons_started = True
            done_flag = [False]
            def _on_done():
                done_flag[0] = True
            cache.ensure(done=_on_done)
            sched = getattr(self, "_schedule_after", None)
            def _poll_icons():
                if done_flag[0]:
                    self.render_parties()
                elif getattr(cache, "_thread", None) and cache._thread.is_alive():
                    if callable(sched):
                        sched(350, _poll_icons)
            if callable(sched):
                sched(350, _poll_icons)
        except Exception:
            _LOG.debug("Party icon cache init skipped", exc_info=True)

    def party_health_check(self, ident):
        """Run Seed & Party Health Diagnostics and present a concise report."""
        from oot_rando.party_health import check_party_health
        report = check_party_health(self.party_library, ident)
        icons = {"ok": "[OK]", "warn": "[WARN]", "error": "[ERROR]"}
        lines = [icons.get(c["level"], "[INFO]") + " " + c["message"] for c in report["checks"]]
        title = "Party Health — " + (report.get("name") or ident[:8])
        body = '\n'.join(lines)
        has_issue = any(c["level"] in ("warn", "error") for c in report["checks"])
        if has_issue:
            messagebox.showwarning(title, body, parent=self.root)
        else:
            messagebox.showinfo(title, body, parent=self.root)

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
        if not initial or not initial.is_dir():
            from oot_rando.tracker.auto_tracker import default_port_save_roots, save_roots
            hookshot_root = mods.parent if mods.name.lower() == "mods" else None
            for cand in list(save_roots(hookshot_root, mods)) + list(default_port_save_roots()):
                if cand.is_dir():
                    initial = cand
                    break
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
            self.show_page('parties')
            self.show_notice('info', 'First keep the installed party',
                             'Keep it with its name and its save; you can then create or import another party.',
                             [('Keep the installed party…', self.capture_party)])
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
                self.notify('Party imported. Click Activate to play.')
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
                return self.party_library.activate(ident, address)
            self.run_job(job, self.party_opened)
        except Exception as error:
            self.error(error)

    def party_seed_dir(self, party):
        """The installed seed of a party, else its stored snapshot (its port folder vanished)."""
        live_seed = Path(party['mods']) / party['mod_name']
        if live_seed.is_dir():
            return live_seed
        snapshot_seed = self.party_library.bundle(party) / 'seed'
        if snapshot_seed.is_dir():
            return snapshot_seed
        return live_seed

    def party_opened(self, party):
        self.party_job_paused = False
        if not Path(party['mods']).exists():
            # Its port folder vanished (a Longshot update): follow the new build.
            resolved = self.resolve_longshot_mods(party['mods'])
            if resolved:
                try:
                    self.party_library.migrate_mods_directory(resolved, old_mods=party['mods'])
                    party = self.party_library.get(party['id'])
                except (OSError, ValueError) as error:
                    self.error(error)
        self.mods.set(party['mods'])
        self.save_path.set('')
        self.auto_save.set(True)
        self.ap_password.set('')
        self.ap_address.set(party.get('ap_address') or 'archipelago.gg:38281')
        self.slot.set('party-' + party['id'])
        self.use_artifact(self.party_seed_dir(party))
        self.start_turbo()
        self.render_parties()
        self.update_home()
        self.notify('Active party: ' + party['name'] + '. You can start the game.')

    def match_party(self, directory):
        self.party_context = None
        if self.parties_enabled.get() and self.party_library and self.party_library.active_id:
            party = self.party_library.get(self.party_library.active_id)
            resolved = Path(directory).resolve()
            live_seed = Path(party["mods"]) / party["mod_name"]
            candidates = {live_seed.resolve()}
            if (Path(party["mods"]) / "Merged_Zelda_Rando").is_dir() or not live_seed.is_dir():
                candidates.add((self.party_library.bundle(party) / "seed").resolve())
            if resolved in candidates:
                self.party_context = party
                self.slot.set("party-" + party["id"])
        if self.party_context is None and self.slot.get().startswith("party-"):
            self.slot.set("My game")

    def restore_party(self):
        if self.parties_enabled.get() and self.party_library and self.party_library.active_id:
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
        except Exception as error:
            self.error(error)
            return
        def delete():
            try:
                self.clear_notices()
                self.party_library.delete(ident)
                self.render_parties()
                self.notify(f'“{party["name"]}” removed. A copy remains in Parties/.deleted.')
            except Exception as error:
                self.error(error)
        self.show_notice('warn', f'Remove “{party["name"]}” from My Games?',
                         'A copy will remain in Parties/.deleted.', [('Remove', delete), ('Cancel', self.clear_notices)])

    def party_folder(self, ident):
        """Open the selected party's storage folder in the OS file manager."""
        try:
            open_in_file_manager(self.party_library.folder(ident))
        except Exception as error:
            self.error(error)

    def _using_real_generator(self) -> bool:
        from oot_rando.gui import generation_worker as _gw
        from oot_rando.randomizer import randomizer_core as _rc
        for fn in (generate_isolated, _gw.generate_isolated, _gw.run_in_process, _rc.generate):
            mod = getattr(fn, "__module__", "") or ""
            if not mod.startswith("oot_rando."):
                return False
        return True

    def generate_party(self, nup, mods, settings, continuing=None):
        if not self.parties_enabled.get():
            return self.generate_plain(nup, mods, settings)
        if not self.parties_ready() or not self.ensure_party_destination(mods):
            return
        initial = continuing["name"] + " (updated)" if continuing else settings.seed
        name = self.party_display_name(initial) if continuing else (
            self.party_name.get().strip() or self.party_display_name(initial))
        if not name:
            return
        settings.validate_supported()
        self.party_library._name(name)
        real_gen = self._using_real_generator()
        if real_gen:
            from oot_rando.randomizer.mods_folder import validate_nup_file
            validate_nup_file(nup)
        saves = self.party_destination(mods)
        if saves is None:
            return
        mods, saves = self.party_library.preflight_generation(
            name, mods, saves, settings, continuing=bool(continuing),
        )
        from oot_rando.party_health import preflight_mods_operation
        pf_mods = preflight_mods_operation(
            mods,
            source_paths=[nup] if (real_gen and Path(nup).exists()) else (),
            allow_missing_parents=True,
        )
        if not pf_mods["ok"]:
            raise ValueError("; ".join(pf_mods["errors"]))
        pf_stage = preflight_mods_operation(data_dir() / "party-generation", allow_missing_parents=True)
        if not pf_stage["ok"]:
            raise ValueError("; ".join(pf_stage["errors"]))
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
            from oot_rando.path_safety import fs_path
            with tempfile.TemporaryDirectory(prefix="g-", dir=fs_path(staging)) as temporary:
                temporary = Path(temporary)
                staging_mods = temporary / TITLE
                if continuing:
                    from oot_rando.parties import copy_verified
                    copy_verified(Path(continuing['mods']) / continuing['mod_name'], staging_mods / continuing['mod_name'])
                installed = generate_isolated(nup, staging_mods, settings, temporary / 'archive', progress)
                party = self.party_library.create(name, installed, mods, saves, ap_address=address,
                                                  continue_active=bool(continuing), tracker=manual)
            return self.party_library.activate(party['id'], outgoing_address)
        def done(party):
            self.party_generated(party, continued=bool(continuing))
            if continuing:
                self.offer_save_migration(self.artifact_manifest, previous)
        self.run_job(job, done)

    def generate_plain(self, nup, mods, settings):
        "Install the seed straight into the mods folder (My Games off)."
        from oot_rando.gui.randomizer_gui import ARCHIVE
        from oot_rando.randomizer.mods_folder import preflight_plain_generation, qol_seed_warning
        real_gen = self._using_real_generator()
        mods = preflight_plain_generation(
            nup, mods, settings, archive=ARCHIVE,
            check_nup=real_gen, check_game_closed=real_gen,
        )
        def job(progress):
            installed = generate_isolated(nup, mods, settings, ARCHIVE, progress)
            return installed, installed
        def done(result):
            directory, installed = result
            previous = self.artifact_manifest
            self.use_artifact(directory)
            warning = qol_seed_warning(Path(installed).parent)
            open_tracker = ('Open the tracker', lambda: self.show_page('tracker'))
            if warning:
                self.show_notice('warn', 'Seed installed in ' + str(installed), warning, [open_tracker])
            else:
                self.notify('Seed installed in ' + str(installed) + '. Start a new game with it.', open_tracker)
            self.offer_save_migration(self.artifact_manifest, previous)
        self.run_job(job, done)

    def party_generated(self, party, continued=False):
        self.party_opened(party)
        self.show_page('parties')
        text = ('The save was carried over. The original party stays available.' if continued
                else 'Start a new save in the game.')
        self.notify(f'“{party["name"]}” is installed. ' + text)
