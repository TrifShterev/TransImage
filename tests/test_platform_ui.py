import sys

from transimage.platform_ui import accelerator_label, choose_font_family, shortcut_modifier


def test_modifier_is_command_on_darwin(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert shortcut_modifier() == "Command"
    assert accelerator_label() == "Cmd+O"


def test_modifier_is_control_on_windows_and_linux(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert shortcut_modifier() == "Control"
    assert accelerator_label() == "Ctrl+O"
    monkeypatch.setattr(sys, "platform", "linux")
    assert shortcut_modifier() == "Control"
    assert accelerator_label() == "Ctrl+O"


def test_font_family_prefers_installed_candidates_in_order() -> None:
    assert choose_font_family(["Arial", "Segoe UI", "Helvetica"]) == "Segoe UI"
    assert choose_font_family(["DejaVu Sans", "Helvetica"]) == "Helvetica"
    assert choose_font_family(["dejavu sans"]) == "dejavu sans"
    assert choose_font_family(["Arial", "Times New Roman"]) is None
