from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import SESSION_COOKIE, csrf_guard, current_user, require_admin
from ..models import AuthSession, User, utcnow
from ..schemas import ChangePasswordIn, LoginIn, SetupIn, UserCreate, UserOut, UserUpdate
from ..security import (
    LOCKOUT_MINUTES,
    LOCKOUT_THRESHOLD,
    client_ip,
    dummy_verify,
    hash_password,
    is_loopback,
    login_limiter,
    new_token,
    password_problems,
    token_hash,
    verify_password,
)
from ..services.audit import audit

router = APIRouter(prefix="/api", tags=["auth"])


def _secure_cookie(request: Request) -> bool:
    s = get_settings()
    if s.secure_cookies is not None:
        return s.secure_cookies
    if request.url.scheme == "https":
        return True
    return s.trust_proxy and request.headers.get("x-forwarded-proto", "").lower() == "https"


def _start_session(db: Session, user: User, request: Request, response: Response) -> None:
    token = new_token()
    hours = get_settings().session_hours
    db.add(
        AuthSession(
            token_hash=token_hash(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=hours),
            ip=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    user.last_login_at = utcnow()
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=hours * 3600,
        httponly=True,
        samesite="strict",
        secure=_secure_cookie(request),
        path="/",
    )


def _check_password(pw: str) -> None:
    problems = password_problems(pw)
    if problems:
        raise HTTPException(422, "؛ ".join(problems))


@router.post("/auth/setup", response_model=UserOut, dependencies=[Depends(csrf_guard)])
def setup(body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Create the first administrator. Only allowed when no user exists."""
    if db.query(User).count() > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "تم إعداد النظام مسبقاً")
    if not (is_loopback(request) or get_settings().allow_remote_setup):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "يجب إنشاء حساب المدير الأول من نفس الجهاز (localhost) أو باستخدام أمر create-admin.",
        )
    _check_password(body.password)
    user = User(username=body.username, full_name=body.full_name, password_hash=hash_password(body.password), role="admin")
    db.add(user)
    db.commit()
    audit(db, "auth.setup", user=user, request=request, entity_type="user", entity_id=user.id)
    _start_session(db, user, request, response)
    return user


@router.post("/auth/login", response_model=UserOut, dependencies=[Depends(csrf_guard)])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if not login_limiter.hit(f"ip:{ip}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "محاولات كثيرة، حاول لاحقاً")
    user = db.query(User).filter(User.username == body.username.strip()).first()
    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, "اسم المستخدم أو كلمة المرور غير صحيحة")
    if user is None:
        dummy_verify(body.password)
        audit(db, "auth.login_failed", request=request, details={"username": body.username[:64]})
        raise generic
    if user.locked_until and user.locked_until > utcnow():
        audit(db, "auth.login_locked", user=user, request=request)
        raise HTTPException(status.HTTP_423_LOCKED, f"الحساب مقفل مؤقتاً لمدة {LOCKOUT_MINUTES} دقيقة بسبب محاولات فاشلة")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        user.failed_logins += 1
        if user.failed_logins >= LOCKOUT_THRESHOLD:
            user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_logins = 0
        db.commit()
        audit(db, "auth.login_failed", user=user, request=request)
        raise generic
    _start_session(db, user, request, response)
    audit(db, "auth.login", user=user, request=request)
    return user


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE, "")
    db.query(AuthSession).filter(AuthSession.token_hash == token_hash(token)).delete()
    db.commit()
    audit(db, "auth.logout", user=user, request=request)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/auth/change-password", status_code=204)
def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "كلمة المرور الحالية غير صحيحة")
    _check_password(body.new_password)
    user.password_hash = hash_password(body.new_password)
    # Invalidate all other sessions.
    current = token_hash(request.cookies.get(SESSION_COOKIE, ""))
    db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.token_hash != current).delete()
    db.commit()
    audit(db, "auth.password_changed", user=user, request=request, entity_type="user", entity_id=user.id)
    return Response(status_code=204)


# ------------------------------------------------------------------ users (admin)
@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "اسم المستخدم مستخدم بالفعل")
    _check_password(body.password)
    user = User(username=body.username, full_name=body.full_name, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    audit(db, "user.create", user=admin, request=request, entity_type="user", entity_id=user.id, details={"role": user.role})
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "المستخدم غير موجود")
    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (changes.get("role") == "operator" or changes.get("is_active") is False):
        raise HTTPException(400, "لا يمكنك إلغاء صلاحيات حسابك أو إيقافه")
    if "password" in changes and changes["password"]:
        _check_password(changes["password"])
        user.password_hash = hash_password(changes.pop("password"))
        db.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
        changes["password_reset"] = True
    changes.pop("password", None)
    for k in ("full_name", "role", "is_active"):
        if k in changes:
            setattr(user, k, changes[k])
    if changes.get("is_active") is False:
        db.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
    db.commit()
    audit(db, "user.update", user=admin, request=request, entity_type="user", entity_id=user.id, details=changes)
    return user
