"""Login, logout, first-run setup, current user."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Role, User, utcnow
from ..schemas import LoginIn, LoginOut, PasswordChange, PreferencesIn, SetupIn, UserOut
from ..security.passwords import DUMMY_HASH, hash_password, password_problems, verify_password
from ..security.sessions import create_session, revoke_session, revoke_user_sessions
from ..services.audit import audit
from .deps import CSRF_COOKIE, SESSION_COOKIE, AuthContext, client_ip, current_user, get_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    max_age = s.session_ttl_hours * 3600
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=s.secure_cookies, samesite="strict", path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=s.secure_cookies, samesite="strict", path="/")


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)) -> dict:
    count = db.scalar(select(func.count(User.id))) or 0
    return {"needs_setup": count == 0}


@router.post("/setup", response_model=UserOut, status_code=201)
def first_run_setup(body: SetupIn, request: Request, db: Session = Depends(get_db)) -> User:
    """Create the first administrator. Only allowed while no user exists."""
    if (db.scalar(select(func.count(User.id))) or 0) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "setup_already_completed")
    problems = password_problems(body.password, body.username)
    if problems:
        raise HTTPException(422, problems)
    user = User(username=body.username, full_name=body.full_name, password_hash=hash_password(body.password), role=Role.admin.value, language=body.language)
    db.add(user)
    db.commit()
    audit(db, "setup_admin_created", user, "user", user.id, client_ip(request))
    return user


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginOut:
    s = get_settings()
    ip = client_ip(request)
    user = db.scalar(select(User).where(User.username == body.username))
    now = utcnow()
    if user is None:
        verify_password(body.password, DUMMY_HASH)  # constant-ish timing
        audit(db, "login_failed", None, "user", "", ip, False, {"reason": "unknown_user"}, username=body.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    if user.locked_until and user.locked_until > now:
        audit(db, "login_blocked_locked", user, "user", user.id, ip, False)
        raise HTTPException(status.HTTP_423_LOCKED, "account_locked")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        user.failed_logins += 1
        if user.failed_logins >= s.login_max_failures:
            user.locked_until = now + timedelta(minutes=s.login_lockout_minutes)
            user.failed_logins = 0
        db.commit()
        audit(db, "login_failed", user, "user", user.id, ip, False, {"reason": "bad_password_or_inactive"})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    token, sess = create_session(db, user, body.client, ip, request.headers.get("User-Agent", ""))
    if body.client == "web":
        _set_cookies(response, token, sess.csrf_token)
    audit(db, "login_success", user, "user", user.id, ip, details={"client": body.client})
    return LoginOut(user=UserOut.model_validate(user), csrf_token=sess.csrf_token, expires_at=sess.expires_at, token=token if body.client == "desktop" else None)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> Response:
    sess = db.merge(ctx.session)
    revoke_session(db, sess)
    audit(db, "logout", ctx.user, "user", ctx.user.id, client_ip(request))
    response.status_code = 204
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.get("/csrf")
def csrf(ctx: AuthContext = Depends(get_auth)) -> dict:
    return {"csrf_token": ctx.session.csrf_token}


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChange, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    user = db.merge(user)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current_password_incorrect")
    problems = password_problems(body.new_password, user.username)
    if problems:
        raise HTTPException(422, problems)
    user.password_hash = hash_password(body.new_password)
    db.commit()
    revoke_user_sessions(db, user.id)
    audit(db, "password_changed", user, "user", user.id, client_ip(request))
    return Response(status_code=204)


@router.put("/preferences", response_model=UserOut)
def preferences(body: PreferencesIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    user = db.merge(user)
    user.language = body.language
    db.commit()
    return user
