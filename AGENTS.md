# TransImage

## Cross-platform

TransImage must run on Windows, macOS, and Linux desktops. Use `pathlib` for paths. Do not add unguarded `ctypes.windll`, `win32`, AppKit, or X11 calls. Agents must not add OS-specific code without a guard and a fallback.

Fonts: use the first installed family from Segoe UI, Helvetica, DejaVu Sans. If none exist, use Tk's default family at about 16pt bold. Do not require Segoe UI.

Shortcuts: bind both `<Control-o>` and `<Command-o>`. The accelerator label is `Cmd+O` on macOS (`sys.platform == "darwin"`) and `Ctrl+O` on Windows and Linux.

Tk is the standard library. On Linux it may be a distro package (`python3-tk` or the distro equivalent). Do not pip-install tkinter.

## Stack

Python, tkinter, and Pillow. Later AI goes through the `openrouter` package. The key lives only in `.env` as `OPENROUTER_API_KEY`. Never commit `.env` or print the key. Do not call OpenRouter until a task asks for it.

## Dependencies

Use `uv`, `pyproject.toml`, `uv.lock`, and `.venv` only. Never add `requirements.txt`, `Pipfile`, or Poetry/PDM files.


## Launch

`uv sync`, then `uv run transimage`. Tests: `uv run pytest`.
