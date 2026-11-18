from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import AuditLog, User
from ..security import client_ip


def audit(
    db: Session,
    action: str,
    *,
    user: User | None = None,
    request: Request | None = None,
    entity_type: str = "",
    entity_id: int | str | None = None,
    details: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "",
        action=action,
        entity_type=entity_type,
        entity_id="" if entity_id is None else str(entity_id),
        details=details or None,
        ip=client_ip(request) if request is not None else "",
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
