from __future__ import annotations

import os
import subprocess
from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from oot_rando.midnas_devotion.core.config import StandaloneMod, clean_subprocess_env


def _human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


class ModFilesDialog(QDialog):
    """Plain-English file inspector for an installed/staged standalone extra mod."""

    def __init__(
        self,
        mod: StandaloneMod,
        conflicts: Dict[str, List[str]],
        auto_merged: Dict[str, List[str]] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.mod = mod
        self.conflicts = conflicts
        self.auto_merged = auto_merged or {}
        self.setWindowTitle(f"Inspect Mod Files — {mod.name}")
        self.resize(960, 580)
        self._build_ui()
        self._populate_table()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # Header summary card
        card = QFrame()
        card.setObjectName("modInfoCard")
        has_conflicts = bool(self.conflicts)
        if has_conflicts:
            card.setStyleSheet(
                "QFrame#modInfoCard { background: #33220d; border: 1px solid #ef6c00; border-radius: 7px; }"
            )
            title_color = "#ffcc80"
            sub_color = "#ffe0b2"
        else:
            card.setStyleSheet(
                "QFrame#modInfoCard { background: #122b16; border: 1px solid #2e7d32; border-radius: 7px; }"
            )
            title_color = "#a5d6a7"
            sub_color = "#cfe8d1"

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(4)

        origin_labels = {
            "live": "Live Game Folder",
            "staged": "Added Extra Mod (Workspace)",
            "disabled": "Disabled Mod (Workspace)",
        }
        origin_txt = origin_labels.get(self.mod.origin, self.mod.origin)

        total_bytes = 0
        romfs_root = os.path.join(self.mod.source_path, "romfs")
        for rel in self.mod.rel_files:
            p = os.path.join(romfs_root, rel)
            if os.path.isfile(p):
                total_bytes += os.path.getsize(p)

        title = QLabel(
            f"{'⚠' if has_conflicts else '✓'}  {self.mod.name}   "
            f"({self.mod.file_count} file(s) · {_human_size(total_bytes)})"
        )
        tf = QFont()
        tf.setPointSize(11)
        tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet(f"border: none; color: {title_color};")

        if has_conflicts:
            owners = sorted({o for lst in self.conflicts.values() for o in lst})
            status_txt = (
                f"Shares {len(self.conflicts)} file(s) with: {', '.join(owners)}.  "
                f"Location: {origin_txt}"
            )
        else:
            status_txt = f"No file conflicts with your main game setup or other checked extra mods.  Location: {origin_txt}"

        sub = QLabel(status_txt)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"border: none; color: {sub_color};")

        path_lbl = QLabel(f"Folder: {self.mod.source_path}")
        path_lbl.setStyleSheet("border: none; color: #b0bec5; font-size: 11px;")
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        card_lay.addWidget(title)
        card_lay.addWidget(sub)
        card_lay.addWidget(path_lbl)
        root.addWidget(card)

        # Filter bar
        filt_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter files by name or path…")
        self.search_edit.textChanged.connect(self._populate_table)

        self.only_conflicts_cb = QCheckBox("Show only conflicts")
        self.only_conflicts_cb.setEnabled(has_conflicts)
        self.only_conflicts_cb.toggled.connect(self._populate_table)

        filt_row.addWidget(self.search_edit, 1)
        filt_row.addWidget(self.only_conflicts_cb)
        root.addLayout(filt_row)

        # File table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Status", "Conflicts With", "File Size", "RomFS File Path"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        # Footer buttons
        foot = QHBoxLayout()
        open_btn = QPushButton("Open Mod Folder")
        open_btn.clicked.connect(self._open_folder)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        foot.addWidget(open_btn)
        foot.addStretch(1)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        q = self.search_edit.text().strip().lower()
        only_conf = self.only_conflicts_cb.isChecked()
        romfs_root = os.path.join(self.mod.source_path, "romfs")

        bold_font = QFont()
        bold_font.setBold(True)

        for rel in self.mod.rel_files:
            owners = self.conflicts.get(rel, [])
            auto_owners = self.auto_merged.get(rel, [])
            if only_conf and not owners:
                continue
            if q and q not in rel.lower() and not any(q in o.lower() for o in owners):
                continue

            full_p = os.path.join(romfs_root, rel)
            sz_txt = _human_size(os.path.getsize(full_p)) if os.path.isfile(full_p) else "-"

            r = self.table.rowCount()
            self.table.insertRow(r)

            if owners:
                st_item = QTableWidgetItem("⚠ Conflict")
                st_item.setForeground(QBrush(QColor("#ffcc80")))
                bg = QBrush(QColor("#33220d"))
                col_txt = ", ".join(owners)
            elif auto_owners:
                st_item = QTableWidgetItem("⇄ Auto-Merged Audio")
                st_item.setForeground(QBrush(QColor("#81d4fa")))
                bg = QBrush(QColor("#102938"))
                col_txt = "Auto-merges with " + ", ".join(auto_owners)
            else:
                st_item = QTableWidgetItem("✓ Safe")
                st_item.setForeground(QBrush(QColor("#a5d6a7")))
                bg = QBrush(QColor("#122616"))
                col_txt = "None"
            st_item.setFont(bold_font)

            items = [
                st_item,
                QTableWidgetItem(col_txt),
                QTableWidgetItem(sz_txt),
                QTableWidgetItem(rel),
            ]
            for c, item in enumerate(items):
                item.setBackground(bg)
                self.table.setItem(r, c, item)

    def _open_folder(self) -> None:
        if os.path.isdir(self.mod.source_path):
            from oot_rando.paths import open_in_file_manager; open_in_file_manager(self.mod.source_path, env=clean_subprocess_env())
