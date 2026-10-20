import os
import shutil
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from PIL import Image

EXPORT_FORMATS = ("PNG", "JPG", "JPEG")
DEFAULT_EXPORT_FORMAT = "PNG"
VIDEO_EXPORT_FORMATS = ("MP4",)
DEFAULT_VIDEO_EXPORT_FORMAT = "MP4"
EXPORT_FOLDER_NAME = "TransImage"
_JPEG_QUALITY = 95
_PNG_MODES = ("1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA")
_ALPHA_MODES = ("RGBA", "RGBa", "LA", "La", "PA")
_WIN_SHELL_FOLDERS = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
)


def _windows_pictures_dir() -> Path | None:
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_SHELL_FOLDERS) as key:
            value, _kind = winreg.QueryValueEx(key, "My Pictures")
    except OSError:
        return None
    expanded = os.path.expandvars(str(value)).strip()
    return Path(expanded) if expanded else None


def parse_xdg_pictures_dir(text: str, home: Path) -> Path | None:
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("XDG_PICTURES_DIR="):
            continue
        value = line.partition("=")[2].strip().strip('"')
        path = Path(value.replace("$HOME", str(home)))
        if not path.is_absolute() or path == home:
            return None
        return path
    return None


def _xdg_pictures_dir(home: Path) -> Path | None:
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    try:
        text = (Path(config_home) / "user-dirs.dirs").read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_xdg_pictures_dir(text, home)


def pictures_dir() -> Path:
    home = Path.home()
    found: Path | None = None
    if sys.platform == "win32":
        found = _windows_pictures_dir()
    elif sys.platform != "darwin":
        found = _xdg_pictures_dir(home)
    return found or home / "Pictures"


def export_dir() -> Path:
    return pictures_dir() / EXPORT_FOLDER_NAME


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in _ALPHA_MODES:
        return True
    return image.mode == "P" and "transparency" in image.info


def prepare_for_format(image: Image.Image, fmt: str) -> Image.Image:
    if fmt == "PNG":
        if image.mode in _PNG_MODES:
            return image
        return image.convert("RGBA" if _has_alpha(image) else "RGB")
    if _has_alpha(image):
        rgba = image.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, (255, 255, 255))
        flattened.paste(rgba, mask=rgba.getchannel("A"))
        return flattened
    if image.mode in ("RGB", "L"):
        return image
    return image.convert("RGB")


def build_export_path(folder: Path, stem: str, fmt: str, now: datetime) -> Path:
    ext = fmt.lower()
    base = f"{stem}_{now:%Y%m%d-%H%M%S}"
    candidate = folder / f"{base}.{ext}"
    counter = 1
    while candidate.exists():
        candidate = folder / f"{base}_{counter}.{ext}"
        counter += 1
    return candidate


def format_for_suffix(
    suffix: str, formats: tuple[str, ...] = EXPORT_FORMATS
) -> str | None:
    fmt = suffix.lstrip(".").upper()
    return fmt if fmt in formats else None


def resolve_export_target(
    selected: str,
    chosen_type: str | None,
    formats: tuple[str, ...] = EXPORT_FORMATS,
    default: str = DEFAULT_EXPORT_FORMAT,
) -> tuple[Path, str]:
    path = Path(selected)
    fmt = format_for_suffix(path.suffix, formats)
    if fmt is not None:
        return path, fmt
    fmt = chosen_type if chosen_type in formats else default
    return path.with_name(f"{path.name}.{fmt.lower()}"), fmt


def _write_atomic(path: Path, write: Callable[[BinaryIO], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    try:
        with partial.open("wb") as handle:
            write(handle)
        partial.replace(path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def save_image(image: Image.Image, path: Path, fmt: str) -> None:
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format: {fmt}")
    prepared = prepare_for_format(image, fmt)

    def write(handle: BinaryIO) -> None:
        if fmt == "PNG":
            prepared.save(handle, format="PNG")
        else:
            prepared.save(handle, format="JPEG", quality=_JPEG_QUALITY)

    _write_atomic(path, write)


def save_video(source: Path, path: Path) -> None:
    def write(handle: BinaryIO) -> None:
        with source.open("rb") as reader:
            shutil.copyfileobj(reader, handle)

    _write_atomic(path, write)
