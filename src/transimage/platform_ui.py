import sys
from collections.abc import Iterable

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
