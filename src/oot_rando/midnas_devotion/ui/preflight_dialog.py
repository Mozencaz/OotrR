from __future__ import annotations

import os
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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

from oot_rando.midnas_devotion.core.config import AppConfig, StandaloneMod
from oot_rando.midnas_devotion.core.preflight import (
    SUPPORTED_ARCHIVE_EXTS,
    ArchiveHandle,
    PreflightReport,
    inspect_archive,
    install_archive_variant,
    list_archive_variants,
    run_advanced_checks,
    sanitize_mod_name,
)

# Column indices
COL_STATUS = 0
COL_OVERLAP = 1
COL_PATH = 2
COL_MOD_SZ = 3
COL_VAN_SZ = 4
COL_RESTBL = 5
COL_MARGIN = 6
TECH_COLS = (COL_MOD_SZ, COL_VAN_SZ, COL_RESTBL, COL_MARGIN)


def _extract_archive_paths(mime_data) -> List[str]:
    if not mime_data or not mime_data.hasUrls():
        return []
    paths: List[str] = []
    for url in mime_data.urls():
        if url.isLocalFile():
            p = url.toLocalFile()
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in SUPPORTED_ARCHIVE_EXTS:
                paths.append(p)
    return paths


def _classify_row(st: str) -> Tuple[str, str, QColor, QColor]:
    """Returns (severity, friendly_label, text_color, row_bg_tint)."""
    if st == "EXEFS":
        return ("unsupported", "✕ Code Mod (Unsupported)", QColor("#e1bee7"), QColor("#2a1436"))
    if "DECOMPRESS_ERR" in st:
        return ("danger", "✕ Unreadable .zs File", QColor("#ef9a9a"), QColor("#381414"))
    if st == "RESTBL_111":
        return ("danger", "✕ Clobbers v1.1.1 RESTBL", QColor("#ef9a9a"), QColor("#381414"))
    if "OVER_RESTBL" in st or "SUB_OVER" in st:
        lbl = "✕ Overlap + Over Memory" if "OVERLAP" in st else (
            "✕ Subfile Over Memory" if "SUB_OVER" in st else "✕ Over Memory Limit"
        )
        return ("danger", lbl, QColor("#ef9a9a"), QColor("#381414"))
    if st == "RESTBL_OLD":
        return ("warn", "⚠ Old v1.0.0 Table (Ignored)", QColor("#ffcc80"), QColor("#33220d"))
    if "TIGHT" in st and "OVERLAP" in st:
        return ("warn", "⚠ Overlap + Tight Memory", QColor("#ffcc80"), QColor("#33220d"))
    if "TIGHT" in st:
        lbl = "⚠ Subfile Tight Memory" if "SUB_" in st else "⚠ Tight Memory Margin"
        return ("warn", lbl, QColor("#ffcc80"), QColor("#33220d"))
    if "OVERLAP" in st:
        return ("warn", "⚠ File Conflict", QColor("#ffcc80"), QColor("#33220d"))
    if "AUTO_MERGE_BARS" in st:
        return ("ok", "⇄ Auto-Merged Audio", QColor("#81d4fa"), QColor("#102938"))
    if st == "SUB_OK":
        return ("ok", "✓ Safe (Subfile)", QColor("#a5d6a7"), QColor("#122616"))
    return ("ok", "✓ Safe", QColor("#a5d6a7"), QColor("#122616"))


def _pill_style(kind: str) -> str:
    palettes = {
        "ok": ("#16331b", "#2e7d32", "#a5d6a7"),
        "warn": ("#3a2409", "#ef6c00", "#ffcc80"),
        "danger": ("#3d1313", "#c62828", "#ef9a9a"),
        "unsupported": ("#2e1340", "#8e24aa", "#e1bee7"),
        "neutral": ("#252525", "#444444", "#bdbdbd"),
    }
    bg, border, fg = palettes.get(kind, palettes["neutral"])
    return (
        f"background: {bg}; border: 1px solid {border}; color: {fg}; "
        "border-radius: 5px; padding: 6px 10px; font-weight: bold;"
    )


from oot_rando.native_dialogs import ask_open_file


