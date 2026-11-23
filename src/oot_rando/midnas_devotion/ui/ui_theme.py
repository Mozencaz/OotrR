"UI Experience themes and first-launch chooser for Midna's Devotion."
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

THEME_MOZENCAZ = "mozencaz"
THEME_ARARAGI = "araragi"
VALID_UI_THEMES = (THEME_MOZENCAZ, THEME_ARARAGI)


def _find_backdrop_path() -> Optional[str]:
    try:
        from oot_rando.midnas_devotion.launcher import resolve_asset

        resolved = resolve_asset("backdrop.png")
        if resolved and os.path.isfile(resolved):
            return resolved
    except Exception:
        pass
    local = Path(__file__).resolve().parent.parent / "assets" / "backdrop.png"
    return str(local) if local.is_file() else None


def container_bg_for_theme(theme_id: str) -> str:
    return "#f2eee3" if theme_id == THEME_MOZENCAZ else "#161a21"


def central_stylesheet(plain: bool) -> str:
    if plain:
        return (
            "QWidget#backdropCentral { background-color: #f2eee3; color: #1f2a24; } "
            "QWidget#backdropCentral QLabel { color: #1f2a24; background-color: transparent; } "
            "QWidget#backdropCentral QCheckBox { color: #1f2a24; background-color: transparent; spacing: 6px; } "
            "QWidget#backdropCentral QFrame { background-color: #fffdf8; color: #1f2a24; } "
            "QWidget#backdropCentral QPushButton { "
            "  background-color: #f7f3ea; color: #1f2a24; border: 1px solid #cfc5ad; "
            "  border-radius: 5px; padding: 5px 10px; "
            "} "
            "QWidget#backdropCentral QPushButton:hover { background-color: #efe9db; border-color: #b8ac92; } "
            "QWidget#backdropCentral QPushButton:pressed { background-color: #e6dfd0; } "
            "QWidget#backdropCentral QPushButton:disabled { "
            "  background-color: #f2eee3; color: #a3a99f; border-color: #e3dccb; "
            "} "
            "QWidget#backdropCentral QListWidget, "
            "QWidget#backdropCentral QComboBox, "
            "QWidget#backdropCentral QTextEdit, "
            "QWidget#backdropCentral QPlainTextEdit { "
            "  background-color: #f7f3ea; color: #1f2a24; border: 1px solid #cfc5ad; border-radius: 5px; "
            "} "
            "QWidget#backdropCentral QComboBox { padding: 4px 8px; } "
            "QWidget#backdropCentral QListWidget::item:selected { "
            "  background-color: #dcebe0; color: #1f2a24; "
            "} "
            "QWidget#backdropCentral QComboBox QAbstractItemView { "
            "  background-color: #fffdf8; color: #1f2a24; border: 1px solid #cfc5ad; "
            "  selection-background-color: #e4efe7; selection-color: #1f2a24; "
            "} "
            "QWidget#backdropCentral QProgressBar { "
            "  background-color: #f7f3ea; color: #1f2a24; border: 1px solid #cfc5ad; "
            "  border-radius: 4px; text-align: center; "
            "} "
            "QWidget#backdropCentral QProgressBar::chunk { background-color: #2f7a55; border-radius: 3px; } "
            "QWidget#backdropCentral QSplitter::handle { background-color: #e3dccb; } "
            "QWidget#backdropCentral QScrollBar:vertical { background: #f2eee3; width: 10px; margin: 0px; } "
            "QWidget#backdropCentral QScrollBar::handle:vertical { "
            "  background: #cfc5ad; border-radius: 5px; min-height: 24px; "
            "} "
            "QWidget#backdropCentral QScrollBar::add-line:vertical, "
            "QWidget#backdropCentral QScrollBar::sub-line:vertical { height: 0px; } "
        )
    return (
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


def status_color(plain: bool, tone: str) -> str:
    if plain:
        return {
            "neutral": "#1f2a24",
            "ok": "#2f7a55",
            "warn": "#b3741a",
            "info": "#2f5f8f",
            "error": "#b71c1c",
        }.get(tone, "#1f2a24")
    return {
        "neutral": "#dddddd",
        "ok": "#a5d6a7",
        "warn": "#ffcc80",
        "info": "#90caf9",
        "error": "#ef9a9a",
    }.get(tone, "#dddddd")


class _ThemePreviewBox(QWidget):
    "Rounded mini-preview banner for either Mozencaz' plain UI or Arararagi's Midna backdrop."

    def __init__(self, plain: bool, backdrop_path: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._plain = plain
        self._pixmap = QPixmap(backdrop_path) if (not plain and backdrop_path and os.path.isfile(backdrop_path)) else QPixmap()
        self.setFixedHeight(148)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 7.0, 7.0)
        painter.setClipPath(clip)

        w = rect.width()
        h = rect.height()

        if self._plain:
            painter.fillRect(rect, QColor("#f2eee3"))

            # Mini top bar
            painter.setPen(QPen(QColor("#e3dccb"), 1.0))
            painter.setBrush(QColor("#fffdf8"))
            painter.drawRoundedRect(QRectF(8, 8, w - 16, 18), 4, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f8eecf"))
            painter.drawRoundedRect(QRectF(13, 12, 62, 10), 3, 3)
            painter.setBrush(QColor("#cfc5ad"))
            painter.drawRoundedRect(QRectF(w - 50, 12, 36, 10), 3, 3)

            # Left and right parchment step cards
            mid_y = 32
            mid_h = h - 72
            left_w = (w - 24) * 0.44
            right_x = 16 + left_w
            right_w = w - right_x - 8

            painter.setPen(QPen(QColor("#e3dccb"), 1.0))
            painter.setBrush(QColor("#fffdf8"))
            painter.drawRoundedRect(QRectF(8, mid_y, left_w, mid_h), 5, 5)
            painter.drawRoundedRect(QRectF(right_x, mid_y, right_w, mid_h), 5, 5)

            # Mini badges & lines on cards
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e4efe7"))
            painter.drawRoundedRect(QRectF(14, mid_y + 7, 28, 9), 2.5, 2.5)
            painter.drawRoundedRect(QRectF(right_x + 6, mid_y + 7, 28, 9), 2.5, 2.5)

            painter.setBrush(QColor("#cfc5ad"))
            painter.drawRoundedRect(QRectF(14, mid_y + 23, left_w - 14, 7), 2.5, 2.5)
            painter.drawRoundedRect(QRectF(14, mid_y + 36, left_w - 22, 7), 2.5, 2.5)

            painter.setBrush(QColor("#e4efe7"))
            painter.drawRoundedRect(QRectF(right_x + 6, mid_y + 22, right_w - 12, 11), 3, 3)
            painter.setBrush(QColor("#e6eff7"))
            painter.drawRoundedRect(QRectF(right_x + 6, mid_y + 37, right_w - 12, 11), 3, 3)
            painter.setBrush(QColor("#f7f3ea"))
            painter.drawRoundedRect(QRectF(right_x + 6, mid_y + 52, right_w - 12, 11), 3, 3)

            # Bottom apply bar
            bot_y = h - 33
            painter.setPen(QPen(QColor("#e3dccb"), 1.0))
            painter.setBrush(QColor("#fffdf8"))
            painter.drawRoundedRect(QRectF(8, bot_y, w - 16, 25), 5, 5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#2f5f8f"))
            painter.drawRoundedRect(QRectF(14, bot_y + 6, (w - 34) * 0.62, 13), 3.5, 3.5)
            painter.setBrush(QColor("#2f7a55"))
            painter.drawRoundedRect(QRectF(18 + (w - 34) * 0.62, bot_y + 6, (w - 34) * 0.34, 13), 3.5, 3.5)

            painter.setClipping(False)
            painter.setPen(QPen(QColor("#cfc5ad"), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 7.0, 7.0)
        else:
            painter.fillRect(rect, QColor(16, 20, 26))
            if not self._pixmap.isNull():
                scaled = self._pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = (self.width() - scaled.width()) // 2
                y = (self.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
                # Gentle dark scrim so artwork stays vibrant while preview panels read cleanly
                painter.fillRect(rect, QColor(12, 16, 22, 68))

            # Subtle translucent mini-UI overlay mirroring Midna's Devotion layout
            painter.setPen(QPen(QColor(90, 105, 122, 130), 1.0))
            painter.setBrush(QColor(22, 26, 33, 128))
            painter.drawRoundedRect(QRectF(8, 8, w - 16, 17), 4, 4)

            mid_y = 30
            mid_h = h - 68
            left_w = (w - 24) * 0.43
            right_x = 16 + left_w
            right_w = w - right_x - 8

            painter.setBrush(QColor(22, 26, 33, 98))
            painter.drawRoundedRect(QRectF(8, mid_y, left_w, mid_h), 5, 5)
            painter.drawRoundedRect(QRectF(right_x, mid_y, right_w, mid_h), 5, 5)

            # Mini blue step badges + translucent active rows
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(21, 101, 192, 210))
            painter.drawRoundedRect(QRectF(14, mid_y + 6, 26, 8), 2.5, 2.5)
            painter.drawRoundedRect(QRectF(right_x + 6, mid_y + 6, 26, 8), 2.5, 2.5)

            painter.setBrush(QColor(16, 46, 41, 175))
            painter.drawRoundedRect(QRectF(right_x + 6, mid_y + 20, right_w - 12, 9), 2.5, 2.5)
            painter.setBrush(QColor(16, 41, 56, 175))
            painter.drawRoundedRect(QRectF(right_x + 6, mid_y + 33, right_w - 12, 9), 2.5, 2.5)
            painter.setBrush(QColor(18, 38, 22, 175))
            painter.drawRoundedRect(QRectF(right_x + 6, mid_y + 46, right_w - 12, 9), 2.5, 2.5)

            # Bottom translucent apply/play strip
            bot_y = h - 32
            painter.setPen(QPen(QColor(90, 105, 122, 130), 1.0))
            painter.setBrush(QColor(22, 26, 33, 135))
            painter.drawRoundedRect(QRectF(8, bot_y, w - 16, 24), 5, 5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(25, 118, 210, 210))
            painter.drawRoundedRect(QRectF(14, bot_y + 6, (w - 34) * 0.62, 12), 3.5, 3.5)
            painter.setBrush(QColor(46, 125, 50, 210))
            painter.drawRoundedRect(QRectF(18 + (w - 34) * 0.62, bot_y + 6, (w - 34) * 0.34, 12), 3.5, 3.5)

            painter.setClipping(False)
            painter.setPen(QPen(QColor("#35506b"), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 7.0, 7.0)


class UiExperienceDialog(QDialog):
    "First-launch and settings picker for Mozencaz' Default vs. Arararagi's UI."

    def __init__(
        self,
        current_theme: str = "",
        first_launch: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.selected_theme: Optional[str] = None

        self.setWindowTitle("Midna's Devotion — Choose UI Experience")
        self.setModal(True)
        self.setMinimumWidth(700)
        self.setStyleSheet(
            "QDialog { background-color: #f2eee3; color: #1f2a24; } "
            "QLabel { background-color: transparent; color: #1f2a24; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        heading = QLabel("Choose Your Midna's Devotion UI Experience")
        hf = QFont()
        hf.setPointSize(13)
        hf.setBold(True)
        heading.setFont(hf)
        root.addWidget(heading)

        intro_text = (
            "Welcome to Midna's Devotion! Pick how you want the mod manager to look. "
            "Both options have the exact same features — you can switch anytime with the UI Style button."
            if first_launch
            else "Switch how Midna's Devotion looks inside the app. Your choice is saved automatically."
        )
        intro = QLabel(intro_text)
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #5c665d; font-size: 12px;")
        root.addWidget(intro)

        backdrop_path = _find_backdrop_path()

        cards = QHBoxLayout()
        cards.setSpacing(14)

        # --- Card 1: Mozencaz' Default UI Experience ---
        moz_card = QFrame()
        moz_card.setObjectName("mozCard")
        moz_border = "#2f7a55" if current_theme == THEME_MOZENCAZ else "#cfc5ad"
        moz_card.setStyleSheet(
            f"QFrame#mozCard {{ background-color: #fffdf8; border: 2px solid {moz_border}; border-radius: 9px; }}"
        )
        moz_lay = QVBoxLayout(moz_card)
        moz_lay.setContentsMargins(14, 14, 14, 14)
        moz_lay.setSpacing(10)

        moz_lay.addWidget(_ThemePreviewBox(plain=True))

        moz_tag = QLabel("PLAIN · MATCHES RANDOMIZER")
        moz_tag.setStyleSheet(
            "background-color: #e4efe7; color: #2f7a55; font-weight: bold; font-size: 10px; "
            "padding: 3px 8px; border-radius: 4px;"
        )
        moz_tag.setFixedHeight(22)
        moz_lay.addWidget(moz_tag, 0, Qt.AlignmentFlag.AlignLeft)

        moz_title = QLabel("Mozencaz' Default UI Experience")
        mtf = QFont()
        mtf.setPointSize(11)
        mtf.setBold(True)
        moz_title.setFont(mtf)
        moz_title.setStyleSheet("color: #1f2a24;")
        moz_title.setWordWrap(True)
        moz_lay.addWidget(moz_title)

        moz_desc = QLabel(
            "Strips away background art and custom dark effects to match the clean, plain parchment "
            "layout of the rest of the OoT Randomizer app."
        )
        moz_desc.setWordWrap(True)
        moz_desc.setStyleSheet("color: #5c665d; font-size: 11px;")
        moz_lay.addWidget(moz_desc, 1)

        moz_btn = QPushButton("Use Mozencaz' Default UI")
        moz_btn.setMinimumHeight(36)
        moz_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        moz_btn.setStyleSheet(
            "QPushButton { background-color: #2f7a55; color: #ffffff; font-weight: bold; "
            "border: 1px solid #246042; border-radius: 5px; padding: 6px 12px; } "
            "QPushButton:hover { background-color: #266948; }"
        )
        moz_btn.clicked.connect(lambda: self._choose(THEME_MOZENCAZ))
        moz_lay.addWidget(moz_btn)

        # --- Card 2: Arararagi's UI Experience ---
        ara_card = QFrame()
        ara_card.setObjectName("araCard")
        ara_border = "#64b5f6" if current_theme == THEME_ARARAGI else "#354659"
        ara_card.setStyleSheet(
            f"QFrame#araCard {{ background-color: #161d26; border: 2px solid {ara_border}; border-radius: 9px; }}"
        )
        ara_lay = QVBoxLayout(ara_card)
        ara_lay.setContentsMargins(14, 14, 14, 14)
        ara_lay.setSpacing(10)

        ara_lay.addWidget(_ThemePreviewBox(plain=False, backdrop_path=backdrop_path))

        ara_tag = QLabel("CUSTOM · MIDNA BACKDROP")
        ara_tag.setStyleSheet(
            "background-color: #1565c0; color: #ffffff; font-weight: bold; font-size: 10px; "
            "padding: 3px 8px; border-radius: 4px;"
        )
        ara_tag.setFixedHeight(22)
        ara_lay.addWidget(ara_tag, 0, Qt.AlignmentFlag.AlignLeft)

        ara_title = QLabel("Arararagi's UI Experience")
        atf = QFont()
        atf.setPointSize(11)
        atf.setBold(True)
        ara_title.setFont(atf)
        ara_title.setStyleSheet("color: #f5f7fa;")
        ara_title.setWordWrap(True)
        ara_lay.addWidget(ara_title)

        ara_desc = QLabel(
            "Keeps the full Midna's Devotion presentation intact with the custom artwork backdrop, "
            "dark translucent panels, and vibrant color accents."
        )
        ara_desc.setWordWrap(True)
        ara_desc.setStyleSheet("color: #b0bec5; font-size: 11px;")
        ara_lay.addWidget(ara_desc, 1)

        ara_btn = QPushButton("Use Arararagi's UI Experience")
        ara_btn.setMinimumHeight(36)
        ara_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ara_btn.setStyleSheet(
            "QPushButton { background-color: #1976d2; color: #ffffff; font-weight: bold; "
            "border: 1px solid #42a5f5; border-radius: 5px; padding: 6px 12px; } "
            "QPushButton:hover { background-color: #1e88e5; }"
        )
        ara_btn.clicked.connect(lambda: self._choose(THEME_ARARAGI))
        ara_lay.addWidget(ara_btn)

        cards.addWidget(moz_card, 1)
        cards.addWidget(ara_card, 1)
        root.addLayout(cards)

        if not first_launch:
            cancel_row = QHBoxLayout()
            cancel_row.addStretch(1)
            cancel_btn = QPushButton("Cancel")
            cancel_btn.setStyleSheet(
                "QPushButton { background-color: #f7f3ea; color: #1f2a24; border: 1px solid #cfc5ad; "
                "border-radius: 5px; padding: 5px 14px; } "
                "QPushButton:hover { background-color: #efe9db; }"
            )
            cancel_btn.clicked.connect(self.reject)
            cancel_row.addWidget(cancel_btn)
            root.addLayout(cancel_row)

    def _choose(self, theme_id: str) -> None:
        self.selected_theme = theme_id
        self.accept()
