"""Embed Midna's Devotion (PySide6 MainWindow) inside a Tkinter container frame."""
from __future__ import annotations

import os
import sys
import tkinter as tk
from typing import Callable, Optional


class EmbeddedMidnaHost:
    """Hosts the full PySide6 MainWindow natively inside a Tkinter frame."""

    def __init__(
        self,
        tk_root: tk.Misc,
        container: tk.Frame,
        on_fallback_window: Optional[Callable[[], None]] = None,
    ) -> None:
        self._tk_root = tk_root
        self._container = container
        self._on_fallback = on_fallback_window

        self._qapp = None
        self._parent_qwindow = None
        self._window = None
        self._mounted = False
        self._visible = False
        self._destroyed = False
        self._pump_after_id: Optional[str] = None
        self._resize_after_id: Optional[str] = None
        self._error_frame: Optional[tk.Frame] = None

        self._container.bind("<Configure>", self._on_container_configure, add="+")
        self._container.bind("<Map>", self._on_container_map, add="+")

    @property
    def is_mounted(self) -> bool:
        return self._mounted and self._window is not None

    def is_busy(self) -> bool:
        if self._window is None:
            return False
        worker = getattr(self._window, "worker", None)
        return bool(worker and worker.isRunning())

    def ensure_mounted(self) -> bool:
        if self._destroyed:
            return False
        if self._mounted and self._window is not None:
            return True

        try:
            self._mount_qt_window()
            self._mounted = True
            self._start_pump()
            return True
        except Exception as exc:
            self._show_error_fallback(exc)
            return False

    def _mount_qt_window(self) -> None:
        # Tkinter on Linux uses X11 (or XWayland), so Qt must use xcb to
        # reparent natively into container.winfo_id().
        if sys.platform.startswith("linux"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QWindow
        from PySide6.QtWidgets import QApplication
        from oot_rando.midnas_devotion.core.config import AppConfig
        from oot_rando.midnas_devotion.ui.main_window import MainWindow

        app = QApplication.instance()
        if app is None:
            app = QApplication([sys.argv[0]])
            app.setQuitOnLastWindowClosed(False)
            app.setApplicationName(
                "Midna's Devotion — Ocarina of Time Mod Manager & Merger (for Longshot + Mozencaz's Randomizer)"
            )
        self._qapp = app

        self._container.update_idletasks()
        host_wid = int(self._container.winfo_id())
        if not host_wid:
            raise RuntimeError("Tkinter host container does not have a valid native window ID.")

        parent_qwin = QWindow.fromWinId(host_wid)
        if parent_qwin is None:
            raise RuntimeError(f"QWindow.fromWinId({host_wid}) returned None.")
        self._parent_qwindow = parent_qwin

        cfg = AppConfig()
        win = MainWindow(cfg)
        win.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        win.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        win.setMinimumSize(0, 0)
        win.winId()

        handle = win.windowHandle()
        if handle is None:
            win.deleteLater()
            raise RuntimeError("Could not obtain native QWindow handle for MainWindow.")

        from oot_rando.midnas_devotion.ui.ui_theme import container_bg_for_theme

        def _sync_container_bg(theme_id: str) -> None:
            try:
                self._container.configure(background=container_bg_for_theme(theme_id))
            except Exception:
                pass

        win.set_theme_change_callback(_sync_container_bg)
        _sync_container_bg(cfg.effective_ui_theme)

        handle.setParent(parent_qwin)
        self._window = win
        self._sync_geometry()

    def show(self) -> None:
        if self._destroyed:
            return
        self._visible = True
        if not self.ensure_mounted():
            return
        if self._window is not None:
            self._container.update_idletasks()
            self._window.show()
            self._sync_geometry()
            self._window.raise_()
            self._schedule_resize_sync()
            if self._qapp is not None:
                self._qapp.processEvents()

    def hide(self) -> None:
        self._visible = False
        if self._window is not None:
            try:
                self._window.hide()
                if self._qapp is not None:
                    self._qapp.processEvents()
            except Exception:
                pass

    def _on_container_configure(self, _event=None) -> None:
        if self._visible and self._window is not None:
            self._sync_geometry()

    def _on_container_map(self, _event=None) -> None:
        if self._visible and self._window is not None:
            self._schedule_resize_sync()

    def _schedule_resize_sync(self) -> None:
        if self._destroyed:
            return
        if self._resize_after_id is not None:
            try:
                self._tk_root.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self._tk_root.after(30, self._delayed_sync)

    def _delayed_sync(self) -> None:
        self._resize_after_id = None
        if not self._destroyed and self._visible and self._window is not None:
            self._sync_geometry()

    def _sync_geometry(self) -> None:
        if self._window is None or self._destroyed:
            return
        try:
            self._container.update_idletasks()
            w = self._container.winfo_width()
            h = self._container.winfo_height()
            if w <= 1 or h <= 1:
                return
            handle = self._window.windowHandle()
            dpr = float(handle.devicePixelRatio()) if handle is not None else 1.0
            if dpr <= 0.0:
                dpr = 1.0
            lw = max(1, int(round(w / dpr)))
            lh = max(1, int(round(h / dpr)))
            self._window.setGeometry(0, 0, lw, lh)
        except Exception:
            pass

    def _start_pump(self) -> None:
        if self._pump_after_id is None and not self._destroyed:
            self._pump_after_id = self._tk_root.after(16, self._pump_qt_events)

    def _pump_qt_events(self) -> None:
        self._pump_after_id = None
        if self._destroyed:
            return
        try:
            if self._qapp is not None:
                self._qapp.processEvents()
        except Exception:
            pass
        delay_ms = 16 if (self._visible or self.is_busy()) else 120
        try:
            self._pump_after_id = self._tk_root.after(delay_ms, self._pump_qt_events)
        except Exception:
            self._pump_after_id = None

    def _show_error_fallback(self, exc: Exception) -> None:
        if self._error_frame is not None:
            return
        from tkinter import ttk

        frame = ttk.Frame(self._container, style="Page.TFrame", padding=24)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        ttk.Label(
            frame,
            text="Could not embed Midna's Devotion directly into this tab.",
            style="Heading.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(
            frame,
            text=str(exc),
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(0, 14))
        if self._on_fallback is not None:
            ttk.Button(
                frame,
                text="Open Midna's Devotion in Separate Window",
                style="Accent.TButton",
                command=self._on_fallback,
            ).pack(anchor="w")
        self._error_frame = frame

    def destroy(self) -> None:
        self._destroyed = True
        self._visible = False
        if self._pump_after_id is not None:
            try:
                self._tk_root.after_cancel(self._pump_after_id)
            except Exception:
                pass
            self._pump_after_id = None
        if self._resize_after_id is not None:
            try:
                self._tk_root.after_cancel(self._resize_after_id)
            except Exception:
                pass
            self._resize_after_id = None
        if self._window is not None:
            try:
                handle = self._window.windowHandle()
                self._window.hide()
                if handle is not None:
                    handle.setParent(None)
                self._window.close()
                self._window.deleteLater()
            except Exception:
                pass
            self._window = None
        self._parent_qwindow = None
        if self._qapp is not None:
            try:
                self._qapp.processEvents()
            except Exception:
                pass
