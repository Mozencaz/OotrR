"""Main PySide6 window for Midna's Devotion (standalone and embedded inside the OoT Randomizer).

Provides the 4-step mod management workflow, dual-theme rendering (Mozencaz Light
and Dark Araragi Midna), drag-and-drop archive preflighting, load-order management,
and asynchronous mod-merge execution via ``BuildWorker``.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from oot_rando.midnas_devotion.core.config import (
    MANAGED_MOD_NAMES,
    AppConfig,
    CoreModEntry,
    SeedInfo,
    StandaloneMod,
    _norm_path_key,
    clean_subprocess_env,
    pretty_mod_name,
)
from oot_rando.paths import open_in_file_manager
from oot_rando.midnas_devotion.core.merger import BuildOptions, run_build
from oot_rando.midnas_devotion.core.preflight import (
    SUPPORTED_ARCHIVE_EXTS,
    ArchiveHandle,
    install_archive_to_dir,
    list_archive_variants,
    sanitize_mod_name,
)
from oot_rando.midnas_devotion.ui.midna_dance import MidnaDanceWidget
from oot_rando.midnas_devotion.ui.mod_files_dialog import ModFilesDialog
from oot_rando.midnas_devotion.ui.preflight_dialog import PreflightDialog
from oot_rando.midnas_devotion.ui.settings_dialog import (
    SettingsDialog,
    find_missing_creatable_folders,
    prompt_create_missing_folders,
)
from oot_rando.native_dialogs import ask_directory, ask_open_file
from oot_rando.midnas_devotion.ui.ui_theme import (
    MidnaInstructionsDialog,
    THEME_ARARAGI,
    THEME_MOZENCAZ,
    UiExperienceDialog,
    app_palette,
    app_stylesheet,
    central_stylesheet,
    status_color,
)


def _find_asset(filename: str) -> Optional[str]:
    """Resolve a bundled Midna UI asset file path, returning None if absent."""
    from oot_rando.midnas_devotion.launcher import resolve_asset
    resolved = resolve_asset(filename)
    return resolved if (resolved and os.path.isfile(resolved)) else None


def _find_app_icon() -> Optional[str]:
    """Locate the bundled application window icon (``icon.png``)."""
    return _find_asset("icon.png")


class BackdropWidget(QWidget):
    """Central widget painting either plain parchment or a cached, dimmed Midna artwork backdrop."""

    def __init__(self, image_path: Optional[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap(image_path) if image_path and os.path.isfile(image_path) else QPixmap()
        self._scaled_cache: Optional[QPixmap] = None
        self._scaled_size: QSize = QSize()
        self._plain_mode: bool = False

    def set_plain_mode(self, plain: bool) -> None:
        """Switch between plain Mozencaz parchment and dimmed dark Midna artwork."""
        self._plain_mode = plain
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = self.rect()
        if self._plain_mode:
            painter.fillRect(rect, QColor("#f2eee3"))
            super().paintEvent(event)
            return
        painter.fillRect(rect, QColor(16, 20, 26))
        if not self._pixmap.isNull() and rect.width() > 0 and rect.height() > 0:
            # Cache the smooth-scaled backdrop per viewport size to avoid rescaling on every hover repaint.
            if self._scaled_cache is None or self._scaled_size != rect.size():
                self._scaled_size = QSize(rect.size())
                self._scaled_cache = self._pixmap.scaled(
                    self._scaled_size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            scaled = self._scaled_cache
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.fillRect(rect, QColor(12, 16, 22, 112))
        super().paintEvent(event)


def _extract_archive_paths(mime_data) -> List[str]:
    """Extract supported local mod archive paths from a Qt drag-and-drop payload."""
    if not mime_data or not mime_data.hasUrls():
        return []
    paths: List[str] = []
    for url in mime_data.urls():
        if url.isLocalFile():
            p = url.toLocalFile()
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in SUPPORTED_ARCHIVE_EXTS:
                paths.append(p)
    return paths


class DropZoneFrame(QFrame):
    """Dashed drag-and-drop card for .zip / .7z / .rar mod archives."""

    files_dropped = Signal(list)
    browse_clicked = Signal()

    IDLE_STYLE = (
        "QFrame#dropZone { background: rgba(22, 32, 44, 150); border: 2px dashed #4a6b8a; border-radius: 7px; }"
        "QFrame#dropZone:hover { background: rgba(31, 42, 54, 175); border-color: #64b5f6; }"
    )
    ACTIVE_STYLE = (
        "QFrame#dropZone { background: rgba(22, 51, 74, 180); border: 2px dashed #64b5f6; border-radius: 7px; }"
    )
    PLAIN_IDLE_STYLE = (
        "QFrame#dropZone { background: #f7f3ea; border: 2px dashed #cfc5ad; border-radius: 7px; }"
        "QFrame#dropZone:hover { background: #efe9db; border-color: #2f7a55; }"
    )
    PLAIN_ACTIVE_STYLE = (
        "QFrame#dropZone { background: #e4efe7; border: 2px dashed #2f7a55; border-radius: 7px; }"
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._plain_mode: bool = False
        self._drag_active: bool = False
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setStyleSheet(self.IDLE_STYLE)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_lbl = QLabel("Drop any mod archive here to check & add")
        t_font = QFont()
        t_font.setBold(True)
        self.title_lbl.setFont(t_font)
        self.title_lbl.setStyleSheet("border: none; color: #e3f2fd;")

        self.sub_lbl = QLabel("Supports .zip, .7z, and .rar (UI, textures, models, BGM, etc.)")
        self.sub_lbl.setStyleSheet("border: none; color: #90a4ae; font-size: 11px;")

        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.sub_lbl)

        self.browse_btn = QPushButton("Browse File…")
        self.browse_btn.setMinimumHeight(32)
        self.browse_btn.clicked.connect(self.browse_clicked.emit)

        lay.addLayout(text_col, 1)
        lay.addWidget(self.browse_btn)

    def set_plain_mode(self, plain: bool) -> None:
        self._plain_mode = plain
        self.sub_lbl.setStyleSheet(
            "border: none; color: #6c766d; font-size: 11px;"
            if plain
            else "border: none; color: #90a4ae; font-size: 11px;"
        )
        self.set_drag_active(self._drag_active)

    def set_drag_active(self, active: bool) -> None:
        self._drag_active = active
        if self._plain_mode:
            self.setStyleSheet(self.PLAIN_ACTIVE_STYLE if active else self.PLAIN_IDLE_STYLE)
            if active:
                self.title_lbl.setText("Release to check mod compatibility!")
                self.title_lbl.setStyleSheet("border: none; color: #2f7a55;")
            else:
                self.title_lbl.setText("Drop any mod archive here to check & add")
                self.title_lbl.setStyleSheet("border: none; color: #1f2a24;")
            return
        self.setStyleSheet(self.ACTIVE_STYLE if active else self.IDLE_STYLE)
        if active:
            self.title_lbl.setText("Release to check mod compatibility!")
            self.title_lbl.setStyleSheet("border: none; color: #64b5f6;")
        else:
            self.title_lbl.setText("Drop any mod archive here to check & add")
            self.title_lbl.setStyleSheet("border: none; color: #e3f2fd;")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _extract_archive_paths(event.mimeData()):
            self.set_drag_active(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if _extract_archive_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.set_drag_active(False)
        paths = _extract_archive_paths(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)


class BuildWorker(QThread):
    """Background worker thread running ``core.merger.run_build`` without blocking the UI."""

    log_line = Signal(str)
    progress_val = Signal(int)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, cfg: AppConfig, opts: BuildOptions) -> None:
        super().__init__()
        self.cfg = cfg
        self.opts = opts

    def run(self) -> None:
        try:
            run_build(
                self.cfg,
                self.opts,
                log=lambda msg: self.log_line.emit(msg),
                progress=lambda pct: self.progress_val.emit(pct),
            )
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


def _friendly_step_from_log(line: str) -> Optional[str]:
    """Translate numbered ``run_build`` log lines into user-facing progress captions."""
    s = line.strip()
    if s.startswith("1."):
        return "Setting up playable character…"
    if s.startswith("2."):
        return "Applying randomizer seed…"
    if s.startswith("3."):
        return "Merging UI, model & audio mods…"
    if s.startswith("4."):
        return "Applying NPC compatibility fixes…"
    if s.startswith("5."):
        return "Merging in-game text and hints…"
    if s.startswith("6."):
        return "Updating game memory table…"
    if s.startswith("7."):
        return "Syncing standalone mods…"
    if s.startswith("8."):
        return "Auto-merging shared BGM / audio tables…"
    if s.startswith("Done!"):
        return "All done — your mod setup is ready!"
    return None


def _friendly_seed_label(seed: SeedInfo, is_newest: bool) -> str:
    """Format a ``SeedInfo`` entry for the Step 1 dropdown with timestamp and newest badge."""
    ts = datetime.fromtimestamp(seed.mtime).strftime("%b %d, %H:%M")
    short_id = seed.name.replace("OoT_Randomizer_", "Seed ")
    prefix = "★ Newest · " if is_newest else ""
    return f"{prefix}{short_id}   ({ts})"


def _make_step_card(step_num: int, title: str, subtitle: str) -> Tuple[QFrame, QVBoxLayout]:
    """Create a numbered step card container with themeable badge, heading, divider, and body layout."""
    card = QFrame()
    card.setObjectName(f"stepCard{step_num}")
    card.setStyleSheet(
        f"QFrame#stepCard{step_num} {{ "
        "background: rgba(26, 30, 38, 150); border: 1px solid #3a3a3a; border-radius: 8px; }"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(14, 12, 14, 12)
    outer.setSpacing(10)

    hdr = QHBoxLayout()
    hdr.setSpacing(10)

    badge = QLabel(f"STEP {step_num}")
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        "background: rgba(21, 101, 192, 195); color: #ffffff; font-weight: bold; font-size: 11px; "
        "padding: 4px 9px; border-radius: 4px; border: none;"
    )
    badge.setFixedHeight(24)

    text_col = QVBoxLayout()
    text_col.setSpacing(1)
    title_lbl = QLabel(title)
    tf = QFont()
    tf.setPointSize(11)
    tf.setBold(True)
    title_lbl.setFont(tf)
    title_lbl.setStyleSheet("border: none; color: #f5f5f5;")

    sub_lbl = QLabel(subtitle)
    sub_lbl.setStyleSheet("border: none; color: #9e9e9e; font-size: 11px;")
    sub_lbl.setWordWrap(True)

    text_col.addWidget(title_lbl)
    text_col.addWidget(sub_lbl)

    hdr.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
    hdr.addLayout(text_col, 1)
    outer.addLayout(hdr)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("background: #333333; max-height: 1px; border: none;")
    outer.addWidget(sep)

    body = QVBoxLayout()
    body.setSpacing(8)
    card.setMinimumWidth(0)
    card._step_num = step_num  # type: ignore[attr-defined]
    card._step_badge = badge  # type: ignore[attr-defined]
    card._step_title = title_lbl  # type: ignore[attr-defined]
    card._step_sub = sub_lbl  # type: ignore[attr-defined]
    card._step_sep = sep  # type: ignore[attr-defined]
    outer.addLayout(body, 1)
    return card, body


class MainWindow(QMainWindow):
    """Primary Midna's Devotion interface supporting both Mozencaz Light and Dark Araragi themes."""

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.seeds: List[SeedInfo] = []
        self.standalone_mods: List[StandaloneMod] = []
        self.char_mods: List[CoreModEntry] = []
        self.library_visual_mods: List[CoreModEntry] = []
        self.worker: Optional[BuildWorker] = None
        self._pending_refresh: bool = False
        self._ui_ready: bool = False
        self._initial_restored: bool = False
        self._status_tone: str = "neutral"
        self._step_cards: List[QFrame] = []
        self._section_labels: List[QLabel] = []
        self._theme_change_callback = None

        self.setWindowTitle("Midna's Devotion — Ocarina of Time Mod Manager & Merger (for Longshot + Mozencaz's Randomizer)")
        icon_path = _find_app_icon()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1220, 840)
        self.setAcceptDrops(True)
        self._build_ui()
        self.apply_ui_theme(self.cfg.effective_ui_theme, persist=False)
        self._onboarding_running: bool = False
        self._onboarding_scheduled: bool = False
        self._migration_notice_shown: bool = False
        self._initial_setup_prompted: bool = False
        self._relocation_prompted: bool = False
        self.refresh_all()

        if not getattr(self.cfg, "embedded_in_randomizer", False):
            self.schedule_startup_onboarding(delay_ms=200)

    def _build_ui(self) -> None:
        central = BackdropWidget(_find_asset("backdrop.png"))
        self.central_widget = central
        central.setObjectName("backdropCentral")
        central.setStyleSheet(
            "QWidget#backdropCentral, QWidget#backdropCentral QLabel { color: #FFFFFF; background-color: transparent; } "
            "QWidget#backdropCentral QFrame { background-color: rgba(22, 26, 33, 145); color: #FFFFFF; } "
            "QWidget#backdropCentral QListWidget, QWidget#backdropCentral QComboBox, QWidget#backdropCentral QTextEdit { "
            "  background-color: rgba(16, 20, 26, 155); "
            "  color: #FFFFFF; "
            "} "
            "QWidget#backdropCentral QComboBox QAbstractItemView { "
            "  background-color: rgba(22, 26, 33, 235); "
            "  color: #FFFFFF; "
            "  selection-background-color: rgba(43, 108, 176, 220); "
            "  selection-color: #FFFFFF; "
            "} "
        )
        self.setCentralWidget(central)
        outer_root = QVBoxLayout(central)
        outer_root.setContentsMargins(0, 0, 0, 0)
        outer_root.setSpacing(0)
        self._view_stack = QStackedWidget()
        self._view_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        outer_root.addWidget(self._view_stack)

        self._main_page = QWidget()
        self._main_page.setObjectName("midnaMainPage")
        self._main_page.setStyleSheet("QWidget#midnaMainPage { background: transparent; }")
        root = QVBoxLayout(self._main_page)
        self._main_root_layout = root
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        # --- Top Mode & Folder Bar ---
        top_frame = QFrame()
        self.top_frame = top_frame
        top_frame.setObjectName("topBar")
        top_frame.setMinimumWidth(0)
        top_frame.setStyleSheet(
            "QFrame#topBar { background: rgba(22, 26, 33, 155); border: 1px solid #353535; border-radius: 7px; }"
        )
        top_bar = QHBoxLayout(top_frame)
        top_bar.setContentsMargins(10, 8, 10, 8)
        top_bar.setSpacing(8)

        self.mode_badge = QLabel()
        self.mode_btn = QPushButton()
        self.mode_btn.clicked.connect(self._toggle_mode)

        self.path_label = QLabel()
        self.path_label.setMinimumWidth(0)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.path_label.setStyleSheet("border: none; color: #9e9e9e; font-size: 11px;")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.instructions_btn = QPushButton("Instructions…")
        self.instructions_btn.setToolTip("View step-by-step instructions for using Midna's Devotion.")
        self.instructions_btn.clicked.connect(self._open_instructions)

        self.ui_style_btn = QPushButton("UI Style…")
        self.ui_style_btn.setToolTip("Switch between Mozencaz' Default UI Experience and Arararagi's UI Experience.")
        self.ui_style_btn.clicked.connect(self._open_ui_style_picker)

        self.folders_btn = QPushButton("Folders ▾")
        self.folders_btn.setToolTip("Open UserModLibrary, ArchivedSeeds, staged_for_generation, Merged_Zelda_Rando, or mods/.")
        self.folders_btn.clicked.connect(self._open_quick_folders_menu)

        self.settings_btn = QPushButton("Configure Folders…")
        self.settings_btn.clicked.connect(self._open_settings)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_all)

        top_bar.addWidget(self.mode_badge)
        top_bar.addWidget(self.mode_btn)
        top_bar.addWidget(self.path_label, 1)
        top_bar.addWidget(self.instructions_btn)
        top_bar.addWidget(self.ui_style_btn)
        top_bar.addWidget(self.folders_btn)
        top_bar.addWidget(self.settings_btn)
        top_bar.addWidget(self._refresh_btn)
        root.addWidget(top_frame)

        # Party-aware status / one-click re-merge banner (Midna-scoped twilight accent)
        self._party_stage_dir = ""
        self.party_banner = QFrame()
        self.party_banner.setObjectName("partyBanner")
        self.party_banner.setStyleSheet(
            "QFrame#partyBanner { background: rgba(20, 44, 52, 200); border: 1px solid #26c6da; border-radius: 7px; }"
        )
        pb_lay = QHBoxLayout(self.party_banner)
        pb_lay.setContentsMargins(12, 8, 12, 8)
        pb_lay.setSpacing(10)
        self.party_banner_lbl = QLabel("")
        self.party_banner_lbl.setWordWrap(True)
        self.party_banner_lbl.setStyleSheet("border: none; background: transparent; color: #e0f7fa; font-weight: bold;")
        self.party_banner_merge_btn = QPushButton("Re-Apply & Merge for Active Seed")
        self.party_banner_merge_btn.setStyleSheet(
            "QPushButton { background: #00838f; color: #ffffff; border: 1px solid #4dd0e1; border-radius: 5px; padding: 5px 12px; font-weight: bold; }"
            "QPushButton:hover { background: #0097a7; }"
        )
        self.party_banner_merge_btn.clicked.connect(self._on_party_banner_remerge)
        self.party_banner_dismiss_btn = QPushButton("Dismiss")
        self.party_banner_dismiss_btn.clicked.connect(lambda: self.party_banner.setVisible(False))
        pb_lay.addWidget(self.party_banner_lbl, 1)
        pb_lay.addWidget(self.party_banner_merge_btn)
        pb_lay.addWidget(self.party_banner_dismiss_btn)
        self.party_banner.setVisible(False)
        root.addWidget(self.party_banner)

        # --- Middle Area: Left (Step 1 + Step 2) | Right (Step 3) ---
        mid_split = QSplitter(Qt.Orientation.Horizontal)
        mid_split.setChildrenCollapsible(False)
        mid_split.setMinimumWidth(0)

        left_col = QWidget()
        left_col.setMinimumWidth(0)
        left_col.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        left_lay = QVBoxLayout(left_col)
        left_lay.setContentsMargins(0, 0, 4, 0)
        left_lay.setSpacing(10)

        # STEP 1: Character & Randomizer Seed
        step1_card, s1 = _make_step_card(
            1,
            "Choose Character & Randomizer Seed",
            "Pick who you want to play as and which Randomizer seed to load.",
        )
        self._step_cards.append(step1_card)

        char_lbl = QLabel("Playable Character")
        char_lbl.setStyleSheet("border: none; font-weight: bold; color: #cfd8dc;")
        self._section_labels.append(char_lbl)
        s1.addWidget(char_lbl)

        char_row = QHBoxLayout()
        char_row.setSpacing(6)
        self.char_combo = QComboBox()
        self.char_combo.setMinimumWidth(0)
        self.char_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.char_combo.setMinimumContentsLength(12)
        self.char_combo.setMinimumHeight(30)
        self.char_combo.currentIndexChanged.connect(self._on_step1_changed)
        self.btn_add_char = QPushButton("+ Add…")
        self.btn_add_char.setMinimumHeight(30)
        self.btn_add_char.setToolTip("Import a character mod archive or link an existing mod folder.")
        self.btn_add_char.clicked.connect(self._show_add_char_menu)
        self.btn_rm_char = QPushButton("✕")
        self.btn_rm_char.setFixedWidth(30)
        self.btn_rm_char.setMinimumHeight(30)
        self.btn_rm_char.setToolTip("Remove imported copy or unlink custom folder.")
        self.btn_rm_char.clicked.connect(self._remove_selected_char_mod)
        char_row.addWidget(self.char_combo, 1)
        char_row.addWidget(self.btn_add_char)
        char_row.addWidget(self.btn_rm_char)
        s1.addLayout(char_row)

        s1.addSpacing(4)
        seed_lbl = QLabel("Randomizer Seed (newest is starred at the top)")
        seed_lbl.setStyleSheet("border: none; font-weight: bold; color: #cfd8dc;")
        self._section_labels.append(seed_lbl)
        s1.addWidget(seed_lbl)

        seed_row = QHBoxLayout()
        seed_row.setSpacing(6)
        self.seed_combo = QComboBox()
        self.seed_combo.setMinimumWidth(0)
        self.seed_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.seed_combo.setMinimumContentsLength(12)
        self.seed_combo.setMinimumHeight(30)
        self.seed_combo.currentIndexChanged.connect(self._on_step1_changed)
        self.btn_add_seed = QPushButton("Browse…")
        self.btn_add_seed.setMinimumHeight(30)
        self.btn_add_seed.setToolTip("Pick a Randomizer seed folder from anywhere on your PC.")
        self.btn_add_seed.clicked.connect(self._browse_seed_folder)
        seed_row.addWidget(self.seed_combo, 1)
        seed_row.addWidget(self.btn_add_seed)
        s1.addLayout(seed_row)
        left_lay.addWidget(step1_card)

        # STEP 2: Pick & Add Visual / UI / Model Mods (unlimited!)
        step2_card, s2 = _make_step_card(
            2,
            "Browse & Add Mods",
            "Add any UI, model, texture, or audio mods from your library or PC to your active list on the right.",
        )
        self._step_cards.append(step2_card)

        lib_lbl = QLabel("Available in Your Mod Library (double-click or click Add →)")
        lib_lbl.setStyleSheet("border: none; font-weight: bold; color: #cfd8dc;")
        self._section_labels.append(lib_lbl)
        s2.addWidget(lib_lbl)

        self.visual_lib_list = QListWidget()
        self.visual_lib_list.setMinimumHeight(95)
        self.visual_lib_list.setSpacing(2)
        self.visual_lib_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.visual_lib_list.itemDoubleClicked.connect(lambda _it: self._add_selected_library_visuals())
        self.visual_lib_list.itemSelectionChanged.connect(self._update_visual_picker_buttons)
        s2.addWidget(self.visual_lib_list, 1)

        vis_btn_row = QHBoxLayout()
        vis_btn_row.setSpacing(6)
        self.btn_add_lib_vis = QPushButton("Add Selected to Mod List →")
        self.btn_add_lib_vis.setMinimumHeight(32)
        self.btn_add_lib_vis.setStyleSheet(
            "QPushButton { background: rgba(21, 101, 192, 195); color: #ffffff; font-weight: bold; border-radius: 4px; padding: 0 12px; }"
            "QPushButton:hover { background: rgba(25, 118, 210, 200); }"
            "QPushButton:disabled { background: rgba(44, 48, 54, 140); color: #777777; }"
        )
        self.btn_add_lib_vis.clicked.connect(self._add_selected_library_visuals)
        vis_btn_row.addWidget(self.btn_add_lib_vis, 1)
        s2.addLayout(vis_btn_row)

        custom_vis_row = QHBoxLayout()
        custom_vis_row.setSpacing(6)
        self.btn_import_vis_arc = QPushButton("+ Import Mod Archive…")
        self.btn_import_vis_arc.setToolTip("Extract a .zip, .7z, or .rar mod and add it to the Active Mod List on the right.")
        self.btn_import_vis_arc.clicked.connect(self._import_visual_archive_to_list)
        self.btn_link_vis_dir = QPushButton("+ Link Mod Folder…")
        self.btn_link_vis_dir.setToolTip("Add any unzipped mod folder directly to the Active Mod List on the right.")
        self.btn_link_vis_dir.clicked.connect(self._link_visual_folder_to_list)
        custom_vis_row.addWidget(self.btn_import_vis_arc, 1)
        custom_vis_row.addWidget(self.btn_link_vis_dir, 1)
        s2.addLayout(custom_vis_row)

        self.cb_prefer_rando_logo = QCheckBox("Keep Randomizer title screen logo when merging UI mods")
        self.cb_prefer_rando_logo.toggled.connect(self._update_setup_summary)
        s2.addWidget(self.cb_prefer_rando_logo)

        left_lay.addWidget(step2_card, 1)

        # STEP 3: Unified Mod List (Visual, Audio & Extra Mods)
        right_col = QWidget()
        right_col.setMinimumWidth(0)
        right_col.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        right_outer = QVBoxLayout(right_col)
        right_outer.setContentsMargins(4, 0, 0, 0)
        right_outer.setSpacing(0)

        step3_card, s3 = _make_step_card(
            3,
            "Active Mod List",
            "Check everything you want enabled. Green = safe · Blue = auto-merged · Amber = conflict. Lower items take priority if two UI mods overlap.",
        )
        self._step_cards.append(step3_card)

        self.drop_zone = DropZoneFrame()
        self.drop_zone.files_dropped.connect(self._handle_dropped_archives)
        self.drop_zone.browse_clicked.connect(self._browse_and_preflight)
        s3.addWidget(self.drop_zone)

        self.overlap_card = QFrame()
        self.overlap_card.setStyleSheet(
            "QFrame { background: rgba(18, 43, 22, 165); border: 1px solid #2e7d32; border-radius: 5px; }"
        )
        ov_lay = QVBoxLayout(self.overlap_card)
        ov_lay.setContentsMargins(10, 8, 10, 8)
        ov_lay.setSpacing(2)
        self.overlap_title = QLabel()
        ov_font = QFont()
        ov_font.setBold(True)
        self.overlap_title.setFont(ov_font)
        self.overlap_detail = QLabel()
        self.overlap_detail.setWordWrap(True)
        ov_lay.addWidget(self.overlap_title)
        ov_lay.addWidget(self.overlap_detail)
        s3.addWidget(self.overlap_card)

        self.mod_list = QListWidget()
        self.mod_list.setMinimumHeight(110)
        self.mod_list.viewport().setAutoFillBackground(False)
        self.mod_list.viewport().setStyleSheet("background: transparent;")
        self.mod_list.setSpacing(2)
        self.mod_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mod_list.customContextMenuRequested.connect(self._show_mod_context_menu)
        self.mod_list.itemChanged.connect(self._on_mod_toggled)
        self.mod_list.currentItemChanged.connect(lambda _c, _p: self._update_mod_action_buttons())
        s3.addWidget(self.mod_list, 1)

        # Mod List Management Toolbar (includes ▲ / ▼ load order controls)
        mod_mgmt_row = QHBoxLayout()
        mod_mgmt_row.setSpacing(6)

        self.btn_move_up = QPushButton("▲")
        self.btn_move_up.setFixedWidth(30)
        self.btn_move_up.setToolTip("Move mod up (lower priority).")
        self.btn_move_up.clicked.connect(lambda: self._move_selected_mod(-1))

        self.btn_move_dn = QPushButton("▼")
        self.btn_move_dn.setFixedWidth(30)
        self.btn_move_dn.setToolTip("Move mod down (higher priority when stacking overlapping mods).")
        self.btn_move_dn.clicked.connect(lambda: self._move_selected_mod(+1))

        self.btn_inspect_mod = QPushButton("Inspect Files…")
        self.btn_inspect_mod.setToolTip("See every file inside the selected mod and check for conflicts.")
        self.btn_inspect_mod.clicked.connect(self._inspect_selected_mod)

        self.btn_overlap_inspector = QPushButton("Overlaps…")
        self.btn_overlap_inspector.setToolTip("Pre-build conflict and overlap breakdown across all checked mods.")
        self.btn_overlap_inspector.clicked.connect(self._open_overlap_inspector)

        self.btn_presets = QPushButton("Loadouts ▾")
        self.btn_presets.setToolTip("Save or apply named mod loadouts (enabled mods, priority order, and character).")
        self.btn_presets.clicked.connect(self._open_presets_menu)

        self.btn_rename_mod = QPushButton("Rename…")
        self.btn_rename_mod.setToolTip("Rename the selected extra mod folder.")
        self.btn_rename_mod.clicked.connect(self._rename_selected_mod)

        self.btn_open_mod = QPushButton("Open Folder")
        self.btn_open_mod.setToolTip("Open the selected mod's folder in your file manager.")
        self.btn_open_mod.clicked.connect(self._open_selected_mod_folder)

        self.btn_delete_mod = QPushButton("Delete")
        self.btn_delete_mod.setToolTip("Remove linked mod from list, or permanently delete a staged/live mod.")
        self.btn_delete_mod.setStyleSheet(
            "QPushButton { background: rgba(74, 28, 28, 185); color: #ffcdd2; border: 1px solid #8e2c2c; "
            "border-radius: 4px; padding: 5px 12px; font-weight: bold; }"
            "QPushButton:hover { background: rgba(107, 34, 34, 200); }"
            "QPushButton:disabled { background: rgba(44, 48, 54, 140); color: #777777; border: 1px solid #3c3c3c; }"
        )
        self.btn_delete_mod.clicked.connect(self._delete_selected_mod)

        mod_mgmt_row.addWidget(self.btn_move_up)
        mod_mgmt_row.addWidget(self.btn_move_dn)
        mod_mgmt_row.addWidget(self.btn_inspect_mod)
        mod_mgmt_row.addWidget(self.btn_rename_mod)
        mod_mgmt_row.addWidget(self.btn_open_mod)
        mod_mgmt_row.addStretch(1)
        mod_mgmt_row.addWidget(self.btn_delete_mod)
        s3.addLayout(mod_mgmt_row)

        mod_tools_row = QHBoxLayout()
        mod_tools_row.setSpacing(6)
        self.btn_overlap_inspector.setText("Conflict & Overlap Inspector…")
        self.btn_presets.setText("Mod Loadouts ▾")
        mod_tools_row.addWidget(self.btn_overlap_inspector)
        mod_tools_row.addWidget(self.btn_presets)
        mod_tools_row.addStretch(1)
        s3.addLayout(mod_tools_row)

        right_outer.addWidget(step3_card)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(0)
        left_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }")
        left_scroll.viewport().setAutoFillBackground(False)
        left_scroll.setWidget(left_col)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMinimumWidth(0)
        right_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        right_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }")
        right_scroll.viewport().setAutoFillBackground(False)
        right_scroll.setWidget(right_col)

        mid_split.addWidget(left_scroll)
        mid_split.addWidget(right_scroll)
        mid_split.setStretchFactor(0, 4)
        mid_split.setStretchFactor(1, 6)
        mid_split.setSizes([420, 560])
        root.addWidget(mid_split, 1)

        # --- STEP 4: Build & Play ---
        step4_card, s4 = _make_step_card(
            4,
            "Apply Changes & Play",
            "Review your loadout summary, click Apply to build your mods, then launch Longshot.",
        )
        self._step_cards.append(step4_card)

        self.summary_label = QLabel()
        self.summary_label.setMinimumWidth(0)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background: rgba(26, 36, 47, 155); border: 1px solid #34495e; color: #d6e4f0; "
            "border-radius: 5px; padding: 8px 10px; font-weight: bold;"
        )
        s4.addWidget(self.summary_label)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.build_btn = QPushButton()
        self.build_btn.setMinimumHeight(42)
        self.build_btn.setStyleSheet(
            "QPushButton { background: rgba(25, 118, 210, 200); color: #ffffff; font-weight: bold; "
            "font-size: 14px; border-radius: 5px; padding: 0 18px; }"
            "QPushButton:hover { background: rgba(30, 136, 229, 215); }"
            "QPushButton:disabled { background: rgba(58, 62, 68, 140); color: #888888; }"
        )
        self.build_btn.clicked.connect(self._start_build)

        self.launch_btn = QPushButton("▶  Play Longshot")
        self.launch_btn.setMinimumHeight(42)
        self.launch_btn.setStyleSheet(
            "QPushButton { background: rgba(46, 125, 50, 195); color: #ffffff; font-weight: bold; "
            "font-size: 14px; border-radius: 5px; padding: 0 20px; }"
            "QPushButton:hover { background: rgba(56, 142, 60, 215); }"
            "QPushButton:disabled { background: rgba(58, 62, 68, 140); color: #888888; }"
        )
        self.launch_btn.clicked.connect(self._launch_longshot)

        self._open_dir_btn = QPushButton("Open Mods Folder")
        self._open_dir_btn.setMinimumHeight(42)
        self._open_dir_btn.clicked.connect(self._open_target_dir)

        action_row.addWidget(self.build_btn, 2)
        action_row.addWidget(self.launch_btn, 1)
        action_row.addWidget(self._open_dir_btn)
        s4.addLayout(action_row)

        prog_row = QHBoxLayout()
        self.status_lbl = QLabel("Ready — follow Steps 1–3 above, then click Apply.")
        self.status_lbl.setMinimumWidth(0)
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._set_status_style("neutral")
        self.log_toggle_btn = QPushButton("Show Technical Log ▾")
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.toggled.connect(self._toggle_log_view)
        prog_row.addWidget(self.status_lbl, 1)
        prog_row.addWidget(self.log_toggle_btn)
        s4.addLayout(prog_row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("monospace", 9))
        self.log_view.setFixedHeight(150)
        self.log_view.setVisible(False)
        s4.addWidget(self.log_view)

        step4_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        root.addWidget(step4_card)

        self._build_page = self._create_build_progress_page()
        self._view_stack.addWidget(self._main_page)
        self._view_stack.addWidget(self._build_page)
        self._view_stack.setCurrentWidget(self._main_page)
        self._compact_mode = False
        self.drop_zone.setMinimumWidth(0)
        self.drop_zone.title_lbl.setWordWrap(True)
        self.drop_zone.title_lbl.setMinimumWidth(0)
        self.drop_zone.sub_lbl.setWordWrap(True)
        self.drop_zone.sub_lbl.setMinimumWidth(0)
        for card in self._step_cards:
            card.setMinimumWidth(0)
            card._step_title.setWordWrap(True)
            card._step_title.setMinimumWidth(0)
            card._step_sub.setWordWrap(True)
            card._step_sub.setMinimumWidth(0)
        for lbl in self._section_labels:
            lbl.setWordWrap(True)
            lbl.setMinimumWidth(0)
        self._ui_ready = True
        self._update_mode_ui()
        self._update_mod_action_buttons()

    def _create_build_progress_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("midnaBuildPage")
        page.setStyleSheet("QWidget#midnaBuildPage { background: transparent; }")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)

        center_row = QHBoxLayout()
        center_row.addStretch(1)

        self._build_card = QFrame()
        self._build_card.setObjectName("buildStageCard")
        self._build_card.setMinimumWidth(0)
        self._build_card.setMaximumWidth(860)
        self._build_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        card_lay = QVBoxLayout(self._build_card)
        card_lay.setContentsMargins(40, 32, 40, 32)
        card_lay.setSpacing(16)

        self.midna_dancer = MidnaDanceWidget(size=280)
        card_lay.addWidget(self.midna_dancer, 0, Qt.AlignmentFlag.AlignHCenter)

        self._build_mode_pill = QLabel()
        self._build_mode_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self._build_mode_pill, 0, Qt.AlignmentFlag.AlignHCenter)

        self._build_title_lbl = QLabel("Weaving Your Mods Together…")
        self._build_title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._build_title_lbl.setWordWrap(True)
        card_lay.addWidget(self._build_title_lbl)

        self._build_step_lbl = QLabel("Preparing build…")
        self._build_step_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._build_step_lbl.setWordWrap(True)
        card_lay.addWidget(self._build_step_lbl)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(28)
        card_lay.addWidget(self.progress)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        self._build_log_toggle = QPushButton("Show Technical Log ▾")
        self._build_log_toggle.setCheckable(True)
        self._build_log_toggle.toggled.connect(self._toggle_build_log_view)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self._build_log_toggle)

        self._build_back_btn = QPushButton("← Back to Mod Manager")
        self._build_back_btn.setVisible(False)
        self._build_back_btn.clicked.connect(self._return_from_build_view)
        ctrl_row.addWidget(self._build_back_btn)
        ctrl_row.addStretch(1)
        card_lay.addLayout(ctrl_row)

        self._build_log_view = QPlainTextEdit()
        self._build_log_view.setReadOnly(True)
        self._build_log_view.setFont(QFont("monospace", 9))
        self._build_log_view.setFixedHeight(220)
        self._build_log_view.setVisible(False)
        card_lay.addWidget(self._build_log_view)

        center_row.addWidget(self._build_card, 1)
        center_row.addStretch(1)
        outer.addLayout(center_row)
        outer.addStretch(1)
        return page

    def _toggle_build_log_view(self, checked: bool) -> None:
        self._build_log_view.setVisible(checked)
        self._build_log_toggle.setText("Hide Technical Log ▴" if checked else "Show Technical Log ▾")

    def _quick_folder_targets(self):
        from oot_rando.paths import data_dir

        target_mods = getattr(self.cfg, "target_mods_dir", "") or ""
        live_mods = getattr(self.cfg, "live_mods_dir", "") or ""
        active_mods = target_mods if (target_mods and os.path.isdir(target_mods)) else (live_mods or target_mods)

        merged_dir = ""
        for base_dir in (target_mods, live_mods):
            if base_dir:
                cand = os.path.join(base_dir, "Merged_Zelda_Rando")
                if os.path.isdir(cand):
                    merged_dir = cand
                    break
        if not merged_dir and active_mods:
            merged_dir = os.path.join(active_mods, "Merged_Zelda_Rando")

        stage_dir = self._party_stage_dir or getattr(self.cfg, "staged_mods_dir", "") or str(data_dir() / "staged_for_generation")
        return [
            ("UserModLibrary", getattr(self.cfg, "backup_dir", "") or "", True),
            ("ArchivedSeeds", getattr(self.cfg, "uninstalled_seeds_dir", "") or "", True),
            ("staged_for_generation", stage_dir, True),
            ("Merged_Zelda_Rando", merged_dir, False),
            ("Active mods/ Folder", active_mods, True),
        ]

    def _open_quick_folders_menu(self) -> None:
        """Show one-click folder shortcuts using the cross-platform file manager opener."""
        import importlib
        from oot_rando.paths import open_in_file_manager
        qtw = importlib.import_module(type(self.folders_btn).__module__)
        menu = qtw.QMenu(self)
        for label, path_str, create_if_missing in self._quick_folder_targets():
            act = menu.addAction(label)
            if not path_str:
                act.setEnabled(False)
                continue
            exists = os.path.isdir(path_str)
            if not exists and not create_if_missing:
                act.setText(label + " (not created yet)")
                act.setEnabled(False)
                continue
            def _open_target(_checked=False, p=path_str, make=create_if_missing, lbl=label):
                try:
                    if make:
                        os.makedirs(p, exist_ok=True)
                    open_in_file_manager(p)
                except Exception as exc:
                    self.status_lbl.setText("Could not open " + lbl + ": " + str(exc))
            act.triggered.connect(_open_target)
        menu.exec(self.folders_btn.mapToGlobal(self.folders_btn.rect().bottomLeft()))

    def set_party_banner(
        self,
        message: str,
        *,
        show_remerge: bool = True,
        party_name: str = "",
        stage_dir: str = "",
    ) -> None:
        """Show or hide the party-switch re-merge banner inside the Midna tab."""
        if stage_dir:
            self._party_stage_dir = stage_dir
        msg = (message or "").strip()
        if not msg:
            self.party_banner.setVisible(False)
            return
        prefix = ("Party " + party_name + ": ") if party_name else ""
        self.party_banner_lbl.setText(prefix + msg)
        self.party_banner_merge_btn.setVisible(bool(show_remerge))
        self.party_banner.setVisible(True)

    def _on_party_banner_remerge(self) -> None:
        """Trigger a one-click re-apply & merge for the currently active party seed."""
        self.party_banner.setVisible(False)
        self.refresh_all()
        self._start_build()

    def _return_from_build_view(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.midna_dancer.set_state("idle")
        self.midna_dancer.stop()
        self._view_stack.setCurrentWidget(self._main_page)

    def _style_build_mode_pill(self, plain: bool) -> None:
        """Style the build-progress mode pill for Sandbox or Live mode in the active theme."""
        if not hasattr(self, "_build_mode_pill"):
            return
        if self.cfg.sandbox_mode:
            self._build_mode_pill.setText("TEST MODE · Safe Preview")
            self._build_mode_pill.setStyleSheet(
                "font-weight: bold; font-size: 11px; padding: 3px 10px; border-radius: 10px; "
                "background: #f8eecf; border: 1px solid #d5a62b; color: #7a520b;"
                if plain
                else "font-weight: bold; font-size: 11px; padding: 3px 10px; border-radius: 10px; "
                "background: rgba(58, 36, 9, 185); border: 1px solid #ef6c00; color: #ffcc80;"
            )
        else:
            self._build_mode_pill.setText("LIVE MODE · Applying to Game")
            self._build_mode_pill.setStyleSheet(
                "font-weight: bold; font-size: 11px; padding: 3px 10px; border-radius: 10px; "
                "background: #e4efe7; border: 1px solid #2f7a55; color: #1f5c3e;"
                if plain
                else "font-weight: bold; font-size: 11px; padding: 3px 10px; border-radius: 10px; "
                "background: rgba(20, 62, 38, 185); border: 1px solid #43a047; color: #a5d6a7;"
            )

    def _style_build_page(self, plain: bool, compact: bool) -> None:
        """Apply light or dark styling to the full-page build progress overlay."""
        if not hasattr(self, "_build_card"):
            return
        self._style_build_mode_pill(plain)
        title_fs = "16px" if compact else "20px"
        step_fs = "11px" if compact else "13px"
        if plain:
            self._build_card.setStyleSheet(
                "QFrame#buildStageCard { background: #fffdf8; border: 1px solid #d5ccb7; border-radius: 12px; }"
            )
            self._build_title_lbl.setStyleSheet(
                f"border: none; background: transparent; color: #1f2a24; font-size: {title_fs}; font-weight: bold;"
            )
            self._build_step_lbl.setStyleSheet(
                f"border: none; background: transparent; color: #4c5850; font-size: {step_fs};"
            )
            self._build_back_btn.setStyleSheet(
                "QPushButton { background: #2f5f8f; color: #ffffff; font-weight: bold; "
                "border: 1px solid #254c73; border-radius: 5px; padding: 6px 14px; }"
                "QPushButton:hover { background: #27517a; }"
            )
        else:
            self._build_card.setStyleSheet(
                "QFrame#buildStageCard { background: rgba(16, 22, 32, 185); border: 1px solid #3f5872; border-radius: 14px; }"
            )
            self._build_title_lbl.setStyleSheet(
                f"border: none; background: transparent; color: #f0f6fc; font-size: {title_fs}; font-weight: bold;"
            )
            self._build_step_lbl.setStyleSheet(
                f"border: none; background: transparent; color: #90caf9; font-size: {step_fs};"
            )
            self._build_back_btn.setStyleSheet(
                "QPushButton { background: rgba(25, 118, 210, 220); color: #ffffff; font-weight: bold; "
                "border: 1px solid #64b5f6; border-radius: 5px; padding: 6px 14px; }"
                "QPushButton:hover { background: rgba(33, 150, 243, 235); }"
            )

    def _is_plain_ui(self) -> bool:
        if hasattr(self, "_plain_ui"):
            return bool(self._plain_ui)
        return self.cfg.effective_ui_theme == THEME_MOZENCAZ

    def set_theme_change_callback(self, callback) -> None:
        self._theme_change_callback = callback

    def _set_status_style(self, tone: str) -> None:
        self._status_tone = tone
        color = status_color(self._is_plain_ui(), tone)
        self.status_lbl.setStyleSheet(f"border: none; font-weight: bold; color: {color};")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not getattr(self, "_ui_ready", False):
            return
        w = self.width()
        want_compact = self._compact_mode
        if not self._compact_mode and w < 990:
            want_compact = True
        elif self._compact_mode and w > 1030:
            want_compact = False
        if want_compact != self._compact_mode:
            self._compact_mode = want_compact
            self.apply_ui_theme(self.cfg.effective_ui_theme, persist=False, notify=False)

    def _refresh_responsive_labels(self) -> None:
        if not getattr(self, "_ui_ready", False):
            return
        compact = getattr(self, "_compact_mode", False)
        plain = self._is_plain_ui()

        self.path_label.setVisible(not compact)
        self.instructions_btn.setText("Guide" if compact else "Instructions…")
        self.ui_style_btn.setText("Theme" if compact else "UI Style…")
        self.settings_btn.setText("Folders…" if compact else "Configure Folders…")
        self.btn_inspect_mod.setText("Inspect" if compact else "Inspect Files…")
        self.btn_rename_mod.setText("Rename" if compact else "Rename…")
        self.btn_open_mod.setText("Folder" if compact else "Open Folder")
        self._open_dir_btn.setText("Mods Folder" if compact else "Open Mods Folder")
        self.launch_btn.setText("▶ Play" if compact else "▶  Play Longshot")
        self.drop_zone.browse_btn.setText("Browse…" if compact else "Browse File…")

        mod = self._selected_standalone_mod()
        if mod and mod.origin == "linked":
            self.btn_delete_mod.setText("Remove" if compact else "Remove from List")
        else:
            self.btn_delete_mod.setText("Delete")

        badge_pad = "3px 7px" if compact else "6px 12px"
        badge_fs = "font-size: 11px; " if compact else ""
        if self.cfg.sandbox_mode:
            self.mode_badge.setText(
                "TEST MODE · Safe" if compact else "TEST MODE · Safe (Won't Touch Your Live Game)"
            )
            self.mode_badge.setToolTip("TEST MODE · Safe (Won't Touch Your Live Game)")
            self.mode_badge.setStyleSheet(
                f"font-weight: bold; {badge_fs}padding: {badge_pad}; border-radius: 5px; "
                "background: #f8eecf; border: 1px solid #d5a62b; color: #7a520b;"
                if plain
                else f"font-weight: bold; {badge_fs}padding: {badge_pad}; border-radius: 5px; "
                "background: rgba(58, 36, 9, 175); border: 1px solid #ef6c00; color: #ffcc80;"
            )
            self.mode_btn.setText("Live Mode" if compact else "Switch to Live Game")
            self.build_btn.setText("Apply (Test Mode)" if compact else "Apply & Build in Test Mode")
        else:
            self.mode_badge.setText(
                "LIVE MODE" if compact else "LIVE MODE · Applies Directly to Longshot"
            )
            self.mode_badge.setToolTip("LIVE MODE · Applies Directly to Longshot")
            self.mode_badge.setStyleSheet(
                f"font-weight: bold; {badge_fs}padding: {badge_pad}; border-radius: 5px; "
                "background: #e4efe7; border: 1px solid #2f7a55; color: #1f5c3e;"
                if plain
                else f"font-weight: bold; {badge_fs}padding: {badge_pad}; border-radius: 5px; "
                "background: rgba(20, 62, 38, 180); border: 1px solid #43a047; color: #a5d6a7;"
            )
            self.mode_btn.setText("Test Mode" if compact else "Switch to Test Mode")
            self.build_btn.setText("Apply (Live Game)" if compact else "Apply & Build to Live Game")

    def _show_migration_notice(self) -> None:
        notices = list(getattr(self.cfg, "migration_notices", []) or [])
        if not notices:
            return
        self.cfg.migration_notices.clear()
        body = (
            "Midna's Devotion updated its folder naming to be clearer and automatically "
            "migrated your existing folders and saved links:\n\n• "
            + "\n• ".join(notices)
            + "\n\nNo action is required — all of your mods and settings are preserved."
        )
        QMessageBox.information(self, "Midna's Devotion Folder Structure Updated", body)

    def _sync_popup_palettes(self, plain: bool) -> None:
        """Force opaque light/dark palettes on QToolTip and QComboBox popups across Linux & Windows."""
        from PySide6.QtGui import QPalette

        bg = QColor("#fffdf8") if plain else QColor("#161a21")
        fg = QColor("#1f2a24") if plain else QColor("#f0f4f8")
        sel_bg = QColor("#e4efe7") if plain else QColor("#2b6cb0")
        sel_fg = QColor("#1f2a24") if plain else QColor("#ffffff")
        tip_bg = QColor("#fffdf8") if plain else QColor("#1b222c")

        tip_pal = QToolTip.palette()
        tip_pal.setColor(QPalette.ColorRole.ToolTipBase, tip_bg)
        tip_pal.setColor(QPalette.ColorRole.ToolTipText, fg)
        tip_pal.setColor(QPalette.ColorRole.Window, tip_bg)
        tip_pal.setColor(QPalette.ColorRole.WindowText, fg)
        QToolTip.setPalette(tip_pal)

        for combo in (getattr(self, "char_combo", None), getattr(self, "seed_combo", None)):
            if combo is None:
                continue
            view = combo.view()
            if view is None:
                continue
            pal = view.palette()
            pal.setColor(QPalette.ColorRole.Window, bg)
            pal.setColor(QPalette.ColorRole.Base, bg)
            pal.setColor(QPalette.ColorRole.AlternateBase, bg)
            pal.setColor(QPalette.ColorRole.Text, fg)
            pal.setColor(QPalette.ColorRole.WindowText, fg)
            pal.setColor(QPalette.ColorRole.Highlight, sel_bg)
            pal.setColor(QPalette.ColorRole.HighlightedText, sel_fg)
            bg_hex = bg.name()
            border_hex = "#cfc5ad" if plain else "#3c4856"
            popup = view.parentWidget()
            for target in (view, view.viewport(), popup):
                if target is not None:
                    target.setPalette(pal)
                    target.setAutoFillBackground(True)
            if popup is not None:
                popup.setStyleSheet(
                    f"background-color: {bg_hex}; border: 1px solid {border_hex}; padding: 0px; margin: 0px;"
                )
                lay = popup.layout()
                if lay is not None:
                    lay.setContentsMargins(0, 0, 0, 0)
                    lay.setSpacing(0)

    def apply_ui_theme(self, theme_id: str, persist: bool = True, notify: bool = True) -> None:
        """Apply Mozencaz Light or Dark Araragi Midna styling across the window, popups, and host callback."""
        chosen = THEME_MOZENCAZ if theme_id == THEME_MOZENCAZ else THEME_ARARAGI
        if persist:
            self.cfg.ui_theme = chosen
            try:
                self.cfg.save_settings()
            except OSError:
                pass
        plain = chosen == THEME_MOZENCAZ
        self._plain_ui = plain
        compact = getattr(self, "_compact_mode", False)

        self.central_widget.set_plain_mode(plain)
        self.central_widget.setStyleSheet(central_stylesheet(plain, compact=compact))
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.setPalette(app_palette(plain))
            qapp.setStyleSheet(app_stylesheet(plain))
        self._sync_popup_palettes(plain)
        self.drop_zone.set_plain_mode(plain)
        self._style_build_page(plain, compact)

        root_lay = getattr(self, "_main_root_layout", None) or self.central_widget.layout()
        if root_lay is not None:
            if compact:
                root_lay.setContentsMargins(8, 6, 8, 6)
                root_lay.setSpacing(6)
            else:
                root_lay.setContentsMargins(14, 12, 14, 12)
                root_lay.setSpacing(10)

        top_lay = self.top_frame.layout()
        if top_lay is not None:
            if compact:
                top_lay.setContentsMargins(6, 5, 6, 5)
                top_lay.setSpacing(4)
            else:
                top_lay.setContentsMargins(10, 8, 10, 8)
                top_lay.setSpacing(8)

        badge_fs = "10px" if compact else "11px"
        badge_pad = "2px 6px" if compact else "4px 9px"
        title_fs = "12px" if compact else "13px"
        sub_fs = "10px" if compact else "11px"
        sec_fs = "11px" if compact else "12px"
        cta_fs = "12px" if compact else "14px"
        cta_pad = "0 10px" if compact else "0 18px"
        cta_h = 34 if compact else 42
        del_pad = "3px 8px" if compact else "5px 12px"
        del_fs = "font-size: 11px; " if compact else ""
        sum_pad = "5px 8px" if compact else "8px 10px"
        sum_fs = "font-size: 11px; " if compact else ""
        arrow_w = 24 if compact else 30

        self.btn_move_up.setFixedWidth(arrow_w)
        self.btn_move_dn.setFixedWidth(arrow_w)
        self.build_btn.setMinimumHeight(cta_h)
        self.launch_btn.setMinimumHeight(cta_h)
        self._open_dir_btn.setMinimumHeight(cta_h)
        if hasattr(self, "midna_dancer"):
            self.midna_dancer.set_display_size(210 if compact else 280)

        for card in self._step_cards:
            cl = card.layout()
            if cl is not None:
                if compact:
                    cl.setContentsMargins(9, 7, 9, 7)
                    cl.setSpacing(6)
                else:
                    cl.setContentsMargins(14, 12, 14, 12)
                    cl.setSpacing(10)

        if plain:
            self.top_frame.setStyleSheet(
                "QFrame#topBar { background: #fffdf8; border: 1px solid #e3dccb; border-radius: 7px; }"
            )
            self.path_label.setStyleSheet("border: none; color: #6c766d; font-size: 11px;")
            for card in self._step_cards:
                num = getattr(card, "_step_num", 0)
                card.setStyleSheet(
                    f"QFrame#stepCard{num} {{ background: #fffdf8; border: 1px solid #e3dccb; border-radius: 8px; }}"
                )
                card._step_badge.setStyleSheet(
                    f"background: #e4efe7; color: #2f7a55; font-weight: bold; font-size: {badge_fs}; "
                    f"padding: {badge_pad}; border-radius: 4px; border: 1px solid #c5dccb;"
                )
                card._step_title.setStyleSheet(f"border: none; color: #1f2a24; font-size: {title_fs}; font-weight: bold;")
                card._step_sub.setStyleSheet(f"border: none; color: #6c766d; font-size: {sub_fs};")
                card._step_sep.setStyleSheet("background: #e3dccb; max-height: 1px; border: none;")
            for lbl in self._section_labels:
                lbl.setStyleSheet(f"border: none; font-weight: bold; color: #1f2a24; font-size: {sec_fs};")
            self.btn_add_lib_vis.setStyleSheet(
                "QPushButton { background: #2f7a55; color: #ffffff; font-weight: bold; "
                "border: 1px solid #246042; border-radius: 4px; padding: 0 10px; }"
                "QPushButton:hover { background: #266948; }"
                "QPushButton:disabled { background: #f2eee3; color: #a3a99f; border: 1px solid #e3dccb; }"
            )
            self.btn_delete_mod.setStyleSheet(
                f"QPushButton {{ background: #fbeaea; color: #8e2c2c; border: 1px solid #e2b8b8; "
                f"border-radius: 4px; padding: {del_pad}; {del_fs}font-weight: bold; }}"
                "QPushButton:hover { background: #f5d8d8; }"
                "QPushButton:disabled { background: #f2eee3; color: #a3a99f; border: 1px solid #e3dccb; }"
            )
            self.summary_label.setStyleSheet(
                f"background: #f7f3ea; border: 1px solid #e3dccb; color: #1f2a24; "
                f"border-radius: 5px; padding: {sum_pad}; {sum_fs}font-weight: bold;"
            )
            self.build_btn.setStyleSheet(
                f"QPushButton {{ background: #2f5f8f; color: #ffffff; font-weight: bold; "
                f"font-size: {cta_fs}; border: 1px solid #254c73; border-radius: 5px; padding: {cta_pad}; }}"
                "QPushButton:hover { background: #27517a; }"
                "QPushButton:disabled { background: #e3dccb; color: #8d948a; border: 1px solid #d5ccb7; }"
            )
            self.launch_btn.setStyleSheet(
                f"QPushButton {{ background: #2f7a55; color: #ffffff; font-weight: bold; "
                f"font-size: {cta_fs}; border: 1px solid #246042; border-radius: 5px; padding: {cta_pad}; }}"
                "QPushButton:hover { background: #266948; }"
                "QPushButton:disabled { background: #e3dccb; color: #8d948a; border: 1px solid #d5ccb7; }"
            )
        else:
            self.top_frame.setStyleSheet(
                "QFrame#topBar { background: rgba(22, 26, 33, 155); border: 1px solid #353535; border-radius: 7px; }"
            )
            self.path_label.setStyleSheet("border: none; color: #9e9e9e; font-size: 11px;")
            for card in self._step_cards:
                num = getattr(card, "_step_num", 0)
                card.setStyleSheet(
                    f"QFrame#stepCard{num} {{ background: rgba(26, 30, 38, 150); border: 1px solid #3a3a3a; border-radius: 8px; }}"
                )
                card._step_badge.setStyleSheet(
                    f"background: rgba(21, 101, 192, 195); color: #ffffff; font-weight: bold; font-size: {badge_fs}; "
                    f"padding: {badge_pad}; border-radius: 4px; border: none;"
                )
                card._step_title.setStyleSheet(f"border: none; color: #f5f5f5; font-size: {title_fs}; font-weight: bold;")
                card._step_sub.setStyleSheet(f"border: none; color: #b0bec5; font-size: {sub_fs};")
                card._step_sep.setStyleSheet("background: #333333; max-height: 1px; border: none;")
            for lbl in self._section_labels:
                lbl.setStyleSheet(f"border: none; font-weight: bold; color: #e6eef8; font-size: {sec_fs};")
            self.btn_add_lib_vis.setStyleSheet(
                "QPushButton { background: rgba(25, 118, 210, 210); color: #ffffff; font-weight: bold; "
                "border: 1px solid #42a5f5; border-radius: 4px; padding: 0 10px; }"
                "QPushButton:hover { background: rgba(30, 136, 229, 230); }"
                "QPushButton:disabled { background: rgba(30, 34, 40, 120); color: #78828c; border: 1px solid #2f353d; }"
            )
            self.btn_delete_mod.setStyleSheet(
                f"QPushButton {{ background: rgba(120, 32, 38, 190); color: #ffcdd2; border: 1px solid #e57373; "
                f"border-radius: 4px; padding: {del_pad}; {del_fs}font-weight: bold; }}"
                "QPushButton:hover { background: rgba(145, 38, 46, 215); }"
                "QPushButton:disabled { background: rgba(30, 34, 40, 120); color: #78828c; border: 1px solid #2f353d; }"
            )
            self.summary_label.setStyleSheet(
                f"background: rgba(18, 24, 34, 185); border: 1px solid #3c4f65; color: #e6eef8; "
                f"border-radius: 5px; padding: {sum_pad}; {sum_fs}font-weight: bold;"
            )
            self.build_btn.setStyleSheet(
                f"QPushButton {{ background: rgba(25, 118, 210, 220); color: #ffffff; font-weight: bold; "
                f"font-size: {cta_fs}; border: 1px solid #64b5f6; border-radius: 5px; padding: {cta_pad}; }}"
                "QPushButton:hover { background: rgba(33, 150, 243, 235); }"
                "QPushButton:disabled { background: rgba(30, 34, 40, 120); color: #78828c; border: 1px solid #2f353d; }"
            )
            self.launch_btn.setStyleSheet(
                f"QPushButton {{ background: rgba(34, 139, 94, 215); color: #ffffff; font-weight: bold; "
                f"font-size: {cta_fs}; border: 1px solid #4db6ac; border-radius: 5px; padding: {cta_pad}; }}"
                "QPushButton:hover { background: rgba(42, 162, 110, 235); }"
                "QPushButton:disabled { background: rgba(30, 34, 40, 120); color: #78828c; border: 1px solid #2f353d; }"
            )

        self._set_status_style(getattr(self, "_status_tone", "neutral"))
        if getattr(self, "_ui_ready", False):
            # _update_mode_ui already refreshes action buttons and responsive labels.
            self._update_mode_ui()
            if getattr(self, "_initial_restored", False):
                self._recolor_visual_library_items()
                self._sync_character_list_row()
                self._update_overlap_panel()
                self.visual_lib_list.viewport().update()
                self.mod_list.viewport().update()
        if notify:
            cb = getattr(self, "_theme_change_callback", None)
            if callable(cb):
                cb(chosen)

    def _modal_parent(self):
        return self if self.isVisible() else None

    def schedule_startup_onboarding(self, delay_ms: int = 180) -> None:
        "Schedule the non-overlapping startup onboarding pipeline once visible."
        if getattr(self, "_onboarding_running", False) or getattr(self, "_onboarding_scheduled", False):
            return
        self._onboarding_scheduled = True

        def _fire() -> None:
            self._onboarding_scheduled = False
            self.run_startup_onboarding()

        QTimer.singleShot(delay_ms, _fire)

    def run_startup_onboarding(self, *, force_headless: bool = False) -> None:
        "Execute theme picker, migration/Longshot relocation notices, folder setup, and missing-folder checks strictly in sequence."
        if getattr(self, "_onboarding_running", False):
            return
        if getattr(self.cfg, "embedded_in_randomizer", False) and not force_headless and not self.isVisible():
            return
        self._onboarding_running = True
        try:
            if not self.cfg.has_ui_theme_choice and not getattr(self, "_first_launch_done", False):
                self._prompt_first_launch(_chain=False)

            if getattr(self.cfg, "migration_notices", None) and not getattr(self, "_migration_notice_shown", False):
                self._migration_notice_shown = True
                self._show_migration_notice()
                self.cfg.migration_notices.clear()

            if getattr(self.cfg, "longshot_relocation_info", None) and not getattr(self, "_relocation_prompted", False):
                self._relocation_prompted = True
                self._prompt_longshot_relocation_if_needed()

            if not self.cfg.is_configured and not getattr(self, "_initial_setup_prompted", False):
                self._initial_setup_prompted = True
                self._prompt_initial_setup()

            if (self.cfg.is_configured or self.cfg.romfs_dir or self.cfg.live_mods_dir) and not getattr(self, "_missing_folders_prompted", False):
                self._prompt_missing_folders_if_needed()
        finally:
            self._onboarding_running = False

    def _prompt_longshot_relocation_if_needed(self) -> None:
        info = getattr(self.cfg, "longshot_relocation_info", None)
        if not isinstance(info, dict):
            return
        mods_list = list(info.get("standalone_mods") or [])
        old_lib = str(info.get("old_library") or "")
        new_lib = str(info.get("new_library") or "")
        if not mods_list and not old_lib:
            self.cfg.longshot_relocation_info = None
            return
        bullets = []
        if mods_list:
            old_mods_val = info.get("old_mods")
            extra_dots = "…" if len(mods_list) > 5 else ""
            bullets.append(f"{len(mods_list)} standalone mod(s) in {old_mods_val}: " + ", ".join(mods_list[:5]) + extra_dots)
        if old_lib:
            bullets.append(f"UserModLibrary in {old_lib}")
        msg = (
            "Longshot updated to a newer folder:" + chr(10)
            + str(info.get("new_port", "")) + chr(10) + chr(10)
            + "Found mod folders still in your previous Longshot folder:" + chr(10) + "• "
            + (chr(10) + "• ").join(bullets) + chr(10) + chr(10)
            + "Copy them into the updated Longshot installation now? (Originals stay untouched as backup.)"
        )
        ans = QMessageBox.question(
            self._modal_parent(),
            "Carry Over Mods to Updated Longshot?",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        handled = list(self.cfg.saved_state.get("handled_longshot_relocations") or [])
        reloc_key = str(info.get("key") or "")
        if reloc_key and reloc_key not in handled:
            handled.append(reloc_key)
        if ans == QMessageBox.StandardButton.Yes:
            from oot_rando.path_safety import fs_path
            copied_count = 0
            try:
                new_mods_dir = str(info.get("new_mods") or "")
                old_mods_dir = str(info.get("old_mods") or "")
                if mods_list and new_mods_dir and old_mods_dir:
                    os.makedirs(fs_path(new_mods_dir), exist_ok=True)
                    for m_name in mods_list:
                        src_m = os.path.join(old_mods_dir, m_name)
                        dst_m = os.path.join(new_mods_dir, m_name)
                        if os.path.isdir(src_m) and not os.path.exists(dst_m):
                            shutil.copytree(fs_path(src_m), fs_path(dst_m))
                            copied_count += 1
                if old_lib and new_lib and os.path.isdir(old_lib) and not os.path.exists(new_lib):
                    shutil.copytree(fs_path(old_lib), fs_path(new_lib))
                    self.cfg.backup_dir = new_lib
                    copied_count += 1
            except OSError as exc:
                QMessageBox.warning(self._modal_parent(), "Could Not Copy All Mods", str(exc))
            self.cfg.longshot_relocation_info = None
            try:
                self.cfg.save_settings({"handled_longshot_relocations": handled})
            except OSError:
                pass
            self.refresh_all()
            if copied_count:
                self._set_status_style("ok")
                self.status_lbl.setText(f"✓  Carried over {copied_count} item(s) into updated Longshot folder.")
        else:
            self.cfg.longshot_relocation_info = None
            try:
                self.cfg.save_settings({"handled_longshot_relocations": handled})
            except OSError:
                pass

    def _prompt_first_launch(self, *, _chain: bool = True) -> None:
        if getattr(self, "_first_launch_done", False):
            return
        self._first_launch_done = True
        dlg = UiExperienceDialog(
            current_theme=self.cfg.ui_theme,
            first_launch=True,
            parent=self._modal_parent(),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_theme:
            self.apply_ui_theme(dlg.selected_theme, persist=True)
        else:
            self.apply_ui_theme(self.cfg.effective_ui_theme, persist=True)
        if _chain:
            self.run_startup_onboarding(force_headless=True)

    def _prompt_text_input(self, title: str, label: str, initial_text: str = "") -> Tuple[str, bool]:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setModal(True)
        dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        lbl = QLabel(label)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        edit = QLineEdit(dlg)
        edit.setText(initial_text)
        edit.selectAll()
        lay.addWidget(edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        cancel_btn.clicked.connect(dlg.reject)
        ok_btn.clicked.connect(dlg.accept)
        edit.returnPressed.connect(dlg.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

        edit.setFocus()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return edit.text(), True
        return "", False

    def _open_instructions(self) -> None:
        """Display the workflow instructions dialog using the currently active UI theme."""
        MidnaInstructionsDialog(None, plain=self._is_plain_ui()).exec()

    def _open_ui_style_picker(self) -> None:
        dlg = UiExperienceDialog(
            current_theme=self.cfg.effective_ui_theme,
            first_launch=False,
            parent=None,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_theme:
            self.apply_ui_theme(dlg.selected_theme, persist=True)

    def _prompt_initial_setup(self) -> None:
        ans = QMessageBox.information(
            self,
            "Welcome to Midna's Devotion",
            "Before you begin, tell Midna's Devotion where your Longshot folders are located.\n\n"
            "You can auto-fill everything in one click by selecting your Longshot folder.\n\n"
            "Open Folder Settings now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._open_settings()

    def _prompt_missing_folders_if_needed(self) -> None:
        if getattr(self, "_missing_folders_prompted", False):
            return
        self._missing_folders_prompted = True
        paths = {
            "romfs_dir": self.cfg.romfs_dir,
            "live_mods_dir": self.cfg.live_mods_dir,
            "backup_dir": self.cfg.backup_dir,
            "uninstalled_seeds_dir": self.cfg.uninstalled_seeds_dir,
            "workspace_dir": self.cfg.workspace_dir,
        }
        if not find_missing_creatable_folders(paths):
            return
        created = prompt_create_missing_folders(
            self._modal_parent(),
            paths,
            synced_keys=getattr(self.cfg, "rando_synced_keys", set()),
            skip_label="Not Now",
        )
        if not created:
            return
        for key, folder_path in created.items():
            setattr(self.cfg, key, folder_path)
        try:
            self.cfg.save_settings()
            self.cfg.sync_from_randomizer(persist=True)
        except OSError as exc:
            QMessageBox.warning(self, "Could Not Save Settings", str(exc))
            return
        self.refresh_all()
        self._set_status_style("ok")
        self.status_lbl.setText(f"✓  Created {len(created)} missing folder(s) for Midna's Devotion.")

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self._modal_parent(), on_jump_to_setup=getattr(self, "_on_jump_to_setup", None))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_all()

    # --- Step 1 Character & Seed Helpers ---
    def _selected_char_entry(self) -> Optional[CoreModEntry]:
        """Return the ``CoreModEntry`` matching the active Step 1 character selection, or None."""
        path = self.char_combo.currentData()
        if not path:
            return None
        target_key = _norm_path_key(str(path))
        return next((e for e in self.char_mods if _norm_path_key(e.path) == target_key), None)

    def _show_add_char_menu(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        menu = QMenu(self)
        act_arc = menu.addAction("Import Character Mod from Archive (.zip / .7z / .rar)…")
        act_dir = menu.addAction("Link Existing Character Mod Folder…")
        chosen = menu.exec(self.btn_add_char.mapToGlobal(QPoint(0, self.btn_add_char.height())))
        if chosen == act_arc:
            self._import_archive_into_dir(self.cfg.core_slot_dir("character"), select_in_char=True)
        elif chosen == act_dir:
            start_dir = self.cfg.backup_dir if (self.cfg.backup_dir and os.path.isdir(self.cfg.backup_dir)) else os.path.expanduser("~")
            folder = ask_directory("Select Character Mod Folder (containing romfs/)", start_dir, qt_parent=self)
            if not folder:
                return
            try:
                entry = self.cfg.link_custom_core_mod("character", folder)
            except Exception as exc:
                QMessageBox.warning(self, "Invalid Mod Folder", str(exc))
                return
            self.refresh_all()
            self._select_combo_by_path(self.char_combo, entry.path)

    def _remove_selected_char_mod(self) -> None:
        entry = self._selected_char_entry()
        if not entry or entry.source_label == "Library":
            return
        msg = (
            f"Unlink '{entry.name}' from the character dropdown?\n\nYour files on disk will NOT be deleted."
            if entry.source_label == "Custom"
            else f"Delete the imported copy of '{entry.name}' from your manager workspace?"
        )
        ans = QMessageBox.question(
            self, "Remove Character Mod?", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            self.cfg.remove_core_mod(entry)
        except Exception as exc:
            QMessageBox.warning(self, "Remove Failed", str(exc))
            return
        self.char_combo.setCurrentIndex(0)
        self.refresh_all()

    def _browse_seed_folder(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        start_dir = self.cfg.uninstalled_seeds_dir or self.cfg.backup_dir or os.path.expanduser("~")
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~")
        folder = ask_directory("Select Randomizer Seed Folder", start_dir, qt_parent=self)
        if not folder:
            return
        try:
            seed_path = self.cfg.add_custom_seed_folder(folder)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Seed Folder", str(exc))
            return
        self.refresh_all()
        self._select_combo_by_path(self.seed_combo, seed_path)

    def _sync_character_list_row(self) -> None:
        char_path = self.char_combo.currentData()
        ent = self._selected_char_entry()
        if not char_path:
            if self.mod_list.count() > 0 and self.mod_list.item(0).data(Qt.ItemDataRole.UserRole) == "__step1_character__":
                self.mod_list.blockSignals(True)
                try:
                    self.mod_list.takeItem(0)
                finally:
                    self.mod_list.blockSignals(False)
            return

        label_raw = ent.name if ent and getattr(ent, "name", None) else os.path.basename(str(char_path))
        disp = pretty_mod_name(label_raw)
        row_text = f"★  [Character] {disp}   —   Active via Step 1 (Applied on Build)"

        self.mod_list.blockSignals(True)
        try:
            if self.mod_list.count() > 0 and self.mod_list.item(0).data(Qt.ItemDataRole.UserRole) == "__step1_character__":
                item = self.mod_list.item(0)
            else:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, "__step1_character__")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.mod_list.insertItem(0, item)

            font = QFont()
            font.setBold(True)
            item.setText(row_text)
            item.setFont(font)
            if self._is_plain_ui():
                item.setForeground(QBrush(QColor("#1b5e50")))
                item.setBackground(QBrush(QColor("#e0f2ef")))
            else:
                item.setForeground(QBrush(QColor("#80cbc4")))
                item.setBackground(QBrush(QColor(16, 52, 46, 130)))
            item.setToolTip("Selected in Step 1 — automatically included when you click Apply in Step 4.")
        finally:
            self.mod_list.blockSignals(False)

    def _on_step1_changed(self) -> None:
        if not self._ui_ready:
            return
        busy = bool(self.worker and self.worker.isRunning())
        ent = self._selected_char_entry()
        self.btn_rm_char.setEnabled((not busy) and (ent is not None) and (ent.source_label in ("Imported", "Custom")))
        self._sync_character_list_row()
        self._update_mod_action_buttons()
        self._update_overlap_panel()
        self._update_setup_summary()

    # --- Step 2 Browse & Add Mods Helpers ---
    def _refresh_visual_library_picker(self) -> None:
        """Populate the Step 2 library picker with non-character mods from ``UserModLibrary``."""
        self.library_visual_mods = self.cfg.find_library_visual_mods()
        in_list_paths = {_norm_path_key(m.source_path) for m in self.standalone_mods}

        self.visual_lib_list.clear()
        if not self.library_visual_mods:
            empty = QListWidgetItem("No extra mods found in Mod Library — use '+ Import' or '+ Link' below.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(QBrush(QColor("#6c766d" if self._is_plain_ui() else "#888888")))
            self.visual_lib_list.addItem(empty)
            self._update_visual_picker_buttons()
            return

        for entry in self.library_visual_mods:
            already = _norm_path_key(entry.path) in in_list_paths
            label = f"✓  {pretty_mod_name(entry.name)}   (In Mod List)" if already else f"+  {pretty_mod_name(entry.name)}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.path)
            item.setToolTip(entry.path)
            if self._is_plain_ui():
                item.setForeground(QBrush(QColor("#2f7a55" if already else "#1f2a24")))
            else:
                item.setForeground(QBrush(QColor("#81c784" if already else "#e3f2fd")))
            self.visual_lib_list.addItem(item)
        self._update_visual_picker_buttons()

    def _recolor_visual_library_items(self) -> None:
        """Update foreground colors on Step 2 library items after switching themes."""
        plain = self._is_plain_ui()
        in_list_paths = {_norm_path_key(m.source_path) for m in self.standalone_mods}
        for i in range(self.visual_lib_list.count()):
            item = self.visual_lib_list.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            if not path:
                item.setForeground(QBrush(QColor("#6c766d" if plain else "#888888")))
                continue
            already = _norm_path_key(str(path)) in in_list_paths
            if plain:
                item.setForeground(QBrush(QColor("#2f7a55" if already else "#1f2a24")))
            else:
                item.setForeground(QBrush(QColor("#81c784" if already else "#e3f2fd")))

    def _update_visual_picker_buttons(self) -> None:
        """Enable or disable Step 2 action buttons based on selection and worker state."""
        if not self._ui_ready:
            return
        busy = bool(self.worker and self.worker.isRunning())
        in_list_paths = {_norm_path_key(m.source_path) for m in self.standalone_mods}
        can_add = any(
            it.data(Qt.ItemDataRole.UserRole)
            and _norm_path_key(str(it.data(Qt.ItemDataRole.UserRole))) not in in_list_paths
            for it in self.visual_lib_list.selectedItems()
        )
        self.btn_add_lib_vis.setEnabled((not busy) and can_add)
        self.btn_import_vis_arc.setEnabled(not busy)
        self.btn_link_vis_dir.setEnabled(not busy)

    def _add_selected_library_visuals(self) -> None:
        added_names: List[str] = []
        from oot_rando.midnas_devotion.core.dedupe import (
            ExistingModTarget,
            check_mod_duplicates,
            fingerprint_mod_dir,
        )
        from oot_rando.midnas_devotion.ui.dedupe_dialog import prompt_duplicate_resolution
        active_targets = [
            ExistingModTarget(name=m.name, path=m.source_path, origin=m.origin)
            for m in self.standalone_mods
        ]
        for it in self.visual_lib_list.selectedItems():
            path = it.data(Qt.ItemDataRole.UserRole)
            if not path:
                continue
            try:
                cand_fp = fingerprint_mod_dir(str(path))
                matches = check_mod_duplicates(cand_fp, active_targets)
                if matches:
                    action, _ = prompt_duplicate_resolution(
                        self,
                        cand_fp.display_name,
                        matches,
                        allow_replace=False,
                        allow_keep_both=True,
                        sandbox_mode=self.cfg.sandbox_mode,
                    )
                    if action == "cancel":
                        continue
                name = self.cfg.add_mod_folder_to_list(str(path))
                added_names.append(name)
                active_targets.append(ExistingModTarget(name=name, path=os.path.abspath(str(path)), origin="linked"))
            except Exception as exc:
                QMessageBox.warning(self, "Could Not Add Mod", str(exc))
        if not added_names:
            return
        self.refresh_all()
        self._check_and_select_mods_in_list(added_names)
        self._set_status_style("ok")
        self.status_lbl.setText(f"✓  Added {', '.join(pretty_mod_name(n) for n in added_names)} to your Mod List.")

    def _link_visual_folder_to_list(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        start_dir = self.cfg.backup_dir if (self.cfg.backup_dir and os.path.isdir(self.cfg.backup_dir)) else os.path.expanduser("~")
        folder = ask_directory("Select Mod Folder (containing romfs/)", start_dir, qt_parent=self)
        if not folder:
            return
        try:
            from oot_rando.midnas_devotion.core.dedupe import (
                ExistingModTarget,
                check_mod_duplicates,
                fingerprint_mod_dir,
            )
            from oot_rando.midnas_devotion.ui.dedupe_dialog import prompt_duplicate_resolution
            active_targets = [
                ExistingModTarget(name=m.name, path=m.source_path, origin=m.origin)
                for m in self.standalone_mods
            ]
            cand_fp = fingerprint_mod_dir(folder)
            matches = check_mod_duplicates(cand_fp, active_targets)
            if matches:
                action, _ = prompt_duplicate_resolution(
                    self,
                    cand_fp.display_name,
                    matches,
                    allow_replace=False,
                    allow_keep_both=True,
                    sandbox_mode=self.cfg.sandbox_mode,
                )
                if action == "cancel":
                    return
            name = self.cfg.add_mod_folder_to_list(folder)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Mod Folder", str(exc))
            return
        self.refresh_all()
        self._check_and_select_mods_in_list([name])
        self._set_status_style("ok")
        self.status_lbl.setText(f"✓  Added '{pretty_mod_name(name)}' to your Mod List.")

    def _import_visual_archive_to_list(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self._import_archive_into_dir(self.cfg.staged_mods_dir, select_in_char=False)

    def _import_archive_into_dir(self, target_parent_dir: str, select_in_char: bool) -> None:
        start_dir = os.path.expanduser("~/Downloads")
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~")
        path = ask_open_file(
            "Select Mod Archive",
            start_dir,
            qt_filter="Mod Archives (*.zip *.7z *.rar);;ZIP (*.zip);;7-Zip (*.7z);;RAR (*.rar)",
            qt_parent=self,
        )
        if not path:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with ArchiveHandle(path) as arc:
                variants, exefs_hits = list_archive_variants(arc)
                QApplication.restoreOverrideCursor()

                if exefs_hits:
                    QMessageBox.critical(
                        self,
                        "Unsupported Code Mod",
                        f"This archive contains {len(exefs_hits)} Switch code-mod file(s) (exefs/), "
                        "which stock Longshot cannot load.",
                    )
                    return
                if not variants:
                    QMessageBox.warning(
                        self,
                        "No romfs/ Folder Found",
                        "Could not find a romfs/ folder inside this archive.",
                    )
                    return

                if len(variants) == 1:
                    chosen_variant = variants[0]
                else:
                    labels = [v if v else "(Archive Root)" for v in variants]
                    picked, ok = QInputDialog.getItem(
                        self,
                        "Choose Mod Variant",
                        "This archive includes multiple versions. Pick the one to add:",
                        labels,
                        0,
                        False,
                    )
                    if not ok:
                        return
                    chosen_variant = variants[labels.index(picked)]

                suggested = (
                    os.path.basename(chosen_variant)
                    if chosen_variant
                    else os.path.splitext(os.path.basename(path))[0]
                )
                mod_name, ok = self._prompt_text_input(
                    "Name Mod",
                    "Enter a name for this mod:",
                    sanitize_mod_name(suggested),
                )
                if not ok or not mod_name.strip():
                    return
                safe_name = sanitize_mod_name(mod_name)
                if safe_name in MANAGED_MOD_NAMES or safe_name.startswith("OoT_Randomizer_"):
                    QMessageBox.warning(
                        self,
                        "Reserved Mod Name",
                        f"'{safe_name}' is a reserved system mod name. Please pick a different name.",
                    )
                    return

                from oot_rando.midnas_devotion.core.dedupe import (
                    check_mod_duplicates,
                    collect_existing_mod_targets,
                    fingerprint_archive_variant,
                )
                from oot_rando.midnas_devotion.ui.dedupe_dialog import prompt_duplicate_resolution
                cand_fp = fingerprint_archive_variant(arc, chosen_variant, display_name=safe_name)
                matches = check_mod_duplicates(cand_fp, collect_existing_mod_targets(self.cfg, self.standalone_mods))
                install_dir = target_parent_dir
                if matches:
                    action, target_match = prompt_duplicate_resolution(
                        self,
                        safe_name,
                        matches,
                        allow_replace=True,
                        allow_keep_both=True,
                        sandbox_mode=self.cfg.sandbox_mode,
                    )
                    if action == "cancel":
                        return
                    if action == "replace" and target_match is not None:
                        safe_name = target_match.existing_name
                        install_dir = os.path.dirname(target_match.existing_path)

                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                dst = install_archive_to_dir(arc, chosen_variant, safe_name, install_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        self.refresh_all()
        if select_in_char:
            self._select_combo_by_path(self.char_combo, os.path.abspath(dst))
            self._set_status_style("ok")
            self.status_lbl.setText(f"✓  Imported character mod '{os.path.basename(dst)}'.")
        else:
            self._check_and_select_mods_in_list([os.path.basename(dst)])
            self._set_status_style("ok")
            self.status_lbl.setText(f"✓  Added '{os.path.basename(dst)}' to your Mod List.")

    def _check_and_select_mods_in_list(self, names: List[str]) -> None:
        name_set = set(names)
        last_item = None
        for i in range(self.mod_list.count()):
            it = self.mod_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) in name_set:
                it.setCheckState(Qt.CheckState.Checked)
                last_item = it
        if last_item is not None:
            self.mod_list.setCurrentItem(last_item)

    @staticmethod
    def _select_combo_by_path(combo: QComboBox, target_path: Optional[str]) -> bool:
        """Select the combo entry whose ``UserRole`` path matches ``target_path`` (case-safe on Windows)."""
        if target_path is None:
            combo.setCurrentIndex(0)
            return True
        target_key = _norm_path_key(target_path)
        for i in range(combo.count()):
            d = combo.itemData(i)
            if d and _norm_path_key(str(d)) == target_key:
                combo.setCurrentIndex(i)
                return True
        return False

    # --- Step 3 Mod List Management Helpers ---
    def _selected_standalone_mod(self) -> Optional[StandaloneMod]:
        it = self.mod_list.currentItem()
        if not it:
            return None
        name = it.data(Qt.ItemDataRole.UserRole)
        return next((m for m in self.standalone_mods if m.name == name), None)

    def _update_mod_action_buttons(self) -> None:
        if not self._ui_ready:
            return
        busy = bool(self.worker and self.worker.isRunning())
        mod = self._selected_standalone_mod()
        row = self.mod_list.currentRow()
        has_sel = (mod is not None) and (not busy)

        has_pinned_char = self.mod_list.count() > 0 and self.mod_list.item(0).data(Qt.ItemDataRole.UserRole) == "__step1_character__"
        min_movable = 1 if has_pinned_char else 0
        self.btn_move_up.setEnabled(has_sel and row > min_movable)
        self.btn_move_dn.setEnabled(has_sel and row < self.mod_list.count() - 1)
        self.btn_inspect_mod.setEnabled(has_sel)
        self.btn_open_mod.setEnabled(has_sel)
        self.btn_rename_mod.setEnabled(has_sel and (mod is not None and mod.origin != "linked"))
        self.btn_delete_mod.setEnabled(has_sel)
        if mod and mod.origin == "linked":
            self.btn_delete_mod.setText("Remove" if getattr(self, "_compact_mode", False) else "Remove from List")
        else:
            self.btn_delete_mod.setText("Delete")

    def _move_selected_mod(self, delta: int) -> None:
        row = self.mod_list.currentRow()
        new_row = row + delta
        min_row = 1 if (self.mod_list.count() > 0 and self.mod_list.item(0).data(Qt.ItemDataRole.UserRole) == "__step1_character__") else 0
        if row < min_row or new_row < min_row or new_row >= self.mod_list.count():
            return
        self.mod_list.blockSignals(True)
        try:
            it = self.mod_list.takeItem(row)
            self.mod_list.insertItem(new_row, it)
            self.mod_list.setCurrentRow(new_row)
            order = [
                self.mod_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.mod_list.count())
                if self.mod_list.item(i).data(Qt.ItemDataRole.UserRole) != "__step1_character__"
            ]
        finally:
            self.mod_list.blockSignals(False)

        self.cfg.set_mod_order(order)
        self.standalone_mods = self.cfg.find_standalone_mods()
        self._update_mod_action_buttons()
        self._update_overlap_panel()
        self._update_setup_summary()

    def _show_mod_context_menu(self, pos: QPoint) -> None:
        it = self.mod_list.itemAt(pos)
        if not it or (self.worker and self.worker.isRunning()):
            return
        self.mod_list.setCurrentItem(it)
        mod = self._selected_standalone_mod()
        if not mod:
            return

        menu = QMenu(self)
        is_checked = it.checkState() == Qt.CheckState.Checked
        act_toggle = menu.addAction("Turn Off Mod" if is_checked else "Turn On Mod")
        menu.addSeparator()
        act_up = menu.addAction("Move Up (Lower Priority)")
        act_dn = menu.addAction("Move Down (Higher Priority)")
        menu.addSeparator()
        act_inspect = menu.addAction("Inspect Files…")
        act_open = menu.addAction("Open Mod Folder")
        menu.addSeparator()
        act_rename = menu.addAction("Rename Mod…") if mod.origin != "linked" else None
        act_delete = menu.addAction("Remove from List" if mod.origin == "linked" else "Delete Mod…")

        chosen = menu.exec(self.mod_list.mapToGlobal(pos))
        if chosen == act_toggle:
            it.setCheckState(Qt.CheckState.Unchecked if is_checked else Qt.CheckState.Checked)
        elif chosen == act_up:
            self._move_selected_mod(-1)
        elif chosen == act_dn:
            self._move_selected_mod(+1)
        elif chosen == act_inspect:
            self._inspect_selected_mod()
        elif chosen == act_open:
            self._open_selected_mod_folder()
        elif act_rename and chosen == act_rename:
            self._rename_selected_mod()
        elif chosen == act_delete:
            self._delete_selected_mod()

    def _inspect_selected_mod(self) -> None:
        mod = self._selected_standalone_mod()
        if not mod:
            return
        conflicts, auto_merged = self.cfg.mod_conflict_map(
            mod,
            self._enabled_standalone_mods(),
            char_path=self.char_combo.currentData(),
            rando_path=self.seed_combo.currentData(),
        )
        dlg = ModFilesDialog(mod, conflicts, auto_merged, self)
        dlg.exec()

    def _party_title_lookup(self) -> Dict[str, str]:
        import json as _json
        from pathlib import Path as _Path
        from oot_rando import paths as _paths

        mapping: Dict[str, str] = {}
        roots = []
        # Read-only lookup: never instantiate PartyLibrary() here (it acquires .lock and runs recover()).
        for fn_name in ("app_dir", "state_dir", "data_dir"):
            fn = getattr(_paths, fn_name, None)
            if callable(fn):
                base = _Path(fn())
                for sub in ("Parties", "parties"):
                    cand = base / sub
                    if cand not in roots:
                        roots.append(cand)

        for parties_root in roots:
            if not parties_root.is_dir():
                continue
            try:
                for pdir in parties_root.iterdir():
                    if not pdir.is_dir() or pdir.name.startswith("."):
                        continue
                    meta_file = pdir / "party.json"
                    if not meta_file.is_file():
                        continue
                    try:
                        meta = _json.loads(meta_file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    pname = str(meta.get("name") or "").strip()
                    if not pname:
                        continue
                    sid = str(meta.get("seed_id") or "").strip()
                    if sid:
                        mapping["seed:" + sid] = pname
                        mapping["seed16:" + sid[:16]] = pname
                    if meta.get("mod_name"):
                        mapping["mod:" + str(meta["mod_name"])] = pname
                    if meta.get("id"):
                        mapping["id:" + str(meta["id"])] = pname
            except OSError:
                continue
        return mapping

    def _party_title_for_seed(self, seed_path: str, lookup: Optional[Dict[str, str]] = None) -> str:
        import json as _json
        from pathlib import Path as _Path

        if not seed_path:
            return ""
        lut = lookup if lookup is not None else self._party_title_lookup()
        if not lut:
            return ""
        sp = _Path(seed_path)
        mf = sp / "manifest.json"
        if mf.is_file():
            try:
                m = _json.loads(mf.read_text(encoding="utf-8"))
                sid = str(m.get("seed_id") or "")
                if sid:
                    if ("seed:" + sid) in lut:
                        return lut["seed:" + sid]
                    if ("seed16:" + sid[:16]) in lut:
                        return lut["seed16:" + sid[:16]]
            except Exception:
                pass
        bname = sp.name
        if ("mod:" + bname) in lut:
            return lut["mod:" + bname]
        if bname.startswith("OoT_Randomizer_"):
            tail = bname[len("OoT_Randomizer_"):]
            if ("seed16:" + tail[:16]) in lut:
                return lut["seed16:" + tail[:16]]
        for parent in sp.parents:
            if ("id:" + parent.name) in lut:
                return lut["id:" + parent.name]
        return ""

    def _open_overlap_inspector(self) -> None:
        from oot_rando.midnas_devotion.ui.conflict_inspector_dialog import ConflictInspectorDialog
        enabled = self._enabled_standalone_mods()
        rows = self.cfg.build_overlap_breakdown(
            enabled,
            char_path=self.char_combo.currentData(),
            rando_path=self.seed_combo.currentData(),
        )
        dlg = ConflictInspectorDialog(rows, parent=self, plain=self._is_plain_ui())
        dlg.exec()

    def _capture_current_loadout(self) -> Dict:
        enabled_names = [m.name for m in self._enabled_standalone_mods()]
        mod_order = [
            self.mod_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.mod_list.count())
            if self.mod_list.item(i).data(Qt.ItemDataRole.UserRole) != "__step1_character__"
        ]
        party_name = ""
        seed_path = self.seed_combo.currentData()
        if seed_path:
            party_name = self._party_title_for_seed(str(seed_path))
        return {
            "party_name": party_name,
            "selected_char_path": self.char_combo.currentData(),
            "prefer_rando_logo": bool(self.cb_prefer_rando_logo.isChecked()),
            "enabled_standalone": enabled_names,
            "mod_order": mod_order,
        }

    def _apply_loadout_preset(self, name: str) -> None:
        preset = self.cfg.get_preset(name)
        if not preset:
            return
        updates = {
            "selected_char_path": preset.get("selected_char_path"),
            "prefer_rando_logo": bool(preset.get("prefer_rando_logo", True)),
            "enabled_standalone": list(preset.get("enabled_standalone") or []),
            "mod_order": list(preset.get("mod_order") or []),
        }
        self.cfg.save_settings(updates)
        if updates["selected_char_path"]:
            self._select_combo_by_path(self.char_combo, updates["selected_char_path"])
        else:
            self.char_combo.setCurrentIndex(0)
        self.cb_prefer_rando_logo.setChecked(updates["prefer_rando_logo"])
        self.refresh_all()
        self.status_lbl.setText("Applied loadout preset: " + name)

    def _open_presets_menu(self) -> None:
        import importlib
        qtw = importlib.import_module(type(self.mod_list).__module__)
        menu = qtw.QMenu(self)

        save_act = menu.addAction("Save Current Loadout…")
        def _do_save():
            name, ok = qtw.QInputDialog.getText(self, "Save Mod Loadout", "Loadout name (e.g. QoL Only, Full Visuals):")
            if ok and name.strip():
                self.cfg.save_preset(name.strip(), self._capture_current_loadout())
                self.status_lbl.setText("Saved loadout preset: " + name.strip())
        save_act.triggered.connect(_do_save)

        presets = self.cfg.list_presets()
        if presets:
            menu.addSeparator()
            apply_menu = menu.addMenu("Apply Loadout")
            del_menu = menu.addMenu("Delete Loadout")
            for pname in sorted(presets.keys(), key=str.casefold):
                pdata = presets.get(pname) or {}
                linked_party = str(pdata.get("party_name") or "").strip()
                menu_lbl = f"{pname}  ·  Party: {linked_party}" if linked_party else pname
                a = apply_menu.addAction(menu_lbl)
                a.triggered.connect(lambda _c=False, n=pname: self._apply_loadout_preset(n))
                d = del_menu.addAction(pname)
                def _do_del(_c=False, n=pname):
                    self.cfg.delete_preset(n)
                    self.status_lbl.setText("Deleted loadout preset: " + n)
                d.triggered.connect(_do_del)
        else:
            empty_act = menu.addAction("(No saved loadouts yet)")
            empty_act.setEnabled(False)

        menu.exec(self.btn_presets.mapToGlobal(self.btn_presets.rect().bottomLeft()))

    def _open_selected_mod_folder(self) -> None:
        """Open the selected mod's folder on disk using the OS file manager."""
        mod = self._selected_standalone_mod()
        if not mod:
            return
        if os.path.isdir(mod.source_path):
            try:
                open_in_file_manager(mod.source_path, env=clean_subprocess_env())
            except OSError as exc:
                QMessageBox.warning(self, "Could Not Open Folder", str(exc))
        else:
            QMessageBox.warning(self, "Folder Not Found", f"Folder no longer exists:\n{mod.source_path}")
            self.refresh_all()

    def _rename_selected_mod(self) -> None:
        mod = self._selected_standalone_mod()
        if not mod:
            return
        if mod.origin == "linked":
            return
        if mod.origin == "live" and self.cfg.sandbox_mode:
            QMessageBox.information(
                self,
                "Protected in Test Mode",
                f"'{mod.name}' is currently inside your live game folder.\n\n"
                "Test Mode never modifies your live game. Switch to Live Mode at the top to rename it.",
            )
            return

        new_raw, ok = self._prompt_text_input(
            "Rename Mod",
            f"Enter a new folder name for '{mod.name}':",
            mod.name,
        )
        if not ok or not new_raw.strip():
            return

        try:
            new_name = self.cfg.rename_standalone_mod(mod, new_raw)
        except Exception as exc:
            QMessageBox.warning(self, "Rename Failed", str(exc))
            return

        cur_item = self.mod_list.currentItem()
        if cur_item and cur_item.data(Qt.ItemDataRole.UserRole) == mod.name:
            cur_item.setData(Qt.ItemDataRole.UserRole, new_name)

        self.refresh_all()
        for i in range(self.mod_list.count()):
            it = self.mod_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == new_name:
                self.mod_list.setCurrentItem(it)
                break
        self._set_status_style("ok")
        self.status_lbl.setText(f"✓  Renamed '{mod.name}' to '{new_name}'.")

    def _delete_selected_mod(self) -> None:
        mod = self._selected_standalone_mod()
        if not mod:
            return

        if mod.origin == "linked":
            ans = QMessageBox.question(
                self,
                "Remove from Mod List?",
                f"Remove '{pretty_mod_name(mod.name)}' from your active Mod List?\n\n"
                f"Your original files in:\n{mod.source_path}\nwill NOT be deleted — you can add it back anytime from Step 2.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            try:
                self.cfg.delete_standalone_mod(mod)
            except Exception as exc:
                QMessageBox.critical(self, "Remove Failed", str(exc))
                return
            self.refresh_all()
            self._set_status_style("warn")
            self.status_lbl.setText(f"Removed '{pretty_mod_name(mod.name)}' from the Mod List (files kept intact).")
            return

        if mod.origin == "live" and self.cfg.sandbox_mode:
            QMessageBox.information(
                self,
                "Protected in Test Mode",
                f"'{mod.name}' is currently inside your live game folder.\n\n"
                "Test Mode never modifies your live game. Just uncheck it to test without it, "
                "or switch to Live Mode at the top to permanently delete it.",
            )
            return

        origin_desc = {
            "live": "your LIVE game mods folder",
            "staged": "your added mods workspace",
            "disabled": "your disabled mods workspace",
        }.get(mod.origin, mod.origin)

        ans = QMessageBox.warning(
            self,
            "Delete Mod?",
            f"Permanently delete '{mod.name}' from {origin_desc}?\n\n"
            f"Folder: {mod.source_path}\n"
            f"Files: {mod.file_count}\n\n"
            "This cannot be undone. (Tip: if you only want to turn it off temporarily, just uncheck it instead.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return

        try:
            removed = self.cfg.delete_standalone_mod(mod)
        except Exception as exc:
            QMessageBox.critical(self, "Delete Failed", str(exc))
            return

        self.refresh_all()
        self._set_status_style("warn")
        self.status_lbl.setText(f"Deleted '{mod.name}' ({len(removed)} folder copy(s) removed).")

    # --- Window-Wide Drag-and-Drop ---
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if (self.worker and self.worker.isRunning()) or not self.cfg.is_configured:
            event.ignore()
            return
        if _extract_archive_paths(event.mimeData()):
            self.drop_zone.set_drag_active(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if _extract_archive_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.drop_zone.set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.drop_zone.set_drag_active(False)
        paths = _extract_archive_paths(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self._handle_dropped_archives(paths)

    def _handle_dropped_archives(self, paths: List[str]) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.cfg.is_configured:
            QMessageBox.warning(self, "Folders Not Configured", "Please configure your base romfs/ folder first.")
            self._open_settings()
            return
        from oot_rando.party_health import preflight_mods_operation
        pf = preflight_mods_operation(self.cfg.target_mods_dir)
        if not pf["ok"]:
            QMessageBox.warning(self, "Preflight Check Failed", chr(10).join(pf["errors"]))
            return
        for path in paths:
            self._open_preflight(initial_archive=path)

    def _browse_and_preflight(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.cfg.is_configured:
            QMessageBox.warning(self, "Folders Not Configured", "Please configure your base romfs/ folder first.")
            self._open_settings()
            return
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
            self._open_preflight(initial_archive=path)

    def _toggle_log_view(self, checked: bool) -> None:
        self.log_view.setVisible(checked)
        self.log_toggle_btn.setText("Hide Technical Log ▴" if checked else "Show Technical Log ▾")

    def _restore_initial_selections(self) -> None:
        st = self.cfg.saved_state
        self.cb_prefer_rando_logo.setChecked(bool(st.get("prefer_rando_logo", False)))

        if "selected_char_path" in st:
            self._select_combo_by_path(self.char_combo, st.get("selected_char_path"))
        else:
            legacy_char = st.get("char_key", "zelda")
            target_folder = {"zelda": "PlayableZeldaCostumes", "malon": "PlayableMalonCostumes"}.get(legacy_char)
            if target_folder:
                match = next((e for e in self.char_mods if e.name == target_folder), None)
                if match:
                    self._select_combo_by_path(self.char_combo, match.path)

    def _update_mode_ui(self) -> None:
        configured = self.cfg.is_configured
        plain = self._is_plain_ui()
        if not configured:
            if plain:
                self.settings_btn.setStyleSheet(
                    "QPushButton { background: #d5a62b; color: #2b2108; border: 1px solid #c0921c; "
                    "font-weight: bold; padding: 5px 10px; border-radius: 4px; }"
                    "QPushButton:hover { background: #e2b746; }"
                )
            else:
                self.settings_btn.setStyleSheet(
                    "QPushButton { background: rgba(239, 108, 0, 200); color: #fff; font-weight: bold; padding: 5px 10px; border-radius: 4px; }"
                    "QPushButton:hover { background: rgba(245, 124, 0, 215); }"
                )
            self._set_status_style("warn")
            self.status_lbl.setText("⚠  Click 'Configure Folders…' at the top right to point to your Longshot installation.")
        else:
            self.settings_btn.setStyleSheet("")

        if self.cfg.sandbox_mode:
            self.mode_badge.setText("TEST MODE · Safe (Won't Touch Your Live Game)")
            self.mode_badge.setStyleSheet(
                "font-weight: bold; padding: 6px 12px; border-radius: 5px; "
                "background: #f8eecf; border: 1px solid #d5a62b; color: #7a520b;"
                if plain
                else "font-weight: bold; padding: 6px 12px; border-radius: 5px; "
                "background: rgba(58, 36, 9, 175); border: 1px solid #ef6c00; color: #ffcc80;"
            )
            self.mode_btn.setText("Switch to Live Game")
            self.build_btn.setText("Apply & Build in Test Mode")
            self.path_label.setText(f"Output: {self.cfg.sandbox_mods_dir}")
        else:
            self.mode_badge.setText("LIVE MODE · Applies Directly to Longshot")
            self.mode_badge.setStyleSheet(
                "font-weight: bold; padding: 6px 12px; border-radius: 5px; "
                "background: #e4efe7; border: 1px solid #2f7a55; color: #1f5439;"
                if plain
                else "font-weight: bold; padding: 6px 12px; border-radius: 5px; "
                "background: rgba(22, 51, 27, 175); border: 1px solid #2e7d32; color: #a5d6a7;"
            )
            self.mode_btn.setText("Switch to Test Mode")
            self.build_btn.setText("Apply & Build to Live Game")
            self.path_label.setText(f"Output: {self.cfg.live_mods_dir or '(not set)'}")

        self.build_btn.setEnabled(configured and not (self.worker and self.worker.isRunning()))
        self._update_mod_action_buttons()
        self._update_visual_picker_buttons()
        self._refresh_responsive_labels()

    def _toggle_mode(self) -> None:
        if self.cfg.sandbox_mode:
            if not self.cfg.live_mods_dir:
                QMessageBox.warning(
                    self,
                    "Live Mods Folder Not Set",
                    "Set your Live Mods Folder in 'Configure Folders…' before switching to Live Mode.",
                )
                self._open_settings()
                return
            ans = QMessageBox.question(
                self,
                "Switch to Live Game Mode?",
                f"Live Mode applies your mod setup directly to:\n{self.cfg.live_mods_dir}\n\n"
                "• Any standalone mods you uncheck are moved safely aside (never deleted).\n"
                "• Your Mod Library backups stay untouched.\n\nSwitch to Live Mode?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            self.cfg.sandbox_mode = False
        else:
            self.cfg.sandbox_mode = True
        self._update_mode_ui()
        self._update_overlap_panel()

    def refresh_all(self) -> None:
        """Reload characters, seeds, library mods, and active list from disk (deferred if a build is running)."""
        if self.worker and self.worker.isRunning():
            self._pending_refresh = True
            return
        self._pending_refresh = False
        if hasattr(self, "midna_dancer") and getattr(self.midna_dancer, "state", "idle") == "idle":
            self.midna_dancer.set_state("scanning")
        # 1. Refresh Playable Character dropdown
        prev_char = self.char_combo.currentData()
        self.char_mods = self.cfg.find_core_mods("character")
        self.char_combo.blockSignals(True)
        self.char_combo.clear()
        self.char_combo.addItem("Vanilla Link (Original Character)", None)
        for entry in self.char_mods:
            self.char_combo.addItem(entry.display_label, entry.path)
        if self._initial_restored and prev_char:
            self._select_combo_by_path(self.char_combo, prev_char)
        self.char_combo.blockSignals(False)

        if not self._initial_restored:
            self._initial_restored = True
            self._restore_initial_selections()

        # 2. Refresh Randomizer Seeds
        prev_seed = self.seed_combo.currentData()
        self.seeds = self.cfg.find_seeds()
        self.seed_combo.blockSignals(True)
        self.seed_combo.clear()
        party_titles = self._party_title_lookup()
        for idx, seed in enumerate(self.seeds):
            base_lbl = _friendly_seed_label(seed, is_newest=(idx == 0))
            ptitle = self._party_title_for_seed(seed.path, party_titles)
            label = (ptitle + " — " + base_lbl) if ptitle else base_lbl
            self.seed_combo.addItem(label, seed.path)
        self.seed_combo.addItem("No Randomizer (Play Normal Story)", None)
        if prev_seed:
            self._select_combo_by_path(self.seed_combo, prev_seed)
        self.seed_combo.blockSignals(False)

        # 3. Refresh Unified Mod List on the right
        prev_selected_name = None
        if self.mod_list.currentItem():
            prev_selected_name = self.mod_list.currentItem().data(Qt.ItemDataRole.UserRole)

        prev_checks: Dict[str, bool] = {}
        for i in range(self.mod_list.count()):
            it = self.mod_list.item(i)
            prev_checks[it.data(Qt.ItemDataRole.UserRole)] = it.checkState() == Qt.CheckState.Checked

        self.standalone_mods = self.cfg.find_standalone_mods()
        saved_enabled = self.cfg.saved_state.get("enabled_standalone")

        self.mod_list.blockSignals(True)
        try:
            self.mod_list.clear()
            restore_row = -1
            for row_idx, mod in enumerate(self.standalone_mods):
                item = QListWidgetItem(mod.name)
                item.setData(Qt.ItemDataRole.UserRole, mod.name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if mod.name in prev_checks:
                    checked = prev_checks[mod.name]
                elif saved_enabled is not None:
                    checked = mod.name in saved_enabled
                else:
                    checked = mod.origin in ("live", "staged", "linked")
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                self.mod_list.addItem(item)
                if mod.name == prev_selected_name:
                    restore_row = row_idx
            if restore_row >= 0:
                self.mod_list.setCurrentRow(restore_row)
        finally:
            self.mod_list.blockSignals(False)

        self._refresh_visual_library_picker()
        # _on_step1_changed syncs the pinned character row, action buttons, overlap panel, and summary.
        self._on_step1_changed()
        self._update_mode_ui()
        self.launch_btn.setEnabled(bool(self.cfg.longshot_binary and os.path.isfile(self.cfg.longshot_binary)))
        if hasattr(self, "midna_dancer") and getattr(self.midna_dancer, "state", "") == "scanning" and not (self.worker and self.worker.isRunning()):
            self.midna_dancer.set_state("idle")

    def _on_mod_toggled(self) -> None:
        self._update_overlap_panel()
        self._update_setup_summary()

    def _enabled_standalone_mods(self) -> List[StandaloneMod]:
        by_name = {m.name: m for m in self.standalone_mods}
        out: List[StandaloneMod] = []
        for i in range(self.mod_list.count()):
            it = self.mod_list.item(i)
            name = it.data(Qt.ItemDataRole.UserRole)
            if name == "__step1_character__":
                continue
            if it.checkState() == Qt.CheckState.Checked and name in by_name:
                out.append(by_name[name])
        return out

    def _update_setup_summary(self) -> None:
        if not self._ui_ready:
            return
        char_path = self.char_combo.currentData()
        seed_path = self.seed_combo.currentData()

        parts = [pretty_mod_name(os.path.basename(char_path)) if char_path else "Vanilla Link"]
        if seed_path:
            ptitle = self._party_title_for_seed(seed_path)
            s_disp = os.path.basename(seed_path).replace("OoT_Randomizer_", "Seed ")
            parts.append((ptitle + " (" + s_disp + ")") if ptitle else s_disp)
        else:
            parts.append("No Randomizer")

        enabled = self._enabled_standalone_mods()
        active_mods = [m for m in enabled if not self.cfg.is_malon_skeleton_conflict(char_path, m.source_path)]
        merged_cnt = sum(1 for m in active_mods if self.cfg.mod_merge_kind(m) != "standalone")
        dropin_cnt = len(active_mods) - merged_cnt

        if merged_cnt:
            parts.append(f"{merged_cnt} Auto-Merged Mod" + ("" if merged_cnt == 1 else "s"))
        if dropin_cnt:
            parts.append(f"{dropin_cnt} Drop-In Mod" + ("" if dropin_cnt == 1 else "s"))
        if not active_mods:
            parts.append("0 Extra Mods")

        self.summary_label.setText("Loadout:   " + "  +  ".join(parts))

    def _update_overlap_panel(self) -> None:
        char_path = self.char_combo.currentData()
        rando_path = self.seed_combo.currentData()
        enabled = self._enabled_standalone_mods()
        overlaps, auto_merged = self.cfg.classify_overlaps(enabled, char_path=char_path, rando_path=rando_path)

        mod_conflicts: Dict[str, Dict[str, List[str]]] = {}
        for rel, owners in overlaps.items():
            for owner in owners:
                for other in owners:
                    if other != owner:
                        mod_conflicts.setdefault(owner, {}).setdefault(other, []).append(rel)

        mod_auto_reasons: Dict[str, List[str]] = {}
        for rel, (owners, reasons) in auto_merged.items():
            for owner in owners:
                mod_auto_reasons.setdefault(owner, []).extend(reasons)

        by_name = {m.name: m for m in self.standalone_mods}
        bold_font = QFont()
        bold_font.setBold(True)
        normal_font = QFont()

        malon_skipped: List[str] = []
        from oot_rando.midnas_devotion.core.dedupe import find_internal_duplicates
        internal_dupes = find_internal_duplicates(self.standalone_mods)

        self.mod_list.blockSignals(True)
        try:
            for i in range(self.mod_list.count()):
                it = self.mod_list.item(i)
                name = it.data(Qt.ItemDataRole.UserRole)
                mod = by_name.get(name)
                if not mod:
                    continue
                is_checked = it.checkState() == Qt.CheckState.Checked
                disp = pretty_mod_name(mod.name)
                f_word = "file" if mod.file_count == 1 else "files"
                merge_kind = self.cfg.mod_merge_kind(mod)

                plain = self._is_plain_ui()
                if not is_checked:
                    it.setText(f"○   {disp}   —   Off ({mod.file_count} {f_word})")
                    it.setFont(normal_font)
                    it.setForeground(QBrush(QColor("#6c766d" if plain else "#9e9e9e")))
                    it.setBackground(QBrush(QColor("#f2eee3") if plain else QColor(22, 26, 33, 95)))
                    it.setToolTip("Turned off — will not be loaded in-game.")
                elif self.cfg.is_malon_skeleton_conflict(char_path, mod.source_path):
                    malon_skipped.append(disp)
                    it.setText(f"⚠   {disp}   —   Auto-Skipped on Playable Malon")
                    it.setFont(bold_font)
                    it.setForeground(QBrush(QColor("#8a540b" if plain else "#ffcc80")))
                    it.setBackground(QBrush(QColor("#f8eecf") if plain else QColor(68, 42, 12, 135)))
                    it.setToolTip(
                        "Automatically skipped while Playable Malon is selected in Step 1 to prevent Adult Malon skeleton glitches."
                    )
                elif name in internal_dupes:
                    dup_others = ", ".join(pretty_mod_name(o) for o in internal_dupes[name])
                    it.setText(f"⚠   {disp}   —   Exact Duplicate of {dup_others}")
                    it.setFont(bold_font)
                    it.setForeground(QBrush(QColor("#8a540b" if plain else "#ffcc80")))
                    it.setBackground(QBrush(QColor("#f8eecf" if plain else QColor(68, 42, 12, 135))))
                    it.setToolTip(
                        f"Identical CRC32/SHA-256 romfs/ contents to: {dup_others}.\n"
                        "You can safely uncheck or remove one copy."
                    )
                elif name in mod_conflicts:
                    other_names = sorted(mod_conflicts[name].keys())
                    bad_files = sorted({f for fl in mod_conflicts[name].values() for f in fl})
                    it.setText(f"⚠   {disp}   —   Conflicts with {', '.join(other_names)}")
                    it.setFont(bold_font)
                    it.setForeground(QBrush(QColor("#8a540b" if plain else "#ffcc80")))
                    it.setBackground(QBrush(QColor("#f8eecf") if plain else QColor(68, 42, 12, 135)))
                    preview = "\n".join(f"• {f}" for f in bad_files[:8])
                    if len(bad_files) > 8:
                        preview += f"\n… and {len(bad_files) - 8} more"
                    it.setToolTip(
                        f"Shares {len(bad_files)} non-mergeable file(s) with {', '.join(other_names)}:\n{preview}\n\n"
                        "Uncheck one mod or use ▲ / ▼ to choose priority."
                    )
                elif name in mod_auto_reasons or merge_kind != "standalone":
                    tag = "Auto-Merges UI & Memory" if merge_kind == "ui_merge" else (
                        "Auto-Merges Model & Memory" if merge_kind == "model_merge" else "Auto-Merges Audio"
                    )
                    it.setText(f"⇄   {disp}   —   {tag} ({mod.file_count} {f_word})")
                    it.setFont(bold_font)
                    it.setForeground(QBrush(QColor("#244c73" if plain else "#81d4fa")))
                    it.setBackground(QBrush(QColor("#e6eff7") if plain else QColor(16, 48, 72, 135)))
                    it.setToolTip(
                        "Safely merged into your main game on Apply (handles UI layouts, dialogue, memory headroom, and audio tables)."
                    )
                else:
                    tag = "Ready · Safe" if mod.origin == "staged" else "Active · Safe"
                    it.setText(f"✓   {disp}   —   {tag} ({mod.file_count} {f_word})")
                    it.setFont(bold_font)
                    it.setForeground(QBrush(QColor("#225c3e" if plain else "#a5d6a7")))
                    it.setBackground(QBrush(QColor("#e4efe7") if plain else QColor(18, 52, 28, 135)))
                    it.setToolTip("Drop-in safe — zero conflicts with your main game or other enabled mods.")
        finally:
            self.mod_list.blockSignals(False)

        plain = self._is_plain_ui()
        if not self.standalone_mods:
            self.overlap_card.setStyleSheet(
                "QFrame { background: #f7f3ea; border: 1px solid #e3dccb; border-radius: 5px; }"
                if plain
                else "QFrame { background: rgba(32, 36, 42, 155); border: 1px solid #444444; border-radius: 5px; }"
            )
            self.overlap_title.setStyleSheet("border: none; color: #1f2a24;" if plain else "border: none; color: #cccccc;")
            self.overlap_detail.setStyleSheet("border: none; color: #6c766d;" if plain else "border: none; color: #aaaaaa;")
            self.overlap_title.setText("No mods added yet")
            self.overlap_detail.setText("Add mods from Step 2 on the left, or drop any mod archive above.")
        elif not overlaps:
            self.overlap_card.setStyleSheet(
                "QFrame { background: #e4efe7; border: 1px solid #2f7a55; border-radius: 5px; }"
                if plain
                else "QFrame { background: rgba(18, 43, 22, 165); border: 1px solid #2e7d32; border-radius: 5px; }"
            )
            self.overlap_title.setStyleSheet("border: none; color: #1f5439;" if plain else "border: none; color: #a5d6a7;")
            self.overlap_detail.setStyleSheet("border: none; color: #2f5e46;" if plain else "border: none; color: #cfe8d1;")
            extra_note = f" ({', '.join(malon_skipped)} auto-skipped for Playable Malon.)" if malon_skipped else ""
            if auto_merged:
                self.overlap_title.setText(f"✓  All Good — Auto-Merging Compatible Layers ({len(enabled)} checked)")
                self.overlap_detail.setText(
                    "Blue items merge UI, memory tables, dialogue, and audio automatically when you click Apply." + extra_note
                )
            else:
                self.overlap_title.setText(f"✓  All Good — No Conflicts ({len(enabled)} checked)")
                self.overlap_detail.setText(
                    "Every checked mod works cleanly together." + extra_note
                )
        else:
            self.overlap_card.setStyleSheet(
                "QFrame { background: #f8eecf; border: 1px solid #b3741a; border-radius: 5px; }"
                if plain
                else "QFrame { background: rgba(51, 34, 13, 170); border: 1px solid #ef6c00; border-radius: 5px; }"
            )
            self.overlap_title.setStyleSheet("border: none; color: #7a4d0e;" if plain else "border: none; color: #ffcc80;")
            self.overlap_detail.setStyleSheet("border: none; color: #6e4c1b;" if plain else "border: none; color: #ffe0b2;")
            self.overlap_title.setText(f"⚠  {len(overlaps)} File Conflict(s) Detected")
            sample = []
            for rel, owners in list(overlaps.items())[:3]:
                sample.append(f"• {' vs '.join(owners)}  ({os.path.basename(rel)})")
            if len(overlaps) > 3:
                sample.append(f"… and {len(overlaps) - 3} more (select a mod & click Inspect Files)")
            self.overlap_detail.setText(
                "Uncheck one of the conflicting mods below (or use ▲ / ▼ to set priority):\n"
                + "\n".join(sample)
            )

    def _open_preflight(self, initial_archive: Optional[str] = None) -> None:
        dlg = PreflightDialog(self.cfg, self._enabled_standalone_mods(), self, initial_archive=initial_archive)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_all()
            if dlg.installed_mod_name:
                self._check_and_select_mods_in_list([dlg.installed_mod_name])

    def _open_target_dir(self) -> None:
        """Create (if needed) and open the active Sandbox or Live mods directory in the file manager."""
        target = self.cfg.target_mods_dir
        if not target:
            QMessageBox.warning(self, "Folder Not Set", "Configure your folders first.")
            return
        try:
            os.makedirs(target, exist_ok=True)
            open_in_file_manager(target, env=clean_subprocess_env())
        except OSError as exc:
            QMessageBox.warning(self, "Could Not Open Folder", str(exc))

    def _launch_longshot(self) -> None:
        """Spawn the configured Longshot executable with a sanitized subprocess environment."""
        binary = self.cfg.longshot_binary
        if not binary or not os.path.isfile(binary):
            QMessageBox.warning(self, "Longshot Not Set", "Set your Longshot executable in 'Configure Folders…'.")
            return
        if self.cfg.sandbox_mode:
            res = QMessageBox.information(
                self,
                "Test Mode Reminder",
                "You are currently in Test Mode, so Longshot will launch using your LIVE mods folder "
                "(not the Test Mode preview).\n\nLaunch Longshot anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if res != QMessageBox.StandardButton.Yes:
                return
        try:
            subprocess.Popen([binary], cwd=self.cfg.launch_cwd, env=clean_subprocess_env(), close_fds=True)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Launch Failed",
                f"Could not start Longshot:\n{binary}\n\n{exc}",
            )
            return
        self._set_status_style("ok")
        self.status_lbl.setText("▶  Launched Longshot!")
        self.log_view.appendPlainText(f"Launched: {binary}")

    def _start_build(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        ok, issues = self.cfg.validate_paths()
        if not ok:
            QMessageBox.warning(self, "Configure Folders First", "\n• ".join(issues))
            self._open_settings()
            return

        enabled_names = [m.name for m in self._enabled_standalone_mods()]
        all_order = [
            self.mod_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.mod_list.count())
            if self.mod_list.item(i).data(Qt.ItemDataRole.UserRole) != "__step1_character__"
        ]
        opts = BuildOptions(
            char_path=self.char_combo.currentData(),
            rando_path=self.seed_combo.currentData(),
            prefer_rando_logo=self.cb_prefer_rando_logo.isChecked(),
            enabled_standalone_names=enabled_names,
        )
        try:
            self.cfg.save_settings(
                {
                    "selected_char_path": opts.char_path,
                    "prefer_rando_logo": opts.prefer_rando_logo,
                    "enabled_standalone": enabled_names,
                    "mod_order": all_order,
                }
            )
        except OSError as exc:
            QMessageBox.warning(self, "Could Not Save Settings", str(exc))

        self.log_view.clear()
        self._build_log_view.clear()
        self._build_log_toggle.setChecked(False)
        self._build_back_btn.setVisible(False)
        self.progress.setValue(0)
        self._set_status_style("info")
        self.status_lbl.setText("Building your mod setup…")
        plain = self._is_plain_ui()
        self._style_build_page(plain, getattr(self, "_compact_mode", False))
        self._build_title_lbl.setText("Weaving Your Mods Together…")
        self._build_step_lbl.setText("Preparing build…")
        self.build_btn.setEnabled(False)
        self.mode_btn.setEnabled(False)
        self.drop_zone.setEnabled(False)

        worker = BuildWorker(self.cfg, opts)
        self.worker = worker
        worker.log_line.connect(self._on_log_line)
        worker.progress_val.connect(self.progress.setValue)
        worker.finished_ok.connect(self._on_build_ok)
        worker.failed.connect(self._on_build_failed)
        worker.finished.connect(worker.deleteLater)
        self._view_stack.setCurrentWidget(self._build_page)
        self.midna_dancer.set_state("merging")
        self.midna_dancer.start()
        worker.start()
        self._update_mod_action_buttons()
        self._update_visual_picker_buttons()

    def _on_log_line(self, line: str) -> None:
        """Append a worker log line to both log views and update the friendly step caption."""
        self.log_view.appendPlainText(line)
        self._build_log_view.appendPlainText(line)
        friendly = _friendly_step_from_log(line)
        if friendly:
            self.status_lbl.setText(friendly)
            self._build_step_lbl.setText(friendly)

    def _on_build_ok(self) -> None:
        """Finalize UI state after ``BuildWorker`` succeeds and refresh discovered mods."""
        self.worker = None
        self.midna_dancer.set_state("success")
        self.midna_dancer.stop()
        if hasattr(self, "party_banner"):
            self.party_banner.setVisible(False)
        self._view_stack.setCurrentWidget(self._main_page)
        self.build_btn.setEnabled(True)
        self.mode_btn.setEnabled(True)
        self.drop_zone.setEnabled(True)
        self._set_status_style("ok")
        if self.cfg.sandbox_mode:
            self.status_lbl.setText("✓  Test build complete! Your live game was not modified.")
        else:
            self.status_lbl.setText("✓  Live mods updated! Click 'Play Longshot' whenever you're ready.")
        self.refresh_all()

    def _on_build_failed(self, err: str) -> None:
        """Surface build failure details on the build page with theme-accessible error contrast."""
        self.worker = None
        self.midna_dancer.set_state("warning")
        self.midna_dancer.stop()
        self.build_btn.setEnabled(True)
        self.mode_btn.setEnabled(True)
        self.drop_zone.setEnabled(True)
        self._set_status_style("error")
        self.status_lbl.setText("✕  Build failed — see details below.")
        self.log_view.appendPlainText(f"\nERROR: {err}")
        self._build_log_view.appendPlainText(f"\nERROR: {err}")
        self._build_title_lbl.setText("✕  Build Failed")
        err_fg = "#b71c1c" if self._is_plain_ui() else "#ef9a9a"
        self._build_title_lbl.setStyleSheet(
            f"border: none; background: transparent; color: {err_fg}; font-size: 19px; font-weight: bold;"
        )
        self._build_step_lbl.setText(err)
        self._build_log_toggle.setChecked(True)
        self._build_back_btn.setVisible(True)
        if self._pending_refresh:
            self.refresh_all()
        else:
            self._update_mod_action_buttons()
            self._update_visual_picker_buttons()

    def closeEvent(self, event) -> None:
        """Prevent closing mid-build (avoiding Qt QThread abort) and stop animations on clean exit."""
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self,
                "Build In Progress",
                "Wait for Midna's Devotion to finish applying mods before closing.",
            )
            event.ignore()
            return
        if hasattr(self, "midna_dancer"):
            self.midna_dancer.stop()
        super().closeEvent(event)
