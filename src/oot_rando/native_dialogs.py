"Cross-platform native OS file and folder pickers for Linux, Windows, and macOS."
from __future__ import annotations

import os
import posixpath
import re
import shutil
import subprocess
import sys
from typing import List, Optional, Sequence, Tuple


FilterSpec = Tuple[str, List[str]]


def _is_bundled_path(entry: str, appdir: str, meipass: str) -> bool:
    """Return True when a search-path entry points inside an AppImage or PyInstaller bundle."""
    if not entry:
        return False
    norm = os.path.normpath(entry)
    if appdir and (norm == appdir or norm.startswith(appdir + os.sep)):
        return True
    if meipass and (norm == meipass or norm.startswith(meipass + os.sep)):
        return True
    return any(tok in norm for tok in ("PySide6", "_MEI", "/.mount_"))


def clean_native_env() -> dict[str, str]:
    """Strip AppImage, PyInstaller, and embedded-Qt overrides before spawning host tools.

    Embedded Qt-in-Tk forces ``QT_QPA_PLATFORM=xcb`` (Linux) and
    ``QT_ENABLE_HIGHDPI_SCALING=0`` (Windows) in-process; stripping those here
    keeps external host pickers (kdialog/zenity) and ``xdg-open`` on the desktop
    session defaults instead of inheriting bundled libraries or X11 overrides.
    """
    env = dict(os.environ)
    appdir = os.path.normpath(env.get("APPDIR", "")) if env.get("APPDIR") else ""
    meipass = os.path.normpath(getattr(sys, "_MEIPASS", "") or "") if getattr(sys, "_MEIPASS", None) else ""

    for key in (
        "QT_QPA_PLATFORM",
        "QT_ENABLE_HIGHDPI_SCALING",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QT_QPA_PLATFORMTHEME",
        "QT_STYLE_OVERRIDE",
        "QML2_IMPORT_PATH",
        "QML_IMPORT_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "GTK_PATH",
        "GTK_EXE_PREFIX",
        "GTK_DATA_PREFIX",
        "GIO_MODULE_DIR",
        "GIO_EXTRA_MODULES",
        "GDK_PIXBUF_MODULE_FILE",
        "GDK_PIXBUF_MODULEDIR",
        "GSETTINGS_SCHEMA_DIR",
    ):
        env.pop(key, None)

    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS", "PATH"):
        orig = env.get(f"{key}_ORIG")
        if orig is not None:
            env[key] = orig
            continue
        if key not in env:
            continue
        parts = [p for p in env[key].split(os.pathsep) if p and not _is_bundled_path(p, appdir, meipass)]
        if parts:
            env[key] = os.pathsep.join(parts)
        elif key != "PATH":
            env.pop(key, None)
    return env


def _linux_backends() -> List[Tuple[str, str]]:
    """Return available Linux native picker binaries ordered for the active desktop environment."""
    if not sys.platform.startswith("linux"):
        return []
    if os.environ.get("OOT_RANDO_NO_NATIVE_DIALOGS") == "1":
        return []
    desktop = (
        os.environ.get("XDG_CURRENT_DESKTOP", "")
        + ":"
        + os.environ.get("DESKTOP_SESSION", "")
    ).lower()
    if any(k in desktop for k in ("kde", "plasma", "lxqt")):
        order = ("kdialog", "qarma", "zenity", "matedialog")
    elif "mate" in desktop:
        order = ("matedialog", "zenity", "kdialog", "qarma")
    else:
        order = ("zenity", "kdialog", "qarma", "matedialog")

    clean_path = clean_native_env().get("PATH")
    found: List[Tuple[str, str]] = []
    for tool in order:
        exe = shutil.which(tool, path=clean_path)
        if exe:
            found.append((tool, exe))
    return found


def normalize_filters(
    filetypes: Optional[Sequence[Tuple[str, str]]] = None,
    qt_filter: str = "",
) -> List[FilterSpec]:
    "Normalize Tkinter filetypes or Qt filter strings into [(label, [patterns])]."
    specs: List[FilterSpec] = []
    if filetypes:
        for label, raw_pats in filetypes:
            pats = [p.strip() for p in str(raw_pats).replace(";", " ").split() if p.strip()]
            if pats:
                specs.append((str(label).strip() or "Files", pats))
    elif qt_filter:
        for part in qt_filter.split(";;"):
            part = part.strip()
            if not part:
                continue
            m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", part)
            if m:
                label = m.group(1).strip() or "Files"
                pats = [p.strip() for p in m.group(2).split() if p.strip()]
                if pats:
                    specs.append((label, pats))
            else:
                specs.append((part, ["*"]))
    return specs


