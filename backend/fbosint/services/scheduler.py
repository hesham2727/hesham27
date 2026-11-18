"""Periodic maintenance: automatic backups and retention purge."""
from __future__ import annotations

import logging
import threading
import time

from ..config import get_settings

log = logging.getLogger("fbosint.scheduler")
_thread: threading.Thread | None = None
_stop = threading.Event()


def _loop() -> None:
    from ..database import SessionLocal
    from . import backup, retention

    s = get_settings()
    last_backup = 0.0
    while not _stop.is_set():
        now = time.time()
        try:
            if s.backup_interval_hours > 0 and now - last_backup >= s.backup_interval_hours * 3600:
                backup.create_backup(s, "auto")
                last_backup = now
            db = SessionLocal()
            try:
                retention.purge_expired(db)
            finally:
                db.close()
        except Exception:  # keep the scheduler alive
            log.exception("maintenance task failed")
        _stop.wait(3600)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="fbosint-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
