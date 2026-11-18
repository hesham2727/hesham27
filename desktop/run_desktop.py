"""PyInstaller / source entry for the desktop application."""
import os
import sys
from pathlib import Path


def _ensure_streams() -> None:
    """Windowed (no-console) Windows builds have sys.stdout/stderr = None, which breaks
    libraries that log to the console. Send output to %APPDATA%\\FBOSINT\\logs instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    base = os.environ.get("FBO_DATA_DIR") or (os.path.join(os.environ.get("APPDATA", str(Path.home())), "FBOSINT") if os.name == "nt" else str(Path.home() / ".fbosint"))
    log_dir = Path(base) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = open(log_dir / "desktop.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives for the process
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


_ensure_streams()

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fbosint_desktop.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
