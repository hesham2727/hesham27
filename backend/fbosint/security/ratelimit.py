"""In-memory sliding-window rate limiter (per client IP and bucket)."""
from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, bucket: str, limit: int, window: float = 60.0) -> tuple[bool, int]:
        """Register a hit. Returns (allowed, retry_after_seconds)."""
        if limit <= 0:
            return True, 0
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault((key, bucket), deque())
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                retry = int(window - (now - q[0])) + 1
                return False, max(retry, 1)
            q.append(now)
            if len(self._hits) > 50_000:  # bound memory under abuse
                self._gc(now, window)
            return True, 0

    def _gc(self, now: float, window: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= window]:
            del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()
