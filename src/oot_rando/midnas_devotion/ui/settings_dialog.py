from __future__ import annotations

import os
from typing import Dict

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
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

    def _auto_fill(self) -> None:
        start = os.path.dirname(self.edits["romfs_dir"].text()) if self.edits["romfs_dir"].text() else os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Select Longshot Folder", start)
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
        start = cur if (cur and os.path.exists(cur)) else os.path.expanduser("~")
        if kind == "file":
            path, _ = QFileDialog.getOpenFileName(self, "Select Executable", start)
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Folder", start)
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
        set_b("workspace_dir", bool(ws), tip="Workspace folder for Test Mode & staged mods.")

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

        self.cfg.romfs_dir = romfs
        self.cfg.live_mods_dir = self.edits["live_mods_dir"].text().strip()
        self.cfg.backup_dir = self.edits["backup_dir"].text().strip()
        self.cfg.uninstalled_seeds_dir = self.edits["uninstalled_seeds_dir"].text().strip()
        self.cfg.longshot_binary = self.edits["longshot_binary"].text().strip()
        self.cfg.workspace_dir = ws
        self.cfg.save_settings()
        # Re-apply main Randomizer Setup priority for any paths managed there
        self.cfg.sync_from_randomizer(persist=True)
        self.accept()
