import sys
from pathlib import Path

from dotenv import load_dotenv


def _enable_windows_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            return


def main() -> None:
    _enable_windows_dpi_awareness()
    load_dotenv(Path.cwd() / ".env", override=False)
    from transimage.app import main as run_app

    run_app()


if __name__ == "__main__":
    main()
