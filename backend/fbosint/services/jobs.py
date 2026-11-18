"""Background execution of investigations (thread pool; inline in tests)."""
from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor

from ..config import get_settings
from .engine import run_investigation

_executor: ThreadPoolExecutor | None = None
_running: dict[int, Future] = {}
_lock = threading.Lock()


def _pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fbosint-job")
    return _executor


def is_running(investigation_id: int) -> bool:
    with _lock:
        f = _running.get(investigation_id)
        return f is not None and not f.done()


def submit(investigation_id: int) -> bool:
    """Queue an investigation. Returns False if it is already running."""
    if get_settings().run_jobs_inline:
        run_investigation(investigation_id)
        return True
    with _lock:
        f = _running.get(investigation_id)
        if f is not None and not f.done():
            return False
        _running[investigation_id] = _pool().submit(run_investigation, investigation_id)
        return True


def wait_all(timeout: float | None = None) -> None:
    with _lock:
        futures = list(_running.values())
    for f in futures:
        f.result(timeout=timeout)
