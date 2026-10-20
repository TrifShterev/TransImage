import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

_FONT_CANDIDATES = ("Segoe UI", "Helvetica", "DejaVu Sans")


def shortcut_modifier() -> str:
    if sys.platform == "darwin":
        return "Command"
    return "Control"


def accelerator_label() -> str:
    if sys.platform == "darwin":
        return "Cmd+O"
    return "Ctrl+O"


def choose_font_family(available: Iterable[str]) -> str | None:
    lookup = {name.casefold(): name for name in available}
    for candidate in _FONT_CANDIDATES:
        found = lookup.get(candidate.casefold())
        if found is not None:
            return found
    return None


def open_with_system_player(path: Path) -> None:
    if sys.platform == "win32":
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise OSError("No system player is available.")
        startfile(str(path))
        return
    if sys.platform == "darwin":
        opener = "open"
    else:
        opener = shutil.which("xdg-open")
        if opener is None:
            raise OSError("No system player found (xdg-open is not installed).")
    subprocess.Popen([opener, str(path)])
