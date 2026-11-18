"""Resource resolution that works from source and from a PyInstaller bundle."""
from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]  # repository root


def shared_i18n_dir() -> Path:
    return resource_root() / "shared" / "i18n"


def ensure_backend_importable() -> None:
    if not getattr(sys, "frozen", False):
        backend = resource_root() / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
