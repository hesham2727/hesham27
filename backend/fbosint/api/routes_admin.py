"""User management, audit log, backups and retention (admin only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AuditLog, User
from ..schemas import AuditOut, UserCreate, UserOut, UserUpdate
from ..security.passwords import hash_password, password_problems
from ..security.sessions import revoke_user_sessions
from ..services import backup, retention
from ..services.audit import audit
from .deps import client_ip, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> User:
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "username_taken")
    problems = password_problems(body.password, body.username)
    if problems:
        raise HTTPException(422, problems)
    u = User(username=body.username, full_name=body.full_name, password_hash=hash_password(body.password), role=body.role, language=body.language)
    db.add(u)
    db.commit()
    audit(db, "user_created", admin, "user", u.id, client_ip(request), details={"username": u.username, "role": u.role})
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user_not_found")
    changes = body.model_dump(exclude_none=True)
    if u.id == admin.id and (changes.get("role", "admin") != "admin" or changes.get("is_active") is False):
        raise HTTPException(409, "cannot_demote_or_disable_self")
    if "password" in changes:
        problems = password_problems(changes["password"], u.username)
        if problems:
            raise HTTPException(422, problems)
        u.password_hash = hash_password(changes.pop("password"))
        u.failed_logins, u.locked_until = 0, None
        revoke_user_sessions(db, u.id)
        changes["password"] = "changed"
    for k in ("full_name", "role", "is_active", "language"):
        if k in changes:
            setattr(u, k, changes[k])
    if changes.get("is_active") is False or "role" in changes:
        revoke_user_sessions(db, u.id)
    db.commit()
    audit(db, "user_updated", admin, "user", u.id, client_ip(request), details=changes)
    return u


@router.get("/audit")
def audit_log(
    action: str = Query("", max_length=64),
    username: str = Query("", max_length=64),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if username:
        stmt = stmt.where(AuditLog.username == username)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": [AuditOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.get("/backups")
def backups(admin: User = Depends(require_admin)) -> list[dict]:
    return backup.list_backups()


@router.post("/backups", status_code=201)
def make_backup(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    path = backup.create_backup(label="manual")
    audit(db, "backup_created", admin, "backup", path.name, client_ip(request))
    return {"name": path.name, "size_bytes": path.stat().st_size}


@router.get("/backups/{name}")
def download_backup(name: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    root = get_settings().backup_dir.resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file() or not name.startswith("fbosint-backup-"):
        raise HTTPException(404, "backup_not_found")
    audit(db, "backup_downloaded", admin, "backup", name, client_ip(request))
    return FileResponse(path, media_type="application/zip", filename=name)


@router.post("/retention/run")
def run_retention(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    n = retention.purge_expired(db)
    audit(db, "retention_run", admin, "system", "", client_ip(request), details={"deleted": n})
    return {"deleted": n}
