"""PyInstaller / source entry for the desktop application."""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fbosint_desktop.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
