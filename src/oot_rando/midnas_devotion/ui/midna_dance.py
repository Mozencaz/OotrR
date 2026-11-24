"""Animated Imp Midna dancing sprite widget displayed during mod-build operations.

Loads an optional bundled GIF or 2x2 green-screen sprite sheet (performing BFS
chroma-key removal and frame centering), falling back to a procedural 24x24
pixel-art animation if assets are absent.
"""
from __future__ import annotations

import os
from collections import deque
from typing import List, Optional, Tuple

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QMovie, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from oot_rando.midnas_devotion.launcher import resolve_asset

_PALETTE = {
    "K": QColor(18, 22, 30, 255),
    "D": QColor(32, 40, 52, 255),
    "T": QColor(48, 62, 78, 255),
    "W": QColor(220, 232, 240, 255),
    "S": QColor(112, 120, 134, 255),
    "L": QColor(162, 172, 186, 255),
    "G": QColor(72, 78, 92, 255),
    "C": QColor(56, 236, 255, 255),
    "B": QColor(0, 164, 204, 255),
    "O": QColor(255, 122, 36, 255),
    "Y": QColor(255, 178, 72, 255),
    "R": QColor(196, 72, 18, 255),
    "E": QColor(255, 58, 58, 255),
    "P": QColor(255, 244, 196, 255),
    "H": QColor(0, 0, 0, 85),
}


