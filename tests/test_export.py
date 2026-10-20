import sys
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from transimage import export
from transimage.export import (
    DEFAULT_VIDEO_EXPORT_FORMAT,
    VIDEO_EXPORT_FORMATS,
    build_export_path,
    parse_xdg_pictures_dir,
    pictures_dir,
    prepare_for_format,
    resolve_export_target,
    save_image,
    save_video,
)

_NOW = datetime(2026, 10, 19, 14, 30, 5)


def test_png_export_keeps_size_and_alpha(tmp_path: Path) -> None:
    image = Image.new("RGBA", (40, 20), (10, 20, 30, 128))
    target = tmp_path / "photo.png"
    save_image(image, target, "PNG")
    with Image.open(target) as opened:
        assert opened.format == "PNG"
        assert opened.size == (40, 20)
        assert opened.mode == "RGBA"


@pytest.mark.parametrize("fmt, ext", [("JPG", "jpg"), ("JPEG", "jpeg")])
def test_jpeg_export_writes_jpeg(tmp_path: Path, fmt: str, ext: str) -> None:
    image = Image.new("RGB", (30, 30), (200, 0, 0))
    target = tmp_path / f"photo.{ext}"
    save_image(image, target, fmt)
    with Image.open(target) as opened:
        assert opened.format == "JPEG"
        assert opened.size == (30, 30)


def test_jpeg_flattens_transparency_onto_white() -> None:
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    prepared = prepare_for_format(image, "JPG")
    assert prepared.mode == "RGB"
    assert prepared.getpixel((0, 0)) == (255, 255, 255)


def test_png_converts_unsupported_modes() -> None:
    assert prepare_for_format(Image.new("CMYK", (2, 2)), "PNG").mode == "RGB"
    assert prepare_for_format(Image.new("PA", (2, 2)), "PNG").mode == "RGBA"


def test_save_creates_missing_folder(tmp_path: Path) -> None:
    target = tmp_path / "Pictures" / "TransImage" / "a.png"
    save_image(Image.new("RGB", (5, 5)), target, "PNG")
    assert target.is_file()
    assert [p.name for p in target.parent.iterdir()] == ["a.png"]


def test_save_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "a.png"
    target.write_bytes(b"old")
    save_image(Image.new("RGB", (5, 5)), target, "PNG")
    with Image.open(target) as opened:
        assert opened.format == "PNG"


def test_suggested_name_avoids_existing_files(tmp_path: Path) -> None:
    first = build_export_path(tmp_path, "a", "PNG", _NOW)
    assert first == tmp_path / "a_20261019-143005.png"
    first.write_bytes(b"existing")
    second = build_export_path(tmp_path, "a", "PNG", _NOW)
    assert second == tmp_path / "a_20261019-143005_1.png"


def test_unknown_format_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_image(Image.new("RGB", (5, 5)), tmp_path / "a.gif", "GIF")


@pytest.mark.parametrize(
    "selected, chosen, expected_name, expected_fmt",
    [
        ("pic.png", "JPEG", "pic.png", "PNG"),
        ("pic.JPG", "PNG", "pic.JPG", "JPG"),
        ("pic.jpeg", None, "pic.jpeg", "JPEG"),
        ("pic", "JPG", "pic.jpg", "JPG"),
        ("pic", None, "pic.png", "PNG"),
        ("pic.bmp", "JPEG", "pic.bmp.jpeg", "JPEG"),
    ],
)
def test_resolve_export_target(
    tmp_path: Path, selected: str, chosen, expected_name: str, expected_fmt: str
) -> None:
    path, fmt = resolve_export_target(str(tmp_path / selected), chosen)
    assert path == tmp_path / expected_name
    assert fmt == expected_fmt


@pytest.mark.parametrize(
    "selected, chosen, expected_name",
    [
        ("clip.mp4", "MP4", "clip.mp4"),
        ("clip.MP4", None, "clip.MP4"),
        ("clip", "MP4", "clip.mp4"),
        ("clip", None, "clip.mp4"),
        ("clip.mov", "MP4", "clip.mov.mp4"),
        ("clip.png", "PNG", "clip.png.mp4"),
    ],
)
def test_resolve_video_export_target(
    tmp_path: Path, selected: str, chosen, expected_name: str
) -> None:
    path, fmt = resolve_export_target(
        str(tmp_path / selected),
        chosen,
        VIDEO_EXPORT_FORMATS,
        DEFAULT_VIDEO_EXPORT_FORMAT,
    )
    assert path == tmp_path / expected_name
    assert fmt == "MP4"


def test_suggested_video_name(tmp_path: Path) -> None:
    assert build_export_path(tmp_path, "a", "MP4", _NOW) == (
        tmp_path / "a_20261019-143005.mp4"
    )


def test_save_video_copies_bytes(tmp_path: Path) -> None:
    source = tmp_path / "src.mp4"
    source.write_bytes(b"video-bytes" * 1000)
    target = tmp_path / "out.mp4"
    save_video(source, target)
    assert target.read_bytes() == source.read_bytes()
    assert source.exists()


def test_save_video_replaces_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "src.mp4"
    source.write_bytes(b"new")
    target = tmp_path / "out.mp4"
    target.write_bytes(b"old")
    save_video(source, target)
    assert target.read_bytes() == b"new"


def test_save_video_creates_folder_and_leaves_no_partial(tmp_path: Path) -> None:
    source = tmp_path / "src.mp4"
    source.write_bytes(b"data")
    target = tmp_path / "Pictures" / "TransImage" / "out.mp4"
    save_video(source, target)
    assert [p.name for p in target.parent.iterdir()] == ["out.mp4"]


def test_save_video_failure_leaves_no_partial(tmp_path: Path) -> None:
    target = tmp_path / "out"
    with pytest.raises(OSError):
        save_video(tmp_path / "missing.mp4", target / "out.mp4")
    assert not list(tmp_path.rglob("*.partial"))


def test_parse_xdg_pictures_dir(tmp_path: Path) -> None:
    home = tmp_path
    text = '# comment\nXDG_PICTURES_DIR="$HOME/Bilder"\n'
    assert parse_xdg_pictures_dir(text, home) == home / "Bilder"
    assert parse_xdg_pictures_dir('XDG_PICTURES_DIR="$HOME/"', home) is None
    assert parse_xdg_pictures_dir('XDG_MUSIC_DIR="$HOME/Music"', home) is None


def test_pictures_dir_defaults_to_home_pictures_on_macos(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert pictures_dir() == tmp_path / "Pictures"


def test_pictures_dir_reads_xdg_config_on_linux(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    config = tmp_path / "config"
    config.mkdir()
    (config / "user-dirs.dirs").write_text(
        'XDG_PICTURES_DIR="$HOME/Photos"\n', encoding="utf-8"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    assert pictures_dir() == tmp_path / "Photos"
    assert export.export_dir() == tmp_path / "Photos" / "TransImage"