class PreflightDialog(QDialog):
    def __init__(
        self,
        cfg: AppConfig,
        enabled_standalone: List[StandaloneMod],
        parent=None,
        initial_archive: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.enabled_standalone = enabled_standalone
        self.archive: Optional[ArchiveHandle] = None
        self.current_report: Optional[PreflightReport] = None
        self.installed_mod_name: Optional[str] = None

        self.setWindowTitle("Check & Add Mod Archive (.zip / .7z / .rar)")
        self.resize(1120, 700)
        self.setAcceptDrops(True)
        self._build_ui()

        if initial_archive:
            QTimer.singleShot(0, lambda p=initial_archive: self.load_archive(p))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # File selector row
        file_row = QHBoxLayout()
        self.arc_edit = QLineEdit()
        self.arc_edit.setReadOnly(True)
        self.arc_edit.setPlaceholderText("Drop a .zip, .7z, or .rar here — or click Browse Archive...")
        browse_btn = QPushButton("Browse Archive...")
        browse_btn.clicked.connect(self._browse_archive)
        file_row.addWidget(QLabel("Archive:"))
        file_row.addWidget(self.arc_edit, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # Variant & mod name row
        meta_row = QHBoxLayout()
        self.variant_combo = QComboBox()
        self.variant_combo.currentIndexChanged.connect(self._run_standard_inspection)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Folder name for Extra Mods list")
        meta_row.addWidget(QLabel("Variant:"))
        meta_row.addWidget(self.variant_combo, 1)
        meta_row.addWidget(QLabel("Mod Name:"))
        meta_row.addWidget(self.name_edit, 1)
        layout.addLayout(meta_row)

        # Summary Card (plain-English verdict + 4 traffic-light pills)
        self.summary_card = QFrame()
        self.summary_card.setFrameShape(QFrame.Shape.StyledPanel)
        self.summary_card.setStyleSheet(
            "QFrame { background: #232323; border: 1px solid #3c3c3c; border-radius: 6px; }"
        )
        card_lay = QVBoxLayout(self.summary_card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(8)

        self.verdict_title = QLabel("Drop or select a mod archive to check compatibility")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        self.verdict_title.setFont(title_font)
        self.verdict_title.setWordWrap(True)

        self.verdict_desc = QLabel(
            "Checks whether a mod can safely sit standalone next to your main game setup without conflicts or crashes."
        )
        self.verdict_desc.setWordWrap(True)
        self.verdict_desc.setStyleSheet("border: none; color: #cccccc;")

        card_lay.addWidget(self.verdict_title)
        card_lay.addWidget(self.verdict_desc)

        pills_row = QHBoxLayout()
        pills_row.setSpacing(8)
        self.pill_exefs = QLabel("Code Mod: —")
        self.pill_overlap = QLabel("Conflicts: —")
        self.pill_restbl = QLabel("Memory Table: —")
        self.pill_sizes = QLabel("Crash / Size Risk: —")
        for pill in (self.pill_exefs, self.pill_overlap, self.pill_restbl, self.pill_sizes):
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setStyleSheet(_pill_style("neutral"))
            pills_row.addWidget(pill, 1)
        card_lay.addLayout(pills_row)
        layout.addWidget(self.summary_card)

        # Controls row: Advanced check + view filters
        ctrl_row = QHBoxLayout()
        self.adv_btn = QPushButton("Run Deep Check (Memory Margins + Packed Subfiles)")
        self.adv_btn.setEnabled(False)
        self.adv_btn.clicked.connect(self._run_advanced)

        self.auto_adv_cb = QCheckBox("Auto-run Deep Check")
        self.only_issues_cb = QCheckBox("Show only issues")
        self.only_issues_cb.toggled.connect(self._refresh_table_visibility)
        self.tech_details_cb = QCheckBox("Show technical byte details")
        self.tech_details_cb.setChecked(False)
        self.tech_details_cb.toggled.connect(self._apply_column_visibility)

        ctrl_row.addWidget(self.adv_btn)
        ctrl_row.addWidget(self.auto_adv_cb)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.only_issues_cb)
        ctrl_row.addWidget(self.tech_details_cb)
        layout.addLayout(ctrl_row)

        # Results table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Result",
                "Conflicts With",
                "File Path",
                "Mod Size",
                "Vanilla Size",
                "RESTBL Limit",
                "Margin (Mod / Van)",
            ]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_OVERLAP, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_PATH, QHeaderView.ResizeMode.Stretch)
        for col in TECH_COLS:
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)
        self._apply_column_visibility()

        # Action row
        btn_row = QHBoxLayout()
        self.counts_lbl = QLabel("")
        self.counts_lbl.setStyleSheet("color: #aaaaaa;")
        btn_row.addWidget(self.counts_lbl, 1)
        self.install_btn = QPushButton("Add to Extra Mods")
        self.install_btn.setEnabled(False)
        self.install_btn.setStyleSheet(
            "QPushButton { background: #2e7d32; color: #ffffff; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #388e3c; }"
            "QPushButton:disabled { background: #3a3a3a; color: #888888; }"
        )
        self.install_btn.clicked.connect(self._install_mod)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.install_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _extract_archive_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if _extract_archive_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = _extract_archive_paths(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.load_archive(paths[0])

    def _apply_column_visibility(self) -> None:
        show_tech = self.tech_details_cb.isChecked()
        for col in TECH_COLS:
            self.table.setColumnHidden(col, not show_tech)

    def _refresh_table_visibility(self) -> None:
        if self.current_report is not None:
            self._render_table(self.current_report)

    def _close_archive(self) -> None:
        if self.archive is not None:
            self.archive.close()
            self.archive = None

    def done(self, result: int) -> None:
        self._close_archive()
        super().done(result)

    def closeEvent(self, event) -> None:
        self._close_archive()
        super().closeEvent(event)

    def _browse_archive(self) -> None:
        start_dir = os.path.expanduser("~/Downloads")
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~")
        path = ask_open_file(
            "Select Mod Archive",
            start_dir,
            qt_filter="Mod Archives (*.zip *.7z *.rar);;ZIP (*.zip);;7-Zip (*.7z);;RAR (*.rar)",
            qt_parent=self,
        )
        if path:
            self.load_archive(path)

    def load_archive(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            return
        self._close_archive()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.archive = ArchiveHandle(path)
            variants, _ = list_archive_variants(self.archive)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self._close_archive()
            QMessageBox.critical(self, "Archive Open Failed", str(exc))
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        self.arc_edit.setText(path)
        self.variant_combo.blockSignals(True)
        self.variant_combo.clear()
        if variants:
            for v in variants:
                label = v if v else "(Archive Root)"
                self.variant_combo.addItem(label, v)
        else:
            self.variant_combo.addItem("(No romfs/ folder found)", "")
        self.variant_combo.blockSignals(False)

        self._run_standard_inspection()

    def _run_standard_inspection(self) -> None:
        if not self.archive:
            return
        variant = self.variant_combo.currentData() or ""
        suggested = os.path.basename(variant) if variant else os.path.splitext(os.path.basename(self.archive.path))[0]
        self.name_edit.setText(sanitize_mod_name(suggested))

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = inspect_archive(self.archive, self.cfg, variant, self.enabled_standalone)
            if self.auto_adv_cb.isChecked():
                run_advanced_checks(self.archive, self.cfg, variant, report)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Inspection Failed", str(exc))
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        self.current_report = report
        self._render_report(report)

    def _run_advanced(self) -> None:
        if not self.archive or not self.current_report:
            return
        variant = self.variant_combo.currentData() or ""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            run_advanced_checks(self.archive, self.cfg, variant, self.current_report)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Deep Check Failed", str(exc))
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        self._render_report(self.current_report)

    @staticmethod
    def _fmt_margin(m_mod: Optional[int], m_van: Optional[int]) -> str:
        if m_mod is None:
            return "-"
        s_mod = f"{m_mod:+,}"
        if m_van is None:
            return s_mod
        return f"{s_mod} / {m_van:+,}"

    def _render_report(self, report: PreflightReport) -> None:
        exefs_n = sum(1 for r in report.rows if r.status == "EXEFS")
        overlap_rows = [r for r in report.rows if "OVERLAP" in r.status]
        rstb_111_n = sum(1 for r in report.rows if r.status == "RESTBL_111")
        rstb_old_n = sum(1 for r in report.rows if r.status == "RESTBL_OLD")
        over_n = sum(1 for r in report.rows if "OVER_RESTBL" in r.status or "SUB_OVER" in r.status)
        tight_n = sum(1 for r in report.rows if "TIGHT" in r.status)
        dec_err_n = sum(1 for r in report.rows if "DECOMPRESS_ERR" in r.status)
        safe_n = sum(1 for r in report.rows if r.status in ("OK", "SUB_OK", "AUTO_MERGE_BARS"))
        issue_n = len(report.rows) - safe_n

        # 1. Update 4 traffic-light pills
        if exefs_n:
            self.pill_exefs.setText(f"✕ Code Mod ({exefs_n} file(s))")
            self.pill_exefs.setStyleSheet(_pill_style("unsupported"))
        else:
            self.pill_exefs.setText("✓ No Code Mods")
            self.pill_exefs.setStyleSheet(_pill_style("ok"))

        auto_bars_rows = [r for r in report.rows if "AUTO_MERGE_BARS" in r.status]
        if overlap_rows:
            owners = sorted({o for r in overlap_rows for o in r.overlap_with})
            self.pill_overlap.setText(f"⚠ {len(overlap_rows)} Conflict(s)")
            self.pill_overlap.setToolTip("Collides with: " + ", ".join(owners))
            self.pill_overlap.setStyleSheet(_pill_style("warn"))
        elif auto_bars_rows:
            self.pill_overlap.setText(f"⇄ {len(auto_bars_rows)} Auto-Merged Audio")
            self.pill_overlap.setToolTip("Shared .bars audio table(s) touch different tracks and merge automatically on build.")
            self.pill_overlap.setStyleSheet(_pill_style("ok"))
        else:
            self.pill_overlap.setText("✓ No File Conflicts")
            self.pill_overlap.setToolTip("")
            self.pill_overlap.setStyleSheet(_pill_style("ok"))

        if rstb_111_n:
            self.pill_restbl.setText("✕ Clobbers v1.1.1 Table")
            self.pill_restbl.setStyleSheet(_pill_style("danger"))
        elif rstb_old_n:
            self.pill_restbl.setText("⚠ Ignored v1.0.0 Table")
            self.pill_restbl.setStyleSheet(_pill_style("warn"))
        else:
            self.pill_restbl.setText("✓ No Table Conflict")
            self.pill_restbl.setStyleSheet(_pill_style("ok"))

        if over_n or dec_err_n:
            self.pill_sizes.setText(f"✕ {over_n + dec_err_n} Size/Read Risk")
            self.pill_sizes.setStyleSheet(_pill_style("danger"))
        elif tight_n:
            self.pill_sizes.setText(f"⚠ {tight_n} Tight Margin(s)")
            self.pill_sizes.setStyleSheet(_pill_style("warn"))
        else:
            suffix = "" if report.advanced_ran else " (Basic)"
            self.pill_sizes.setText(f"✓ Sizes Safe{suffix}")
            self.pill_sizes.setStyleSheet(_pill_style("ok"))

        # 2. Update plain-English summary card
        has_hard_danger = bool(rstb_111_n or over_n or dec_err_n)
        if report.verdict == "UNSUPPORTED":
            self._set_card_theme("#2a1436", "#8e24aa", "#e1bee7")
            self.verdict_title.setText("✕ NOT SUPPORTED ON LONGSHOT")
            self.verdict_desc.setText(
                "This archive contains Switch code-mod files (exefs/) that stock Longshot cannot load yet. Skip this one for now."
            )
            self.install_btn.setEnabled(False)
        elif not report.rows:
            self._set_card_theme("#33220d", "#ef6c00", "#ffcc80")
            self.verdict_title.setText("⚠ NO MOD FILES FOUND")
            self.verdict_desc.setText(
                "No romfs/ folder was found under this variant. Try choosing a different variant above or check the archive manually."
            )
            self.install_btn.setEnabled(False)
        elif has_hard_danger:
            self._set_card_theme("#381414", "#c62828", "#ef9a9a")
            self.verdict_title.setText("✕ NOT SAFE AS A DROP-IN MOD")
            reasons = []
            if rstb_111_n:
                reasons.append("it ships a v1.1.1 ResourceSizeTable that will overwrite Merged_Zelda_Rando's table")
            if over_n:
                reasons.append(f"{over_n} file(s) exceed memory table limits and can crash the game")
            if dec_err_n:
                reasons.append(f"{dec_err_n} file(s) could not be decompressed cleanly")
            self.verdict_desc.setText(
                "Do not drop this straight into mods/: " + "; ".join(reasons) + ". Needs a merge or RESTBL bump first."
            )
            self.install_btn.setEnabled(True)
        elif report.verdict == "NEEDS_ATTENTION":
            self._set_card_theme("#33220d", "#ef6c00", "#ffcc80")
            self.verdict_title.setText("⚠ CAUTION — REVIEW BEFORE INSTALLING")
            notes = []
            if overlap_rows:
                owners = sorted({o for r in overlap_rows for o in r.overlap_with})
                notes.append(f"replaces {len(overlap_rows)} file(s) already used by {', '.join(owners)}")
            if rstb_old_n:
                notes.append("includes an old v1.0.0 memory table that Longshot 1.1.1 ignores")
            if tight_n:
                notes.append(f"{tight_n} file(s) have tighter memory headroom than vanilla")
            self.verdict_desc.setText("Worth checking first: " + "; ".join(notes) + ".")
            self.install_btn.setEnabled(True)
        else:
            self._set_card_theme("#122b16", "#2e7d32", "#a5d6a7")
            self.verdict_title.setText("✓ SAFE TO DROP IN STANDALONE")
            extra = (
                f" Deep check also verified memory margins and {report.subfiles_scanned} packed subfile(s)."
                if report.advanced_ran
                else " Click 'Run Deep Check' if this mod contains models or packed actor files."
            )
            self.verdict_desc.setText(
                f"All {len(report.rows)} file(s) passed with zero conflicts and safe memory sizes. Click 'Add to Extra Mods' to stage it."
                + extra
            )
            self.install_btn.setEnabled(True)

        self.adv_btn.setEnabled(not report.advanced_ran)
        self.counts_lbl.setText(
            f"Summary: {safe_n} safe  ·  {issue_n} issue(s)  ·  {len(report.rows)} total item(s)"
            + (f"  ({report.subfiles_scanned} subfiles scanned)" if report.advanced_ran else "")
        )
        self._render_table(report)

    def _set_card_theme(self, bg: str, border: str, title_fg: str) -> None:
        self.summary_card.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 2px solid {border}; border-radius: 6px; }}"
        )
        self.verdict_title.setStyleSheet(f"border: none; color: {title_fg};")

    def _render_table(self, report: PreflightReport) -> None:
        self.table.setRowCount(0)
        only_issues = self.only_issues_cb.isChecked()

        for row in report.rows:
            sev, friendly_label, fg_color, bg_color = _classify_row(row.status)
            if only_issues and sev == "ok":
                continue

            r = self.table.rowCount()
            self.table.insertRow(r)

            items = [
                QTableWidgetItem(friendly_label),
                QTableWidgetItem(", ".join(row.overlap_with) if row.overlap_with else "None"),
                QTableWidgetItem(row.rel_path),
                QTableWidgetItem(f"{row.mod_size:,}" if row.mod_size else "-"),
                QTableWidgetItem(f"{row.van_size:,}" if row.van_size else "-"),
                QTableWidgetItem(f"{row.restbl_size:,}" if row.restbl_size is not None else "None"),
                QTableWidgetItem(self._fmt_margin(row.margin_mod, row.margin_van)),
            ]

            bold_font = QFont()
            bold_font.setBold(True)
            items[COL_STATUS].setFont(bold_font)
            items[COL_STATUS].setForeground(QBrush(fg_color))
            items[COL_STATUS].setToolTip(f"Raw code: {row.status}")

            bg_brush = QBrush(bg_color)
            for col_idx, item in enumerate(items):
                item.setBackground(bg_brush)
                self.table.setItem(r, col_idx, item)

    def _install_mod(self) -> None:
        if not self.archive or not self.current_report:
            return
        all_warnings = self.current_report.warnings + self.current_report.advanced_warnings
        if self.current_report.verdict == "NEEDS_ATTENTION":
            res = QMessageBox.warning(
                self,
                "Preflight Warnings",
                "This archive flagged issues:\n\n• "
                + "\n• ".join(all_warnings)
                + "\n\nAdd it to Extra Mods anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if res != QMessageBox.StandardButton.Yes:
                return

        mod_name = sanitize_mod_name(self.name_edit.text())
        variant = self.variant_combo.currentData() or ""
        try:
            dst = install_archive_variant(self.archive, variant, mod_name, self.cfg)
        except Exception as exc:
            QMessageBox.critical(self, "Install Failed", str(exc))
            return

        self.installed_mod_name = os.path.basename(dst)
        QMessageBox.information(
            self,
            "Mod Added",
            f"Added '{self.installed_mod_name}' to your Extra Mods list.\n\n"
            "Make sure it's checked in Step 3, then click Apply & Build in Step 4.",
        )
        self.accept()