def _render_fallback_frame(step: int) -> QImage:
    """Render one frame of the procedural 8-step 24x24 pixel-art Midna fallback animation."""
    w, h = 24, 24
    grid = [[None for _ in range(w)] for _ in range(h)]

    def put(x: int, y: int, key: str) -> None:
        if 0 <= x < w and 0 <= y < h:
            grid[y][x] = key

    def draw_rows(ox: int, oy: int, rows: Tuple[str, ...]) -> None:
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch != ".":
                    put(ox + rx, oy + ry, ch)

    bounces = (0, -1, -2, -1, 0, -1, -2, -1)
    sways = (-1, 0, 1, 1, 1, 0, -1, -1)
    dy = bounces[step % 8]
    dx = sways[step % 8]
    pose_alt = (step // 2) % 2 == 1
    happy_wink = step in (2, 6)

    for sx in (range(9 + dx, 15 + dx) if dy == -2 else range(8 + dx, 16 + dx)):
        put(sx, 22, "H")

    if step in (0, 1, 7):
        draw_rows(11 + dx, 1 + dy, ("..YYY...", ".YOOOY..", "..ROO...", "...OO..."))
    elif step in (2, 3):
        draw_rows(12 + dx, 1 + dy, ("...YYY..", "..YOOOY.", "..OOOR..", "..OO...."))
    elif step in (4, 5):
        draw_rows(8 + dx, 1 + dy, ("..YYY...", ".YOOOY..", "..ROO...", "...OO..."))
    else:
        draw_rows(7 + dx, 1 + dy, (".YYY....", "YOOOY...", ".ROOO...", "...OO..."))

    draw_rows(
        7 + dx,
        4 + dy,
        ("....LL....", "...LSSL...", "..LSSSSG..", ".LSCBSSSG.", ".GSCBGGSG.", ".GGSSGGGK."),
    )
    draw_rows(
        6 + dx,
        10 + dy,
        ("KW.GWWWWWWK", ".K.GWWKPKWK", "...KWWKKWK.")
        if happy_wink
        else ("KW.GWWWEPWK", ".K.GWWWEWWK", "...KWWKKWK."),
    )
    draw_rows(7 + dx, 13 + dy, ("..KDDDK..", ".KDCTCDK.", ".KDTWTDK.", ".KWDDDWK.", "..KDDDK.."))

    if not pose_alt:
        put(6 + dx, 12 + dy, "W"); put(7 + dx, 13 + dy, "D"); put(6 + dx, 11 + dy, "C")
        put(16 + dx, 15 + dy, "D"); put(17 + dx, 16 + dy, "W")
        put(9 + dx, 18 + dy, "D"); put(8 + dx, 19 + dy, "W")
        put(13 + dx, 18 + dy, "D"); put(14 + dx, 19 + dy, "D")
    else:
        put(17 + dx, 12 + dy, "W"); put(16 + dx, 13 + dy, "D"); put(17 + dx, 11 + dy, "C")
        put(7 + dx, 15 + dy, "D"); put(6 + dx, 16 + dy, "W")
        put(9 + dx, 18 + dy, "D"); put(8 + dx, 19 + dy, "D")
        put(13 + dx, 18 + dy, "D"); put(15 + dx, 19 + dy, "W")

    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    for y in range(h):
        for x in range(w):
            ch = grid[y][x]
            if ch is not None:
                img.setPixelColor(x, y, _PALETTE[ch])
    return img


def _is_chroma_green(r: int, g: int, b: int) -> bool:
    """Return True for chroma-key green background pixels."""
    return g >= 115 and (g - r) >= 38 and (g - b) >= 48


def _strip_green_cell(cell: QImage, strip_br_watermark: bool = False) -> Tuple[QImage, Tuple[int, int, int, int]]:
    """Flood-fill strip chroma green from one sprite-sheet cell and return ``(cleaned_image, tight_bbox)``."""
    img = cell.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return img, (0, 0, max(1, w), max(1, h))
    bpl = img.bytesPerLine()
    raw = bytearray(img.constBits())

    if strip_br_watermark:
        wm_x0 = int(w * 0.88)
        wm_y0 = int(h * 0.88)
        for y in range(wm_y0, h):
            row_off = y * bpl
            for x in range(wm_x0, w):
                idx = row_off + x * 4
                raw[idx] = 0
                raw[idx + 1] = 255
                raw[idx + 2] = 0
                raw[idx + 3] = 255

    visited = bytearray(w * h)
    bg_mask = bytearray(w * h)
    q: deque[Tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        pos = y * w + x
        if visited[pos]:
            return
        idx = y * bpl + x * 4
        if _is_chroma_green(raw[idx], raw[idx + 1], raw[idx + 2]):
            visited[pos] = 1
            bg_mask[pos] = 1
            q.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while q:
        cx, cy = q.popleft()
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                pos = ny * w + nx
                if not visited[pos]:
                    idx = ny * bpl + nx * 4
                    if _is_chroma_green(raw[idx], raw[idx + 1], raw[idx + 2]):
                        visited[pos] = 1
                        bg_mask[pos] = 1
                        q.append((nx, ny))

    for y in range(h):
        row_off = y * bpl
        row_p = y * w
        for x in range(w):
            if not bg_mask[row_p + x]:
                idx = row_off + x * 4
                r, g, b = raw[idx], raw[idx + 1], raw[idx + 2]
                if g >= 165 and (g - r) >= 65 and (g - b) >= 75:
                    bg_mask[row_p + x] = 1

    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        row_off = y * bpl
        row_p = y * w
        for x in range(w):
            pos = row_p + x
            idx = row_off + x * 4
            if bg_mask[pos]:
                raw[idx + 3] = 0
                continue
            touches_bg = (
                (x > 0 and bg_mask[pos - 1])
                or (x + 1 < w and bg_mask[pos + 1])
                or (y > 0 and bg_mask[pos - w])
                or (y + 1 < h and bg_mask[pos + w])
            )
            if touches_bg:
                r, g, b = raw[idx], raw[idx + 1], raw[idx + 2]
                if g > r + 18 and g > b + 24:
                    if g - max(r, b) >= 42:
                        raw[idx + 3] = 0
                        continue
                    raw[idx + 1] = max(r, b)
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y

    out = QImage(bytes(raw), w, h, bpl, QImage.Format.Format_RGBA8888).copy()
    if max_x < min_x or max_y < min_y:
        return out, (0, 0, w, h)
    return out, (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def _load_2x2_sprite_sheet(path: str) -> List[QImage]:
    """Split a 2x2 green-screen sprite sheet into 4 chroma-keyed, bottom-aligned square frames."""
    src = QImage(path)
    if src.isNull() or src.width() < 64 or src.height() < 64:
        return []

    if src.width() > 512 or src.height() > 512:
        src = src.scaled(
            512,
            512,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

    cw = src.width() // 2
    ch = src.height() // 2
    coords = ((0, 0, False), (cw, 0, False), (0, ch, False), (cw, ch, True))

    cropped: List[QImage] = []
    max_w = 1
    max_h = 1
    for ox, oy, is_br in coords:
        cell = src.copy(ox, oy, cw, ch)
        cleaned, (bx, by, bw, bh) = _strip_green_cell(cell, strip_br_watermark=is_br)
        sub = cleaned.copy(bx, by, bw, bh)
        cropped.append(sub)
        max_w = max(max_w, bw)
        max_h = max(max_h, bh)

    side = max(max_w, max_h) + 8
    aligned: List[QImage] = []
    for sub in cropped:
        canvas = QImage(side, side, QImage.Format.Format_RGBA8888)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        dx = (side - sub.width()) // 2
        dy = side - sub.height() - 4
        painter.drawImage(dx, dy, sub)
        painter.end()
        aligned.append(canvas)
    return aligned


class MidnaDanceWidget(QLabel):
    """Animated pixel-art dancing Imp Midna indicator shown during mod merging."""

    def __init__(self, size: int = 280, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._display_size = size
        self._raw_frames: List[QImage] = []
        self._frames: List[QPixmap] = []
        self._movie: Optional[QMovie] = None
        self._frame_idx = 0
        self._running = False

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: transparent; border: none;")
        self.setToolTip("Midna is weaving your mods together…")
        self.setFixedSize(size, size)

        self._timer = QTimer(self)
        self._timer.setInterval(175)
        self._timer.timeout.connect(self._advance)

        self._load_media()

    def _load_media(self) -> None:
        gif_path = resolve_asset("midna_dance.gif")
        if gif_path and os.path.isfile(gif_path):
            movie = QMovie(gif_path, parent=self)
            if movie.isValid():
                movie.setScaledSize(QSize(self._display_size, self._display_size))
                self._movie = movie
                self.setMovie(movie)
                return

        for name in (
            "midna_dance_sheet.png",
            "midna_dance_sheet.jpg",
            "midna_dance_sheet.jpeg",
            "midna_dance_sheet.webp",
            "midna_dance.png",
        ):
            sheet_path = resolve_asset(name)
            if sheet_path and os.path.isfile(sheet_path):
                frames = _load_2x2_sprite_sheet(sheet_path)
                if frames:
                    self._raw_frames = frames
                    self._timer.setInterval(175)
                    self._rebuild_frames()
                    return

        self._raw_frames = [_render_fallback_frame(i) for i in range(8)]
        self._timer.setInterval(135)
        self._rebuild_frames()

    def _rebuild_frames(self) -> None:
        sz = self._display_size
        self._frames = [
            QPixmap.fromImage(img).scaled(
                sz,
                sz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            for img in self._raw_frames
        ]
        if self._frames:
            self.setPixmap(self._frames[self._frame_idx % len(self._frames)])

    def set_display_size(self, size: int) -> None:
        """Resize the animation widget and rescale cached frames cleanly."""
        size = max(16, int(size))
        if size == self._display_size:
            return
        self._display_size = size
        self.setFixedSize(size, size)
        if self._movie is not None:
            self._movie.setScaledSize(QSize(size, size))
        else:
            self._rebuild_frames()

    def start(self) -> None:
        """Begin animating (or mark running so animation starts once visible)."""
        self._running = True
        self._frame_idx = 0
        self.setVisible(True)
        if self._movie is not None:
            self._movie.start()
        else:
            if self._frames:
                self.setPixmap(self._frames[0])
            self._timer.start()

    def stop(self) -> None:
        """Stop frame playback and timer ticks."""
        self._running = False
        if self._movie is not None:
            self._movie.stop()
        self._timer.stop()

    def hideEvent(self, event) -> None:
        """Pause timer/movie playback while hidden (e.g. when another randomizer tab is active)."""
        if self._movie is not None:
            self._movie.setPaused(True)
        if self._timer.isActive():
            self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        """Resume playback when returning to the tab if a build animation is still running."""
        super().showEvent(event)
        if self._running:
            if self._movie is not None:
                self._movie.setPaused(False)
            elif not self._timer.isActive():
                self._timer.start()

    def _advance(self) -> None:
        """Step to the next cached sprite frame."""
        if not self._frames or not self.isVisible():
            return
        self._frame_idx = (self._frame_idx + 1) % len(self._frames)
        self.setPixmap(self._frames[self._frame_idx])
