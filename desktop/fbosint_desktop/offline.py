"""Local report cache — exported reports remain available without the server."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def save_report(reports_dir: str, filename: str, data: bytes) -> Path:
    d = Path(reports_dir)
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in filename if c.isalnum() or c in "-_.") or "report.bin"
    path = d / safe
    path.write_bytes(data)
    return path


def list_reports(reports_dir: str) -> list[dict]:
    d = Path(reports_dir)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("INV-*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.suffix.lower() in (".pdf", ".xlsx"):
            out.append({"name": p.name, "path": str(p), "size": p.stat().st_size, "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    return out
