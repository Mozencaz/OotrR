from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional, Tuple

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from oot_rando.midnas_devotion.core.config import AppConfig, auto_detect_from_folder, default_workspace_dir
from oot_rando.native_dialogs import ask_directory, ask_open_file

CREATABLE_MIDNA_FOLDERS: Tuple[Tuple[str, str, str], ...] = (
    ("live_mods_dir", "Live Mods Folder", "mods"),
    ("backup_dir", "Mod Library / Backups", "mods_backup"),
    ("uninstalled_seeds_dir", "Extra Seeds Folder", "seeds-uninstalled"),
    ("workspace_dir", "Manager Workspace", "ootmodman"),
)


def find_missing_creatable_folders(paths: Dict[str, str]) -> List[Tuple[str, str, str, str]]:
    "Return [(key, label, default_dirname, current_path)] for creatable Midna folders not on disk."
    missing: List[Tuple[str, str, str, str]] = []
    for key, label, default_name in CREATABLE_MIDNA_FOLDERS:
        cur = str(paths.get(key, "") or "").strip()
        if not cur or not os.path.isdir(cur):
            missing.append((key, label, default_name, cur))
    return missing


def create_missing_folders_in_dir(
    missing: Iterable[Tuple[str, str, str, str]],
    base_dir: str,
    *,
    synced_keys: Iterable[str] = (),
) -> Dict[str, str]:
    "Create each missing folder inside base_dir (or at its synced path if Setup-managed)."
    base_abs = os.path.abspath(os.path.expanduser(base_dir))
    synced = set(synced_keys)
    created: Dict[str, str] = {}
    missing_list = list(missing)
    base_name_low = os.path.basename(base_abs).lower()
    for key, _label, default_name, cur in missing_list:
        if key in synced and cur:
            target = os.path.abspath(os.path.expanduser(cur))
        elif len(missing_list) == 1 and base_name_low == default_name.lower():
            target = base_abs
        else:
            target = os.path.join(base_abs, default_name)
        os.makedirs(target, exist_ok=True)
        created[key] = target
    return created


