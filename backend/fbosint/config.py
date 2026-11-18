"""Application configuration loaded from environment variables.

All settings use the ``FBO_`` prefix. Secrets are never hard-coded: when no
encryption key is provided, one is generated on first start and stored in the
data directory with owner-only permissions.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def default_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "FBOSINT"
    return Path.home() / ".fbosint"


@dataclass
class Settings:
    env: str = "production"
    mode: str = "local"  # local | network
    data_dir: Path = field(default_factory=default_data_dir)
    database_url: str = ""
    encryption_key: str = ""
    host: str = "127.0.0.1"
    port: int = 8765
    tls_certfile: str = ""
    tls_keyfile: str = ""
    cookie_secure: bool | None = None  # None -> auto (True when TLS configured)
    cors_origins: list[str] = field(default_factory=list)
    session_ttl_hours: int = 12
    session_idle_minutes: int = 60
    rate_limit_per_minute: int = 240
    login_rate_limit_per_minute: int = 10
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    retention_days: int = 365
    backup_interval_hours: int = 24
    backup_keep: int = 14
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_access_token: str = ""
    meta_graph_version: str = "v23.0"
    meta_redirect_uri: str = ""
    http_timeout: float = 15.0
    enrich_allow_private_networks: bool = False
    enrich_max_bytes: int = 2_000_000
    media_max_bytes: int = 10_000_000
    max_posts: int = 200
    user_agent: str = "FBOSINT-Analyzer/1.0 (+public-source research; respects robots.txt)"
    frontend_dist: str = ""
    update_manifest_url: str = ""
    run_jobs_inline: bool = False  # tests: run investigations synchronously
    scheduler_enabled: bool = True

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def tls_enabled(self) -> bool:
        return bool(self.tls_certfile and self.tls_keyfile)

    @property
    def secure_cookies(self) -> bool:
        return self.tls_enabled if self.cookie_secure is None else self.cookie_secure

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.media_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)

    def resolve_encryption_key(self) -> str:
        """Return the Fernet key, generating and persisting one if needed."""
        if self.encryption_key:
            Fernet(self.encryption_key.encode())  # validate
            return self.encryption_key
        key_file = self.data_dir / "secret.key"
        if key_file.exists():
            self.encryption_key = key_file.read_text().strip()
        else:
            self.ensure_dirs()
            self.encryption_key = Fernet.generate_key().decode()
            fd = os.open(str(key_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(self.encryption_key)
        return self.encryption_key


def read_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser (KEY=VALUE, # comments). Never overrides real environment variables."""
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def load_settings(env: dict[str, str] | None = None) -> Settings:
    if env is None:
        e: dict[str, str] = {}
        base_dir = Path(os.environ.get("FBO_DATA_DIR") or default_data_dir()).expanduser()
        for candidate in (base_dir / ".env", Path.cwd() / ".env"):
            if candidate.is_file():
                e.update(read_env_file(candidate))
        e.update(os.environ)
    else:
        e = env
    data_dir = Path(e.get("FBO_DATA_DIR") or default_data_dir()).expanduser()
    s = Settings(
        env=e.get("FBO_ENV", "production"),
        mode=e.get("FBO_MODE", "local"),
        data_dir=data_dir,
        database_url=e.get("FBO_DATABASE_URL", ""),
        encryption_key=e.get("FBO_ENCRYPTION_KEY", ""),
        host=e.get("FBO_HOST", "127.0.0.1"),
        port=_int(e.get("FBO_PORT"), 8765),
        tls_certfile=e.get("FBO_TLS_CERTFILE", ""),
        tls_keyfile=e.get("FBO_TLS_KEYFILE", ""),
        cookie_secure=None if e.get("FBO_COOKIE_SECURE") in (None, "") else _bool(e.get("FBO_COOKIE_SECURE")),
        cors_origins=[o.strip() for o in e.get("FBO_CORS_ORIGINS", "").split(",") if o.strip()],
        session_ttl_hours=_int(e.get("FBO_SESSION_TTL_HOURS"), 12),
        session_idle_minutes=_int(e.get("FBO_SESSION_IDLE_MINUTES"), 60),
        rate_limit_per_minute=_int(e.get("FBO_RATE_LIMIT_PER_MINUTE"), 240),
        login_rate_limit_per_minute=_int(e.get("FBO_LOGIN_RATE_LIMIT_PER_MINUTE"), 10),
        login_max_failures=_int(e.get("FBO_LOGIN_MAX_FAILURES"), 5),
        login_lockout_minutes=_int(e.get("FBO_LOGIN_LOCKOUT_MINUTES"), 15),
        retention_days=_int(e.get("FBO_RETENTION_DAYS"), 365),
        backup_interval_hours=_int(e.get("FBO_BACKUP_INTERVAL_HOURS"), 24),
        backup_keep=_int(e.get("FBO_BACKUP_KEEP"), 14),
        meta_app_id=e.get("FBO_META_APP_ID", ""),
        meta_app_secret=e.get("FBO_META_APP_SECRET", ""),
        meta_access_token=e.get("FBO_META_ACCESS_TOKEN", ""),
        meta_graph_version=e.get("FBO_META_GRAPH_VERSION", "v23.0"),
        meta_redirect_uri=e.get("FBO_META_REDIRECT_URI", ""),
        http_timeout=float(e.get("FBO_HTTP_TIMEOUT", "15") or 15),
        enrich_allow_private_networks=_bool(e.get("FBO_ENRICH_ALLOW_PRIVATE_NETWORKS")),
        max_posts=_int(e.get("FBO_MAX_POSTS"), 200),
        frontend_dist=e.get("FBO_FRONTEND_DIST", ""),
        update_manifest_url=e.get("FBO_UPDATE_MANIFEST_URL", ""),
        run_jobs_inline=_bool(e.get("FBO_RUN_JOBS_INLINE")),
        scheduler_enabled=_bool(e.get("FBO_SCHEDULER_ENABLED"), True),
    )
    if not s.database_url:
        s.database_url = f"sqlite:///{(data_dir / 'fbosint.db').as_posix()}"
    return s


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_settings(settings: Settings | None) -> None:
    """Replace the active settings (used by tests and the desktop launcher)."""
    global _settings
    _settings = settings
