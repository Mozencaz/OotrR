# Pre-build file overlap and conflict breakdown dialog for Midna Devotion.
from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class ConflictInspectorDialog(QDialog):
    def __init__(self, rows: List[Dict], parent=None, plain: bool = False) -> None:
        super().__init__(parent)
        self._rows = list(rows)
        self._plain = bool(plain)
        self.setWindowTitle("Pre-Build Conflict & Overlap Inspector")
        self.resize(860, 520)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        conflict_cnt = sum(1 for r in self._rows if r["status"] == "Conflict")
        auto_cnt = sum(1 for r in self._rows if r["status"] == "Auto-Merged")
        hdr = QLabel(
            f"Pre-Build Breakdown: {conflict_cnt} Conflict(s), {auto_cnt} Auto-Merged Asset(s)"
        )
        hf = QFont()
        hf.setBold(True)
        hf.setPointSize(11)
        hdr.setFont(hf)
        lay.addWidget(hdr)

        sub = QLabel(
            "Shows colliding romfs/ assets (.bfres, .blarc, .bntx, .bars, messages) across enabled mods and which mod wins."
        )
        sub.setWordWrap(True)
        lay.addWidget(sub)

        filt = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter by path, asset type, or mod name…")
        self.search_box.textChanged.connect(self._populate)
        self.only_conflicts = QCheckBox("Conflicts only")
        self.only_conflicts.toggled.connect(self._populate)
        filt.addWidget(self.search_box, 1)
        filt.addWidget(self.only_conflicts)
        lay.addLayout(filt)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Status", "Type", "Asset Path", "Mods Touching File", "Winner / Resolution"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

    def _populate(self) -> None:
        q = self.search_box.text().strip().lower()
        only_c = self.only_conflicts.isChecked()
        filtered = []
        for r in self._rows:
            if only_c and r["status"] != "Conflict":
                continue
            hay = " ".join([r["status"], r["category"], r["path"], " ".join(r["owners"]), r["winner"]]).lower()
            if q and q not in hay:
                continue
            filtered.append(r)

        self.table.setRowCount(len(filtered))
        for i, r in enumerate(filtered):
            is_conf = r["status"] == "Conflict"
            status_item = QTableWidgetItem("⚠ Conflict" if is_conf else "⇄ Auto-Merged")
            status_item.setForeground(QColor("#ffb74d" if is_conf else "#81d4fa"))
            self.table.setItem(i, 0, status_item)
            self.table.setItem(i, 1, QTableWidgetItem(r["category"]))
            self.table.setItem(i, 2, QTableWidgetItem(r["path"]))
            self.table.setItem(i, 3, QTableWidgetItem(", ".join(r["owners"])))
            win_item = QTableWidgetItem(r["winner"])
            win_item.setToolTip(r.get("detail", ""))
            self.table.setItem(i, 4, win_item)