def suggest_base_dir(paths: Dict[str, str]) -> str:
    for key in ("live_mods_dir", "romfs_dir", "backup_dir", "workspace_dir"):
        raw = str(paths.get(key, "") or "").strip()
        if not raw:
            continue
        p = os.path.abspath(os.path.expanduser(raw))
        parent = os.path.dirname(p)
        if parent and os.path.isdir(parent):
            return parent
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def prompt_create_missing_folders(
    parent,
    paths: Dict[str, str],
    *,
    synced_keys: Iterable[str] = (),
    skip_label: str = "Not Now",
) -> Optional[Dict[str, str]]:
    "Ask whether to auto-create missing Midna folders in a user-chosen directory."
    missing = find_missing_creatable_folders(paths)
    if not missing:
        return {}

    lines = []
    for key, label, default_name, cur in missing:
        detail = cur if cur else f"(not set — will create '{default_name}')"
        lines.append(f"• {label}: {detail}")

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Missing Midna's Devotion Folders")
    box.setText(
        "Some Midna's Devotion folders are not present yet:\n\n"
        + "\n".join(lines)
        + "\n\nWould you like to auto-create them in a directory you choose?"
    )
    choose_btn = box.addButton("Choose Directory && Create…", QMessageBox.ButtonRole.AcceptRole)
    can_create_in_place = all(bool(cur) for _k, _l, _d, cur in missing)
    inplace_btn = (
        box.addButton("Create at Configured Paths", QMessageBox.ButtonRole.ActionRole)
        if can_create_in_place
        else None
    )
    skip_btn = box.addButton(skip_label, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(choose_btn)
    box.exec()
    clicked = box.clickedButton()
    if clicked is None or clicked == skip_btn:
        return None

    if inplace_btn is not None and clicked == inplace_btn:
        created: Dict[str, str] = {}
        try:
            for key, _label, _default_name, cur in missing:
                target = os.path.abspath(os.path.expanduser(cur))
                os.makedirs(target, exist_ok=True)
                created[key] = target
        except OSError as exc:
            QMessageBox.warning(parent, "Could Not Create Folders", str(exc))
            return None
        return created

    base_dir = ask_directory(
        "Choose Directory for Midna's Devotion Folders",
        suggest_base_dir(paths),
        qt_parent=parent,
    )
    if not base_dir:
        return None
    try:
        return create_missing_folders_in_dir(missing, base_dir, synced_keys=synced_keys)
    except OSError as exc:
        QMessageBox.warning(parent, "Could Not Create Folders", str(exc))
        return None


class SettingsDialog(QDialog):
    """User-friendly folder picker for every important directory (zero hardcoded paths)."""

    def __init__(self, cfg: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Folder & Path Settings")
        self.resize(820, 520)
        self.edits: Dict[str, QLineEdit] = {}
        self.badges: Dict[str, QLabel] = {}
        self._build_ui()
        self._load_from_cfg()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # Quick Auto-Fill card
        auto_card = QFrame()
        auto_card.setObjectName("autoCard")
        auto_card.setStyleSheet(
            "QFrame#autoCard { background: #1a242f; border: 1px solid #34526f; border-radius: 7px; }"
        )
        auto_lay = QHBoxLayout(auto_card)
        auto_lay.setContentsMargins(12, 10, 12, 10)
        auto_lay.setSpacing(10)

        auto_text = QVBoxLayout()
        auto_title = QLabel("Quick Setup: Auto-Fill from your Longshot Folder")
        tf = QFont()
        tf.setBold(True)
        auto_title.setFont(tf)
        auto_title.setStyleSheet("border: none; color: #e3f2fd;")
        auto_sub = QLabel(
            "Pick your main Longshot folder (or stable/v3.x.x folder) to automatically fill romfs, mods, backups, seeds, and the Longshot binary."
        )
        auto_sub.setWordWrap(True)
        auto_sub.setStyleSheet("border: none; color: #b0bec5; font-size: 11px;")
        auto_text.addWidget(auto_title)
        auto_text.addWidget(auto_sub)

        auto_btn = QPushButton("Auto-Fill from Folder…")
        auto_btn.setMinimumHeight(34)
        auto_btn.setStyleSheet(
            "QPushButton { background: #1976d2; color: #fff; font-weight: bold; padding: 0 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #1e88e5; }"
        )
        auto_btn.clicked.connect(self._auto_fill)

        auto_lay.addLayout(auto_text, 1)
        auto_lay.addWidget(auto_btn)
        root.addWidget(auto_card)

        self.rando_sync_lbl = QLabel()
        self.rando_sync_lbl.setWordWrap(True)
        self.rando_sync_lbl.setStyleSheet(
            "background: #162822; border: 1px solid #2e6b52; border-radius: 6px; "
            "color: #b9f6ca; padding: 7px 10px; font-size: 11px;"
        )
        self.rando_sync_lbl.setVisible(False)
        root.addWidget(self.rando_sync_lbl)

        # Individual customizable paths
        grid_card = QFrame()
        grid_card.setObjectName("gridCard")
        grid_card.setStyleSheet(
            "QFrame#gridCard { background: #212121; border: 1px solid #383838; border-radius: 7px; }"
        )
        grid = QGridLayout(grid_card)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)

        fields = [
            ("romfs_dir", "Base Game romfs/ *", "Folder containing Pack/ZsDic.pack.zs (required)", "dir"),
            ("live_mods_dir", "Live Mods Folder *", "Longshot's active mods/ folder (used in Live Mode)", "dir"),
            ("backup_dir", "Mod Library / Backups", "Holds Character mods, UI/visual mods, and archived Randomizer seeds", "dir"),
            ("uninstalled_seeds_dir", "Extra Seeds Folder", "Optional folder scanned for OoT_Randomizer_* seeds", "dir"),
            ("longshot_binary", "Longshot Executable", "Optional binary launched by the 'Play Longshot' button", "file"),
            ("workspace_dir", "Manager Workspace *", "Stores Test Mode builds, staged mods, and disabled mods", "dir"),
        ]

        for row_idx, (key, label, hint, kind) in enumerate(fields):
            lbl = QLabel(label)
            lf = QFont()
            lf.setBold(True)
            lbl.setFont(lf)
            lbl.setStyleSheet("border: none; color: #eceff1;")
            lbl.setToolTip(hint)

            edit = QLineEdit()
            edit.setPlaceholderText(hint)
            edit.textChanged.connect(self._update_badges)

            badge = QLabel("—")
            badge.setFixedWidth(24)
            badge.setStyleSheet("border: none; font-weight: bold;")

            browse_btn = QPushButton("Browse…")
            browse_btn.clicked.connect(lambda _=False, k=key, m=kind: self._browse_field(k, m))

            self.edits[key] = edit
            self.badges[key] = badge

            grid.addWidget(lbl, row_idx, 0)
            grid.addWidget(edit, row_idx, 1)
            grid.addWidget(badge, row_idx, 2)
            grid.addWidget(browse_btn, row_idx, 3)

        grid.setColumnStretch(1, 1)
        root.addWidget(grid_card, 1)

        # Footer info & actions
        foot = QHBoxLayout()
        saved_lbl = QLabel(f"Settings file: {self.cfg.settings_path}")
        saved_lbl.setStyleSheet("color: #9e9e9e; font-size: 11px;")

        self.create_missing_btn = QPushButton("Create Missing Folders…")
        self.create_missing_btn.setToolTip("Auto-create any missing Midna's Devotion folders in a directory you choose.")
        self.create_missing_btn.clicked.connect(self._create_missing_folders)

        reset_ws_btn = QPushButton("Default Workspace")
        reset_ws_btn.setToolTip(f"Reset workspace to {default_workspace_dir()}")
        reset_ws_btn.clicked.connect(lambda: self.edits["workspace_dir"].setText(default_workspace_dir()))

        save_btn = QPushButton("Save Folders")
        save_btn.setMinimumHeight(34)
        save_btn.setStyleSheet(
            "QPushButton { background: #2e7d32; color: #fff; font-weight: bold; padding: 0 16px; border-radius: 4px; }"
            "QPushButton:hover { background: #388e3c; }"
        )
        save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(34)
        cancel_btn.clicked.connect(self.reject)

        foot.addWidget(saved_lbl, 1)
        foot.addWidget(self.create_missing_btn)
        foot.addWidget(reset_ws_btn)
        foot.addWidget(save_btn)
        foot.addWidget(cancel_btn)
        root.addLayout(foot)

    def _load_from_cfg(self) -> None:
        self.edits["romfs_dir"].setText(self.cfg.romfs_dir)
        self.edits["live_mods_dir"].setText(self.cfg.live_mods_dir)
        self.edits["backup_dir"].setText(self.cfg.backup_dir)
        self.edits["uninstalled_seeds_dir"].setText(self.cfg.uninstalled_seeds_dir)
        self.edits["longshot_binary"].setText(self.cfg.longshot_binary)
        self.edits["workspace_dir"].setText(self.cfg.workspace_dir or default_workspace_dir())
        synced = sorted(getattr(self.cfg, "rando_synced_keys", set()))
        if synced:
            friendly = {
                "live_mods_dir": "Live Mods Folder",
                "romfs_dir": "Base Game romfs/",
                "longshot_binary": "Longshot Executable",
            }
            names = ", ".join(friendly.get(k, k) for k in synced)
            self.rando_sync_lbl.setText(
                f"Synced automatically from the main Randomizer's Setup tab: {names}. "
                "To change these paths, update MODS FOLDER in the Setup tab (it takes priority over this dialog)."
            )
            self.rando_sync_lbl.setVisible(True)
        else:
            self.rando_sync_lbl.setVisible(False)
        self._update_badges()

    def _current_paths_dict(self) -> Dict[str, str]:
        return {k: e.text().strip() for k, e in self.edits.items()}

    def _create_missing_folders(self) -> None:
        created = prompt_create_missing_folders(
            self,
            self._current_paths_dict(),
            synced_keys=getattr(self.cfg, "rando_synced_keys", set()),
            skip_label="Cancel",
        )
        if created:
            for key, path in created.items():
                if key in self.edits:
                    self.edits[key].setText(path)
            self._update_badges()

    def _auto_fill(self) -> None:
        start = os.path.dirname(self.edits["romfs_dir"].text()) if self.edits["romfs_dir"].text() else os.path.expanduser("~")
        folder = ask_directory("Select Longshot Folder", start, qt_parent=self)
        if not folder:
            return
        detected = auto_detect_from_folder(folder)
        for key, val in detected.items():
            if val:
                self.edits[key].setText(val)
        if not self.edits["workspace_dir"].text().strip():
            self.edits["workspace_dir"].setText(default_workspace_dir())
        self._update_badges()

    def _browse_field(self, key: str, kind: str) -> None:
        cur = self.edits[key].text().strip()
        start = cur if cur else os.path.expanduser("~")
        if kind == "file":
            path = ask_open_file("Select Executable", start, qt_parent=self)
        else:
            path = ask_directory("Select Folder", start, qt_parent=self)
        if path:
            self.edits[key].setText(path)

    def _update_badges(self) -> None:
        def set_b(key: str, ok: bool, warn: bool = False, tip: str = "") -> None:
            b = self.badges[key]
            if ok:
                b.setText("✓")
                b.setStyleSheet("border: none; font-weight: bold; color: #81c784;")
            elif warn:
                b.setText("⚠")
                b.setStyleSheet("border: none; font-weight: bold; color: #ffb74d;")
            else:
                b.setText("✕")
                b.setStyleSheet("border: none; font-weight: bold; color: #e57373;")
            b.setToolTip(tip)

        romfs = self.edits["romfs_dir"].text().strip()
        if romfs and os.path.isfile(os.path.join(romfs, "Pack", "ZsDic.pack.zs")):
            set_b("romfs_dir", True, tip="Valid romfs/ folder (ZsDic.pack.zs found).")
        else:
            set_b("romfs_dir", False, tip="Required: must contain Pack/ZsDic.pack.zs.")

        live_m = self.edits["live_mods_dir"].text().strip()
        if live_m and os.path.isdir(live_m):
            set_b("live_mods_dir", True, tip="Folder exists.")
        elif live_m:
            set_b("live_mods_dir", False, warn=True, tip="Folder does not exist yet (will be created when building).")
        else:
            set_b("live_mods_dir", False, warn=True, tip="Optional in Test Mode, required for Live Mode.")

        bkp = self.edits["backup_dir"].text().strip()
        set_b("backup_dir", bool(bkp and os.path.isdir(bkp)), warn=not bool(bkp), tip="Optional mod library / backups folder.")

        seeds = self.edits["uninstalled_seeds_dir"].text().strip()
        set_b("uninstalled_seeds_dir", bool(seeds and os.path.isdir(seeds)), warn=not bool(seeds), tip="Optional extra seeds folder.")

        lbin = self.edits["longshot_binary"].text().strip()
        set_b("longshot_binary", bool(lbin and os.path.isfile(lbin)), warn=not bool(lbin), tip="Optional Longshot executable.")

        ws = self.edits["workspace_dir"].text().strip()
        set_b("workspace_dir", bool(ws and os.path.isdir(ws)), warn=bool(ws and not os.path.isdir(ws)), tip="Workspace folder for Test Mode & staged mods.")
        if hasattr(self, "create_missing_btn"):
            missing = find_missing_creatable_folders(self._current_paths_dict())
            self.create_missing_btn.setEnabled(bool(missing))
            self.create_missing_btn.setText(
                f"Create Missing Folders ({len(missing)})…" if missing else "All Folders Ready"
            )

    def _save(self) -> None:
        romfs = self.edits["romfs_dir"].text().strip()
        ws = self.edits["workspace_dir"].text().strip() or default_workspace_dir()

        if not romfs or not os.path.isfile(os.path.join(romfs, "Pack", "ZsDic.pack.zs")):
            ans = QMessageBox.warning(
                self,
                "Base romfs/ Not Valid",
                "The Base Game romfs/ folder is missing Pack/ZsDic.pack.zs.\n"
                "Building and archive checking won't work until a valid romfs/ folder is chosen.\n\nSave anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        paths_now = self._current_paths_dict()
        paths_now["workspace_dir"] = ws
        if find_missing_creatable_folders(paths_now):
            created = prompt_create_missing_folders(
                self,
                paths_now,
                synced_keys=getattr(self.cfg, "rando_synced_keys", set()),
                skip_label="Save Without Creating",
            )
            if created:
                for key, path in created.items():
                    paths_now[key] = path
                    if key in self.edits:
                        self.edits[key].setText(path)
                ws = paths_now["workspace_dir"] or ws

        self.cfg.romfs_dir = romfs
        self.cfg.live_mods_dir = paths_now["live_mods_dir"]
        self.cfg.backup_dir = paths_now["backup_dir"]
        self.cfg.uninstalled_seeds_dir = paths_now["uninstalled_seeds_dir"]
        self.cfg.longshot_binary = self.edits["longshot_binary"].text().strip()
        self.cfg.workspace_dir = ws
        self.cfg.save_settings()
        # Re-apply main Randomizer Setup priority for any paths managed there
        self.cfg.sync_from_randomizer(persist=True)
        self.accept()
