"""Optional, free reverse-geocoding adapter (OSM Nominatim). Disabled by default.

Policy compliance: one request per second max, identifying User-Agent,
manual on-demand use only, results cached on the location record.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

from .. import __version__

_lock = threading.Lock()
_last_call = 0.0


class GeocodingUnavailable(Exception):
    pass


def reverse_geocode(endpoint: str, lat: float, lon: float, timeout: float = 10.0) -> str:
    global _last_call
    with _lock:
        wait = 1.05 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    query = urllib.parse.urlencode(
        {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2", "accept-language": "ar", "zoom": 18}
    )
    req = urllib.request.Request(
        f"{endpoint}?{query}",
        headers={"User-Agent": f"Tahqiq/{__version__} (self-hosted MVP; manual on-demand lookups)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https endpoint
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network down, policy block, etc.
        raise GeocodingUnavailable(str(exc)) from exc
    return str(data.get("display_name") or "")
