"""Desktop client configuration (stored next to the backend data, no secrets)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def data_dir() -> Path:
    d = os.environ.get("FBO_DATA_DIR")
    if d:
        return Path(d)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "FBOSINT"
    return Path.home() / ".fbosint"


@dataclass
class DesktopConfig:
    mode: str = "local"                  # local | network
    server_url: str = "https://fbosint-server:8765"
    verify_tls: bool = True
    ca_bundle: str = ""                  # optional path to a self-signed server certificate
    local_port: int = 8765
    language: str = "ar"
    last_username: str = ""
    reports_dir: str = field(default_factory=lambda: str(Path.home() / "Documents" / "FBOSINT Reports"))
    update_manifest_url: str = ""

    @staticmethod
    def path() -> Path:
        return data_dir() / "desktop.json"

    @classmethod
    def load(cls) -> "DesktopConfig":
        p = cls.path()
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
                return cls(**known)
            except (ValueError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}" if self.mode == "local" else self.server_url.rstrip("/")
