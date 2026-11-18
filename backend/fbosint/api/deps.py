"""Authentication / authorisation dependencies."""
from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Role, User, UserSession
from ..security.sessions import resolve_session

SESSION_COOKIE = "fbo_session"
CSRF_COOKIE = "fbo_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class AuthContext:
    user: User
    session: UserSession
    via_cookie: bool


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    token = ""
    via_cookie = False
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    else:
        token = request.cookies.get(SESSION_COOKIE, "")
        via_cookie = bool(token)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    sess = resolve_session(db, token)
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session_invalid_or_expired")
    if via_cookie and request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, sess.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf_token_invalid")
    return AuthContext(user=sess.user, session=sess, via_cookie=via_cookie)


def current_user(ctx: AuthContext = Depends(get_auth)) -> User:
    return ctx.user


def require_roles(*roles: Role):
    allowed = {r.value for r in roles}

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient_role")
        return user

    return dep


require_admin = require_roles(Role.admin)
require_writer = require_roles(Role.admin, Role.investigator)
