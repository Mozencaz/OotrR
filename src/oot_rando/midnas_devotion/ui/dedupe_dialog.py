"""Interactive duplicate-mod resolution prompt for Midna's Devotion."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from PySide6.QtWidgets import QMessageBox

from oot_rando.midnas_devotion.core.dedupe import DuplicateMatch, format_duplicate_summary


def prompt_duplicate_resolution(
    parent,
    candidate_name: str,
    matches: Sequence[DuplicateMatch],
    *,
    allow_replace: bool = True,
    allow_keep_both: bool = True,
    sandbox_mode: bool = True,
) -> Tuple[str, Optional[DuplicateMatch]]:
    """Ask how to handle detected duplicate/similar mods.

    Returns ("replace", top_match), ("keep", None), or ("cancel", None).
    """
    if not matches:
        return ("keep", None)

    top = matches[0]
    summary = format_duplicate_summary(matches)

    if top.kind == "EXACT_CONTENT":
        title = "Exact Duplicate Mod Detected"
        intro = (
            f"Mod {candidate_name!r} has the exact same file contents (CRC32 & SHA-256) "
            "as a mod you already have:"
        )
    elif top.kind == "HIGH_OVERLAP":
        title = "Possible Updated Version / Variant Detected"
        intro = (
            f"Mod {candidate_name!r} shares most of its romfs/ files with an existing mod "
            "(it looks like an update or variant):"
        )
    else:
        title = "Similar Mod Name Detected"
        intro = f"Mod {candidate_name!r} has a very similar name to an existing mod:"

    can_replace = bool(allow_replace)
    note = ""
    if can_replace and top.existing_origin == "live" and sandbox_mode:
        can_replace = False
        note = (
            "\n\nNote: Test Mode is active, so replacing a mod inside your Live Mods folder "
            "is blocked to keep Live untouched."
        )

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(f"{intro}\n\n{summary}{note}\n\nHow would you like to proceed?")

    replace_btn = (
        box.addButton(f"Replace / Update {top.existing_name}", QMessageBox.ButtonRole.AcceptRole)
        if can_replace
        else None
    )
    keep_btn = (
        box.addButton("Keep Both", QMessageBox.ButtonRole.ActionRole)
        if allow_keep_both
        else None
    )
    cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_btn if top.kind == "EXACT_CONTENT" else (replace_btn or cancel_btn))
    box.exec()

    clicked = box.clickedButton()
    if replace_btn is not None and clicked == replace_btn:
        return ("replace", top)
    if keep_btn is not None and clicked == keep_btn:
        return ("keep", None)
    return ("cancel", None)
