"""Append-only audit trail."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditLog, User


def audit(
    db: Session,
    action: str,
    user: User | None = None,
    target_type: str = "",
    target_id: str | int = "",
    ip: str = "",
    success: bool = True,
    details: dict[str, Any] | None = None,
    username: str = "",
    commit: bool = True,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            username=(user.username if user else username)[:64],
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            ip_address=ip[:64],
            success=success,
            details=details or {},
        )
    )
    if commit:
        db.commit()
