"""Data-retention purge. Runs at start-up, every 24 h, and on demand."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import AuditLog, AuthSession, Investigation, LocationInvitation, LocationRecord, NumberCheck, utcnow
from .app_settings import load_all
from .audit import audit


def run_retention(db: Session, user=None, request=None) -> dict:
    cfg = load_all(db)["retention"]
    now = utcnow()
    counts: dict[str, int] = {}

    def older(days: int):
        return now - timedelta(days=int(days))

    if int(cfg.get("location_records_days", 0)) > 0:
        counts["location_records"] = (
            db.query(LocationRecord)
            .filter(LocationRecord.collected_at < older(cfg["location_records_days"]))
            .delete(synchronize_session=False)
        )
    if int(cfg.get("invitations_days", 0)) > 0:
        counts["invitations"] = (
            db.query(LocationInvitation)
            .filter(LocationInvitation.expires_at < older(cfg["invitations_days"]))
            .delete(synchronize_session=False)
        )
    if int(cfg.get("number_checks_days", 0)) > 0:
        counts["number_checks"] = (
            db.query(NumberCheck)
            .filter(NumberCheck.checked_at < older(cfg["number_checks_days"]))
            .delete(synchronize_session=False)
        )
    if int(cfg.get("closed_investigations_days", 0)) > 0:
        old = (
            db.query(Investigation)
            .filter(Investigation.status == "closed", Investigation.closed_at < older(cfg["closed_investigations_days"]))
            .all()
        )
        for inv in old:
            db.delete(inv)
        counts["closed_investigations"] = len(old)
    if int(cfg.get("audit_logs_days", 0)) > 0:
        counts["audit_logs"] = (
            db.query(AuditLog).filter(AuditLog.at < older(cfg["audit_logs_days"])).delete(synchronize_session=False)
        )
    counts["expired_sessions"] = (
        db.query(AuthSession).filter(AuthSession.expires_at < now).delete(synchronize_session=False)
    )
    db.commit()
    audit(db, "retention.run", user=user, request=request, details=counts)
    return counts
