"""Per-file mod contents and conflict inspector dialog for Midna's Devotion."""
from __future__ import annotations

import os
from typing import Dict, List, Optional

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
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from oot_rando.midnas_devotion.core.config import StandaloneMod, UI_MERGE_EXTS, clean_subprocess_env
from oot_rando.midnas_devotion.core.formats import BARS_EXTS
from oot_rando.paths import open_in_file_manager


def _human_size(num_bytes: int) -> str:
    """Format a byte count into B / KB / MB for display in the inspector table."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def _auto_merge_label(rel_path: str) -> str:
    """Return an accurate auto-merge category label for a relative romfs path."""
    low = rel_path.replace("\\", "/").lower()
    if low.endswith(BARS_EXTS):
        return "⇄ Auto-Merged Audio"
    if "resourcesizetable" in low:
        return "⇄ Auto-Merged Table"
    if low.startswith("mals/"):
        return "⇄ Auto-Merged Dialogue"
    if low.endswith(UI_MERGE_EXTS):
        return "⇄ Auto-Merged UI"
    return "⇄ Auto-Merged"


class ModFilesDialog(QDialog):
    """Plain-English file inspector for an installed, staged, or linked mod."""

    def __init__(
        self,
        mod: StandaloneMod,
        conflicts: Dict[str, List[str]],
        auto_merged: Optional[Dict[str, List[str]]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.mod = mod
        self.conflicts = conflicts
        self.auto_merged = auto_merged or {}
        self._cfg = getattr(parent, "cfg", None)
        self._plain = bool(getattr(parent, "_plain_ui", False))
        self.setWindowTitle(f"Inspect Mod Files — {mod.name}")
        self.resize(960, 580)
        self._build_ui()
        self._populate_table()

    def _resolve_file(self, rel: str) -> str:
        """Locate a mod file on disk, falling back to stashed ``bars_originals`` when available."""
        if self._cfg is not None:
            return self._cfg.resolve_mod_file_path(self.mod, rel)
        return os.path.join(self.mod.source_path, "romfs", *rel.replace("\\", "/").split("/"))

    def _build_ui(self) -> None:
        """Construct summary banner, filter controls, file table, and footer actions."""
        root = QVBoxLayout(self)
        root.setSpacing(10)

        card = QFrame()
        card.setObjectName("modInfoCard")
        has_conflicts = bool(self.conflicts)
        if self._plain:
            if has_conflicts:
                card.setStyleSheet(
                    "QFrame#modInfoCard { background: #fdf3e3; border: 1px solid #dfaa5c; border-radius: 7px; }"
                )
                title_color = "#7a4d0e"
                sub_color = "#6e4c1b"
            else:
                card.setStyleSheet(
                    "QFrame#modInfoCard { background: #eaf4ed; border: 1px solid #8ec29e; border-radius: 7px; }"
                )
                title_color = "#1f5439"
                sub_color = "#2f5e46"
        else:
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
            "linked": "Mod Library / Linked Folder",
        }
        origin_txt = origin_labels.get(self.mod.origin, self.mod.origin)

        total_bytes = 0
        for rel in self.mod.rel_files:
            p = self._resolve_file(rel)
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
        path_lbl.setStyleSheet(
            "border: none; color: #5c665d; font-size: 11px;"
            if self._plain
            else "border: none; color: #b0bec5; font-size: 11px;"
        )
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        card_lay.addWidget(title)
        card_lay.addWidget(sub)
        card_lay.addWidget(path_lbl)
        root.addWidget(card)

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
        """Populate the file table according to the search filter and conflict-only toggle."""
        self.table.setRowCount(0)
        q = self.search_edit.text().strip().lower()
        only_conf = self.only_conflicts_cb.isChecked()

        bold_font = QFont()
        bold_font.setBold(True)

        for rel in self.mod.rel_files:
            owners = self.conflicts.get(rel, [])
            auto_owners = self.auto_merged.get(rel, [])
            if only_conf and not owners:
                continue
            if q and q not in rel.lower() and not any(q in o.lower() for o in owners + auto_owners):
                continue

            full_p = self._resolve_file(rel)
            sz_txt = _human_size(os.path.getsize(full_p)) if os.path.isfile(full_p) else "-"

            r = self.table.rowCount()
            self.table.insertRow(r)

            if owners:
                st_item = QTableWidgetItem("⚠ Conflict")
                st_item.setForeground(QBrush(QColor("#8a5308" if self._plain else "#ffcc80")))
                bg = QBrush(QColor("#fdf3e3" if self._plain else "#33220d"))
                col_txt = ", ".join(owners)
            elif auto_owners:
                st_item = QTableWidgetItem(_auto_merge_label(rel))
                st_item.setForeground(QBrush(QColor("#1b5e8a" if self._plain else "#81d4fa")))
                bg = QBrush(QColor("#e7f2fa" if self._plain else "#102938"))
                col_txt = "Auto-merges with " + ", ".join(auto_owners)
            else:
                st_item = QTableWidgetItem("✓ Safe")
                st_item.setForeground(QBrush(QColor("#1f5439" if self._plain else "#a5d6a7")))
                bg = QBrush(QColor("#eaf4ed" if self._plain else "#122616"))
                col_txt = "None"
            st_item.setFont(bold_font)

            items = [
                st_item,
                QTableWidgetItem(col_txt),
                QTableWidgetItem(sz_txt),
                QTableWidgetItem(rel),
            ]
            row_fg = QBrush(QColor("#1f2a24" if self._plain else "#f1f5f9"))
            for c, item in enumerate(items):
                item.setBackground(bg)
                if c != 0:
                    item.setForeground(row_fg)
                self.table.setItem(r, c, item)

    def _open_folder(self) -> None:
        """Open the inspected mod's directory in the OS file manager."""
        if os.path.isdir(self.mod.source_path):
            try:
                open_in_file_manager(self.mod.source_path, env=clean_subprocess_env())
            except OSError as exc:
                QMessageBox.warning(self, "Could Not Open Folder", str(exc))