def _kdialog_filter_arg(filters: List[FilterSpec]) -> str:
    """Format normalized filters into kdialog newline-delimited filter syntax."""
    if not filters:
        return ""
    lines = []
    for label, pats in filters:
        pat_str = " ".join(pats)
        lines.append(f"{label} ({pat_str})")
    if not any("*" in pats or "*.*" in pats for _, pats in filters):
        lines.append("All Files (*)")
    return "\n".join(lines)


def _zenity_filter_args(filters: List[FilterSpec]) -> List[str]:
    """Format normalized filters into ``--file-filter`` CLI flags for zenity-compatible pickers."""
    if not filters:
        return []
    args = []
    for label, pats in filters:
        pat_str = " ".join(pats)
        args.append(f"--file-filter={label} | {pat_str}")
    if not any("*" in pats or "*.*" in pats for _, pats in filters):
        args.append("--file-filter=All Files | *")
    return args


def _resolve_start_dir(initialdir: str) -> str:
    """Resolve an initial directory (or file parent) to an existing directory, falling back to ``~``."""
    if initialdir:
        expanded = os.path.abspath(os.path.expanduser(initialdir))
        if os.path.isdir(expanded):
            return expanded
        parent = os.path.dirname(expanded)
        if parent and os.path.isdir(parent):
            return parent
    return os.path.expanduser("~")


def _run_picker_cmd(cmd: List[str]) -> Optional[str]:
    "Run a native picker command; returns path on ok, empty string on cancel, None on error."
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=clean_native_env(),
        )
    except OSError:
        return None
    if proc.returncode == 0:
        return proc.stdout.strip()
    if proc.returncode in (1, 5):
        return ""
    return None


def _apply_default_ext(path: str, defaultextension: str) -> str:
    """Append ``defaultextension`` when the chosen save path has no extension."""
    if not path or not defaultextension:
        return path
    ext = defaultextension if defaultextension.startswith(".") else f".{defaultextension}"
    if not os.path.splitext(path)[1]:
        return path + ext
    return path


def _filters_to_qt(filters: List[FilterSpec], qt_filter: str) -> str:
    """Convert normalized filters into a ``QFileDialog`` filter string."""
    if qt_filter:
        return qt_filter
    if not filters:
        return ""
    parts = []
    for label, pats in filters:
        pat_str = " ".join(pats)
        parts.append(f"{label} ({pat_str})")
    return ";;".join(parts)


def _filters_to_tk(
    filters: List[FilterSpec],
    filetypes: Optional[Sequence[Tuple[str, str]]],
) -> Optional[List[Tuple[str, str]]]:
    """Convert normalized filters into ``tkinter.filedialog`` ``filetypes`` tuples."""
    if filetypes:
        return list(filetypes)
    if not filters:
        return None
    return [(label, " ".join(pats)) for label, pats in filters]


def ask_directory(
    title: str = "Select Folder",
    initialdir: str = "",
    *,
    qt_parent=None,
    tk_parent=None,
) -> str:
    """Prompt for an existing directory using a native Linux picker, Qt, or Tk fallback."""
    start_dir = _resolve_start_dir(initialdir)
    for backend, exe in _linux_backends():
        if backend == "kdialog":
            cmd = [exe, "--title", title, "--getexistingdirectory", start_dir]
        else:
            cmd = [
                exe,
                "--file-selection",
                "--directory",
                "--title",
                title,
                "--filename",
                start_dir.rstrip(os.sep) + os.sep,
            ]
        res = _run_picker_cmd(cmd)
        if res is not None:
            return posixpath.normpath(res) if res else ""

    if qt_parent is not None:
        from PySide6.QtWidgets import QFileDialog
        chosen = QFileDialog.getExistingDirectory(qt_parent, title, start_dir) or ""
        return os.path.normpath(chosen) if chosen else ""

    from tkinter import filedialog
    kwargs = {"title": title, "initialdir": start_dir}
    if tk_parent is not None:
        kwargs["parent"] = tk_parent
    chosen = filedialog.askdirectory(**kwargs) or ""
    return os.path.normpath(chosen) if chosen else ""


