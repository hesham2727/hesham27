"""Data retention: delete investigations (and their media files) older than N days."""
from __future__ import annotations

import shutil
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Investigation, utcnow
from .app_config import general_settings
from .audit import audit


def delete_investigation(db: Session, inv: Investigation) -> None:
    media_folder = get_settings().media_dir / str(inv.id)
    db.delete(inv)
    db.commit()
    if media_folder.exists():
        shutil.rmtree(media_folder, ignore_errors=True)


def purge_expired(db: Session) -> int:
    days = int(general_settings(db).get("retention_days", 0) or 0)
    if days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=days)
    expired = list(db.scalars(select(Investigation).where(Investigation.created_at < cutoff, Investigation.status != "running")))
    for inv in expired:
        ref = inv.reference
        delete_investigation(db, inv)
        audit(db, "retention_purge", None, "investigation", ref, username="system", details={"retention_days": days})
    return len(expired)
