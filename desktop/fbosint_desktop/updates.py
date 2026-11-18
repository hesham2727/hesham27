"""Update check against a JSON manifest: {"version": "1.1.0", "url": "...", "sha256": "..."}."""
from __future__ import annotations

import httpx

from . import __version__


def _v(s: str) -> tuple[int, ...]:
    return tuple(int(p) for p in s.split(".") if p.isdigit())


def check(manifest_url: str, transport: httpx.BaseTransport | None = None) -> dict | None:
    if not manifest_url.lower().startswith("https://"):
        return None
    with httpx.Client(timeout=10, transport=transport) as c:
        data = c.get(manifest_url).json()
    if _v(str(data.get("version", "0"))) > _v(__version__) and str(data.get("url", "")).startswith("https://"):
        return data
    return None
