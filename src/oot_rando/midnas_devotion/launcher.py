"""Entry point for Midna's Devotion mod manager inside oot_rando."""
from __future__ import annotations

import sys
from pathlib import Path


def resolve_asset(rel_name: str) -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = []
    if meipass:
        candidates.append(Path(meipass) / "oot_rando" / "midnas_devotion" / "assets" / rel_name)
        candidates.append(Path(meipass) / "midnas_devotion" / "assets" / rel_name)
    candidates.append(Path(__file__).resolve().parent / "assets" / rel_name)
    for c in candidates:
        if c.is_file():
            return str(c)
    return str(candidates[-1])


def main(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is required to launch Midna's Devotion (install PySide6 or use the prebuilt release)."
        ) from exc
    from oot_rando.midnas_devotion.core.config import AppConfig
    from oot_rando.midnas_devotion.ui.main_window import MainWindow

    args = list(sys.argv[:1] if argv is None else [sys.argv[0], *argv])
    app = QApplication.instance() or QApplication(args)
    app.setApplicationName(
        "Midna's Devotion — Ocarina of Time Mod Manager & Merger (for Longshot + Mozencaz's Randomizer)"
    )
    cfg = AppConfig()
    win = MainWindow(cfg)
    win.show()
    return int(app.exec())
