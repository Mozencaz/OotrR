"""Embed Midna's Devotion (PySide6 ``MainWindow``) inside a Tkinter container frame.

Handles cross-toolkit window reparenting (X11 ``xcb`` on Linux, non-DPI-mutating
embedding on Windows), HiDPI logical geometry translation, cooperative Qt event
pumping on Tk's ``after`` loop, and deterministic teardown.
"""
from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from typing import Callable, Optional

_LOG = logging.getLogger(__name__)


class EmbeddedMidnaHost:
    """Hosts the full PySide6 ``MainWindow`` natively inside a Tkinter container frame."""

    def __init__(
        self,
        tk_root: tk.Misc,
        container: tk.Frame,
        on_fallback_window: Optional[Callable[[], None]] = None,
        on_theme_changed: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize host state and bind container resize/map events (mount is deferred)."""
        self._tk_root = tk_root
        self._container = container
        self._on_fallback = on_fallback_window
        self._on_theme_changed = on_theme_changed

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
        """Return True once the embedded Qt window has been created and attached."""
        return self._mounted and self._window is not None

    def is_busy(self) -> bool:
        """Return True while an active Midna background worker thread is running."""
        if self._window is None:
            return False
        worker = getattr(self._window, "worker", None)
        return bool(worker and worker.isRunning())

    def sync_from_randomizer(self, mods_dir: Optional[str] = None, *, refresh_always: bool = False) -> None:
        """Push the randomizer's active mods directory into Midna's config and refresh UI if needed."""
        if self._window is None or self._destroyed:
            return
        try:
            changed = self._window.cfg.sync_from_randomizer(mods_dir, persist=True)
            if changed or refresh_always:
                self._window.refresh_all()
        except Exception:
            _LOG.debug("Failed to sync Midna embedded host from randomizer", exc_info=True)

    def ensure_mounted(self) -> bool:
        """Lazily mount the Qt ``MainWindow`` and start the Tk->Qt event pump."""
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
            _LOG.warning("Failed to embed Midna's Devotion window: %s", exc, exc_info=True)
            self._show_error_fallback(exc)
            return False

    def _mount_qt_window(self) -> None:
        """Create or reuse ``QApplication`` and reparent ``MainWindow`` into Tk's native HWND/XID."""
        # Tkinter on Linux uses X11 (or XWayland), so Qt must use xcb to
        # reparent natively into container.winfo_id().
        # On Windows, prevent Qt from flipping process DPI awareness mid-run,
        # which otherwise shrinks the already-created Tkinter window and breaks maximize.
        qt_argv = [sys.argv[0]]
        if sys.platform.startswith("linux"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"
        elif sys.platform == "win32":
            os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
            qt_argv.extend(["-platform", "windows:dpiawareness=0"])

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QWindow
        from PySide6.QtWidgets import QApplication
        from oot_rando.midnas_devotion.core.config import AppConfig
        from oot_rando.midnas_devotion.ui.main_window import MainWindow

        app = QApplication.instance()
        if app is None:
            app = QApplication(qt_argv)
            app.setStyle("Fusion")
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
        # Force native window handle creation before calling windowHandle().setParent().
        win.winId()

        handle = win.windowHandle()
        if handle is None:
            win.deleteLater()
            raise RuntimeError("Could not obtain native QWindow handle for MainWindow.")

        from oot_rando.midnas_devotion.ui.ui_theme import container_bg_for_theme

        def _on_qt_theme_changed(theme_id: str) -> None:
            if self._destroyed:
                return
            try:
                self._container.configure(background=container_bg_for_theme(theme_id))
            except Exception:
                _LOG.debug("Failed to update Tk container background for theme %r", theme_id, exc_info=True)
            if self._on_theme_changed is not None:
                try:
                    self._on_theme_changed(theme_id)
                except Exception:
                    _LOG.debug("Theme change callback failed for theme %r", theme_id, exc_info=True)

        win.set_theme_change_callback(_on_qt_theme_changed)
        _on_qt_theme_changed(cfg.effective_ui_theme)

        handle.setParent(parent_qwin)
        self._window = win
        self._sync_geometry()

    def show(self) -> None:
        """Display the embedded Qt window and align its geometry to the Tk host frame."""
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
        """Hide the embedded Qt window when switching away to another Tkinter tab."""
        self._visible = False
        if self._window is not None:
            try:
                self._window.hide()
                if self._qapp is not None:
                    self._qapp.processEvents()
            except Exception:
                _LOG.debug("Failed to hide embedded Midna window", exc_info=True)

    def _on_container_configure(self, _event=None) -> None:
        """Keep Qt window dimensions synced as the Tk container resizes."""
        if not self._destroyed and self._visible and self._window is not None:
            self._sync_geometry()

    def _on_container_map(self, _event=None) -> None:
        """Schedule a deferred geometry sync once the Tk container maps onto screen."""
        if not self._destroyed and self._visible and self._window is not None:
            self._schedule_resize_sync()

    def _schedule_resize_sync(self) -> None:
        """Debounce a 30 ms follow-up geometry sync to catch late window-manager sizing."""
        if self._destroyed:
            return
        if self._resize_after_id is not None:
            try:
                self._tk_root.after_cancel(self._resize_after_id)
            except Exception:
                _LOG.debug("Failed to cancel pending resize sync timer", exc_info=True)
        self._resize_after_id = self._tk_root.after(30, self._delayed_sync)

    def _delayed_sync(self) -> None:
        """Execute the debounced geometry sync callback."""
        self._resize_after_id = None
        if not self._destroyed and self._visible and self._window is not None:
            self._sync_geometry()

    def _sync_geometry(self) -> None:
        """Translate Tk physical pixel bounds to Qt logical pixels and resize ``MainWindow``."""
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
            # Tk reports physical pixels on X11 while QWidget.setGeometry expects logical units.
            lw = max(1, int(round(w / dpr)))
            lh = max(1, int(round(h / dpr)))
            self._window.setGeometry(0, 0, lw, lh)
        except Exception:
            _LOG.debug("Failed to sync embedded Midna geometry", exc_info=True)

    def _start_pump(self) -> None:
        """Kick off the periodic Tk ``after`` loop that drives Qt's event queue."""
        if self._pump_after_id is None and not self._destroyed:
            self._pump_after_id = self._tk_root.after(16, self._pump_qt_events)

    def _pump_qt_events(self) -> None:
        """Process pending Qt events at ~60 Hz while visible/busy, or ~8 Hz while hidden."""
        self._pump_after_id = None
        if self._destroyed:
            return
        try:
            if self._qapp is not None:
                self._qapp.processEvents()
        except Exception:
            _LOG.debug("Qt event pump raised an exception", exc_info=True)
        delay_ms = 16 if (self._visible or self.is_busy()) else 120
        try:
            self._pump_after_id = self._tk_root.after(delay_ms, self._pump_qt_events)
        except Exception:
            _LOG.debug("Could not reschedule Qt event pump (Tk root likely closing)", exc_info=True)
            self._pump_after_id = None

    def _show_error_fallback(self, exc: Exception) -> None:
        """Render an in-tab recovery panel with a separate-window launch button on mount failure."""
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
        """Cancel timers, detach the native Qt handle from Tk, and schedule widget cleanup."""
        self._destroyed = True
        self._visible = False
        if self._pump_after_id is not None:
            try:
                self._tk_root.after_cancel(self._pump_after_id)
            except Exception:
                _LOG.debug("Failed to cancel Qt pump timer during destroy", exc_info=True)
            self._pump_after_id = None
        if self._resize_after_id is not None:
            try:
                self._tk_root.after_cancel(self._resize_after_id)
            except Exception:
                _LOG.debug("Failed to cancel resize sync timer during destroy", exc_info=True)
            self._resize_after_id = None
        if self._window is not None:
            try:
                handle = self._window.windowHandle()
                self._window.hide()
                # Detach before Tk destroys the host frame so Qt does not touch a freed XID/HWND.
                if handle is not None:
                    handle.setParent(None)
                self._window.close()
                self._window.deleteLater()
            except Exception:
                _LOG.debug("Failed to tear down embedded Midna window cleanly", exc_info=True)
            self._window = None
        self._parent_qwindow = None
        if self._qapp is not None:
            try:
                self._qapp.processEvents()
            except Exception:
                _LOG.debug("Final Qt processEvents failed during destroy", exc_info=True)