def ask_open_file(
    title: str = "Select File",
    initialdir: str = "",
    filetypes: Optional[Sequence[Tuple[str, str]]] = None,
    qt_filter: str = "",
    *,
    qt_parent=None,
    tk_parent=None,
) -> str:
    """Prompt to open an existing file using a native Linux picker, Qt, or Tk fallback."""
    start_dir = _resolve_start_dir(initialdir)
    filters = normalize_filters(filetypes=filetypes, qt_filter=qt_filter)
    for backend, exe in _linux_backends():
        if backend == "kdialog":
            cmd = [exe, "--title", title, "--getopenfilename", start_dir]
            flt = _kdialog_filter_arg(filters)
            if flt:
                cmd.append(flt)
        else:
            cmd = [
                exe,
                "--file-selection",
                "--title",
                title,
                "--filename",
                start_dir.rstrip(os.sep) + os.sep,
            ] + _zenity_filter_args(filters)
        res = _run_picker_cmd(cmd)
        if res is not None:
            return res

    if qt_parent is not None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(qt_parent, title, start_dir, _filters_to_qt(filters, qt_filter))
        return path or ""

    from tkinter import filedialog
    kwargs = {"title": title, "initialdir": start_dir}
    tk_ft = _filters_to_tk(filters, filetypes)
    if tk_ft:
        kwargs["filetypes"] = tk_ft
    if tk_parent is not None:
        kwargs["parent"] = tk_parent
    return filedialog.askopenfilename(**kwargs) or ""


def ask_save_file(
    title: str = "Save File",
    initialdir: str = "",
    initialfile: str = "",
    defaultextension: str = "",
    filetypes: Optional[Sequence[Tuple[str, str]]] = None,
    qt_filter: str = "",
    *,
    qt_parent=None,
    tk_parent=None,
) -> str:
    """Prompt for a save file path using a native Linux picker, Qt, or Tk fallback."""
    start_dir = _resolve_start_dir(initialdir)
    target = os.path.join(start_dir, initialfile) if initialfile else (start_dir.rstrip(os.sep) + os.sep)
    filters = normalize_filters(filetypes=filetypes, qt_filter=qt_filter)
    for backend, exe in _linux_backends():
        if backend == "kdialog":
            cmd = [exe, "--title", title, "--getsavefilename", target]
            flt = _kdialog_filter_arg(filters)
            if flt:
                cmd.append(flt)
        else:
            cmd = [
                exe,
                "--file-selection",
                "--save",
                "--title",
                title,
                "--filename",
                target,
            ] + _zenity_filter_args(filters)
        res = _run_picker_cmd(cmd)
        if res is not None:
            return _apply_default_ext(res, defaultextension)

    if qt_parent is not None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(qt_parent, title, target, _filters_to_qt(filters, qt_filter))
        return _apply_default_ext(path or "", defaultextension)

    from tkinter import filedialog
    kwargs = {"title": title, "initialdir": start_dir}
    if initialfile:
        kwargs["initialfile"] = initialfile
    if defaultextension:
        kwargs["defaultextension"] = defaultextension
    tk_ft = _filters_to_tk(filters, filetypes)
    if tk_ft:
        kwargs["filetypes"] = tk_ft
    if tk_parent is not None:
        kwargs["parent"] = tk_parent
    return filedialog.asksaveasfilename(**kwargs) or ""


def askdirectory(
    title: str = "Select Folder",
    initialdir: str = "",
    parent=None,
    **_kwargs,
) -> str:
    """Drop-in replacement for ``tkinter.filedialog.askdirectory``."""
    return ask_directory(title=title, initialdir=initialdir, tk_parent=parent)


def askopenfilename(
    title: str = "Select File",
    initialdir: str = "",
    filetypes: Optional[Sequence[Tuple[str, str]]] = None,
    parent=None,
    **_kwargs,
) -> str:
    """Drop-in replacement for ``tkinter.filedialog.askopenfilename``."""
    return ask_open_file(title=title, initialdir=initialdir, filetypes=filetypes, tk_parent=parent)


def asksaveasfilename(
    title: str = "Save File",
    initialdir: str = "",
    initialfile: str = "",
    defaultextension: str = "",
    filetypes: Optional[Sequence[Tuple[str, str]]] = None,
    parent=None,
    **_kwargs,
) -> str:
    """Drop-in replacement for ``tkinter.filedialog.asksaveasfilename``."""
    return ask_save_file(
        title=title,
        initialdir=initialdir,
        initialfile=initialfile,
        defaultextension=defaultextension,
        filetypes=filetypes,
        tk_parent=parent,
    )


def open_in_file_manager(target, env=None):
    """Open a folder or file in the OS file manager (Windows, Linux, macOS).

    On Linux, strips AppImage / PyInstaller / embedded-Qt environment overrides
    when ``env`` is not explicitly supplied so ``xdg-open`` launches cleanly.
    """
    target_str = str(target)
    if sys.platform == "win32":
        os.startfile(target_str)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target_str], env=env)
    else:
        if env is None:
            env = clean_native_env()
        subprocess.Popen(["xdg-open", target_str], env=env)
