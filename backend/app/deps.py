from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuthSession, User, utcnow
from .security import token_hash

SESSION_COOKIE = "tahqiq_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "tahqiq"


def csrf_guard(request: Request) -> None:
    """Mutating API calls must carry a custom header.

    Browsers cannot attach custom headers to cross-site requests without a
    CORS pre-flight, which this API never allows. Combined with SameSite=Strict
    cookies this blocks CSRF.
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get(CSRF_HEADER, "").lower() != CSRF_VALUE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "طلب مرفوض (CSRF)")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "يجب تسجيل الدخول")
    sess = db.query(AuthSession).filter(AuthSession.token_hash == token_hash(token)).first()
    if sess is None or sess.expires_at <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "انتهت الجلسة، سجّل الدخول مجدداً")
    user = sess.user
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "الحساب موقوف")
    csrf_guard(request)
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "هذه العملية متاحة لمدير النظام فقط")
    return user
