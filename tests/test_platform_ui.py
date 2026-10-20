import os
import shutil
import subprocess
import sys

import pytest

from transimage.platform_ui import (
    accelerator_label,
    choose_font_family,
    open_with_system_player,
    shortcut_modifier,
)


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


def test_system_player_uses_startfile_on_windows(monkeypatch, tmp_path) -> None:
    opened = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)
    open_with_system_player(tmp_path / "clip.mp4")
    assert opened == [str(tmp_path / "clip.mp4")]


def test_system_player_raises_without_startfile(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(os, "startfile", raising=False)
    with pytest.raises(OSError):
        open_with_system_player(tmp_path / "clip.mp4")


def test_system_player_uses_open_on_macos(monkeypatch, tmp_path) -> None:
    commands = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda cmd: commands.append(cmd))
    open_with_system_player(tmp_path / "clip.mp4")
    assert commands == [["open", str(tmp_path / "clip.mp4")]]


def test_system_player_uses_xdg_open_on_linux(monkeypatch, tmp_path) -> None:
    commands = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(subprocess, "Popen", lambda cmd: commands.append(cmd))
    open_with_system_player(tmp_path / "clip.mp4")
    assert commands == [["/usr/bin/xdg-open", str(tmp_path / "clip.mp4")]]


def test_system_player_missing_xdg_open_raises(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(OSError, match="xdg-open"):
        open_with_system_player(tmp_path / "clip.mp4")
