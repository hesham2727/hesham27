"""Runtime configuration, read from environment variables.

All values have safe defaults so the application runs fully offline with no
configuration at all (Desktop mode). Nothing here requires a paid service.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Tahqiq"
    return Path.home() / ".tahqiq"


def _resource_root() -> Path:
    """Folder holding bundled resources (frontend build, fonts, migrations).

    Under PyInstaller the files are unpacked to sys._MEIPASS.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent  # backend/


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # "desktop" = single Windows user, backend bound to 127.0.0.1
    # "server"  = Local/LAN web app or Internet (VPS / tunnel) deployment
    mode: str = field(default_factory=lambda: os.environ.get("TAHQIQ_MODE", "server"))
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("TAHQIQ_DATA_DIR", str(_default_data_dir())))
    )
    database_url: str = field(default_factory=lambda: os.environ.get("TAHQIQ_DATABASE_URL", ""))
    # Externally reachable HTTPS base URL used in customer invitations.
    # If empty here, the admin may set it in the Settings screen.
    public_base_url: str = field(default_factory=lambda: os.environ.get("TAHQIQ_PUBLIC_BASE_URL", ""))
    session_hours: int = field(default_factory=lambda: int(os.environ.get("TAHQIQ_SESSION_HOURS", "12")))
    # Force Secure cookies. Defaults to on when the public URL is https.
    secure_cookies: bool | None = field(
        default_factory=lambda: _bool("TAHQIQ_SECURE_COOKIES", False) if "TAHQIQ_SECURE_COOKIES" in os.environ else None
    )
    # Allow the very first admin account to be created from a non-loopback
    # address. Off by default so an exposed server cannot be hijacked.
    allow_remote_setup: bool = field(default_factory=lambda: _bool("TAHQIQ_ALLOW_REMOTE_SETUP", False))
    # Trust X-Forwarded-For from a local reverse proxy (Caddy / cloudflared).
    trust_proxy: bool = field(default_factory=lambda: _bool("TAHQIQ_TRUST_PROXY", False))
    resource_root: Path = field(default_factory=_resource_root)

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        if not self.database_url:
            self.database_url = f"sqlite:///{(self.data_dir / 'tahqiq.db').as_posix()}"

    @property
    def frontend_dist(self) -> Path:
        env = os.environ.get("TAHQIQ_FRONTEND_DIST")
        if env:
            return Path(env)
        bundled = self.resource_root / "frontend_dist"
        if bundled.exists():
            return bundled
        return self.resource_root.parent / "frontend" / "dist"

    @property
    def fonts_dir(self) -> Path:
        return self.resource_root / "app" / "assets" / "fonts"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings(new: Settings | None = None) -> Settings:
    """Used by tests and the desktop launcher."""
    global _settings
    _settings = new or Settings()
    return _settings
