"""Server-side session management. Only the SHA-256 of the token is stored."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User, UserSession, utcnow


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User, client: str, ip: str, user_agent: str) -> tuple[str, UserSession]:
    s = get_settings()
    token = secrets.token_urlsafe(32)
    now = utcnow()
    sess = UserSession(
        token_hash=_hash(token),
        csrf_token=secrets.token_urlsafe(24),
        user_id=user.id,
        client=client,
        ip_address=ip[:64],
        user_agent=user_agent[:255],
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=s.session_ttl_hours),
    )
    db.add(sess)
    db.commit()
    return token, sess


def resolve_session(db: Session, token: str) -> UserSession | None:
    if not token or len(token) > 200:
        return None
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == _hash(token)))
    if sess is None or sess.revoked:
        return None
    s = get_settings()
    now = utcnow()
    if now >= sess.expires_at or now - sess.last_seen_at > timedelta(minutes=s.session_idle_minutes):
        sess.revoked = True
        db.commit()
        return None
    if not sess.user.is_active:
        return None
    if (now - sess.last_seen_at).total_seconds() > 30:  # avoid a write per request
        sess.last_seen_at = now
        db.commit()
    return sess


def revoke_session(db: Session, sess: UserSession) -> None:
    sess.revoked = True
    db.commit()


def revoke_user_sessions(db: Session, user_id: int) -> None:
    db.execute(update(UserSession).where(UserSession.user_id == user_id).values(revoked=True))
    db.commit()
