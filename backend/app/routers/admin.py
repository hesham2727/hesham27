"""System status, settings, audit log, retention and report exports."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..db import get_db
from ..deps import current_user, require_admin
from ..models import AuditLog, Investigation, LocationInvitation, LocationRecord, NumberCheck, SourceRecord, User
from ..schemas import AuditOut
from ..services import app_settings
from ..services.audit import audit
from ..services.reports import investigation_pdf, investigations_xlsx
from ..services.retention import run_retention

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "version": __version__}


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)):
    """Unauthenticated: tells the UI whether first-run setup is required."""
    return {
        "version": __version__,
        "mode": get_settings().mode,
        "setup_required": db.query(User).count() == 0,
    }


@router.get("/settings")
def get_app_settings(_: User = Depends(current_user), db: Session = Depends(get_db)):
    data = app_settings.load_all(db)
    data["internet_mode"] = app_settings.internet_mode_status(db)
    data["public_base_url_locked"] = bool(get_settings().public_base_url)
    return data


_ALLOWED_KEYS = {"organization_name", "public_base_url", "invitation_default_hours", "map", "adapters", "retention"}


@router.put("/settings")
def put_app_settings(request: Request, payload: dict = Body(...), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    updates = {k: v for k, v in payload.items() if k in _ALLOWED_KEYS}
    if "public_base_url" in updates:
        url = str(updates["public_base_url"] or "").strip().rstrip("/")
        if url:
            ok, message = app_settings.check_public_url(url)
            if not ok:
                raise HTTPException(422, message)
        updates["public_base_url"] = url
    if "map" in updates:
        tile = str(updates["map"].get("tile_url", app_settings.OSM_TILE_URL))
        if not tile.startswith("https://") or "{z}" not in tile or "{x}" not in tile or "{y}" not in tile:
            raise HTTPException(422, "رابط البلاطات يجب أن يكون https ويحتوي على {z} و{x} و{y}")
    if "retention" in updates:
        for k, v in updates["retention"].items():
            if not isinstance(v, int) or v < 0 or v > 3650:
                raise HTTPException(422, f"قيمة غير صالحة لمدة الاحتفاظ: {k}")
    if "invitation_default_hours" in updates:
        h = updates["invitation_default_hours"]
        if not isinstance(h, int) or not 1 <= h <= 168:
            raise HTTPException(422, "مدة صلاحية الدعوة بين 1 و168 ساعة")
    if "adapters" in updates:
        known = app_settings.DEFAULTS["adapters"]
        for name, cfg in updates["adapters"].items():
            if name not in known or not isinstance(cfg, dict):
                raise HTTPException(422, f"محوّل غير معروف: {name}")
            # endpoints are fixed; only the enabled flag is editable
            updates["adapters"][name] = {"enabled": bool(cfg.get("enabled"))}
    saved = app_settings.save(db, updates)
    audit(db, "settings.update", user=admin, request=request, details={"keys": sorted(updates)})
    saved["internet_mode"] = app_settings.internet_mode_status(db)
    saved["public_base_url_locked"] = bool(get_settings().public_base_url)
    return saved


@router.post("/retention/run")
def retention_now(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return run_retention(db, user=admin, request=request)


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    action: str = "",
    username: str = "",
    entity_type: str = "",
    entity_id: str = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action.startswith(action))
    if username:
        q = q.filter(AuditLog.username == username)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if date_from:
        q = q.filter(AuditLog.at >= date_from)
    if date_to:
        q = q.filter(AuditLog.at <= date_to)
    return q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()


# ------------------------------------------------------------------ reports
def _xlsx(content: bytes, name: str) -> Response:
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/reports/investigations/{inv_id}.pdf")
def report_pdf(inv_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = db.get(Investigation, inv_id)
    if inv is None:
        raise HTTPException(404, "التحقيق غير موجود")
    sources = db.query(SourceRecord).filter(SourceRecord.investigation_id == inv_id).order_by(SourceRecord.observed_at).all()
    locs = db.query(LocationRecord).filter(LocationRecord.investigation_id == inv_id).order_by(LocationRecord.collected_at.desc()).all()
    invites = db.query(LocationInvitation).filter(LocationInvitation.investigation_id == inv_id).order_by(LocationInvitation.created_at).all()
    checks = db.query(NumberCheck).filter(NumberCheck.investigation_id == inv_id).order_by(NumberCheck.checked_at).all()
    pdf = investigation_pdf(inv, sources, locs, invites, checks, generated_by=user.full_name or user.username)
    audit(db, "report.pdf", user=user, request=request, entity_type="investigation", entity_id=inv_id)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{inv.ref_code}.pdf"'})


@router.get("/reports/investigations/{inv_id}.xlsx")
def report_xlsx_one(inv_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = db.get(Investigation, inv_id)
    if inv is None:
        raise HTTPException(404, "التحقيق غير موجود")
    data = investigations_xlsx(
        [inv],
        db.query(SourceRecord).filter(SourceRecord.investigation_id == inv_id).all(),
        db.query(LocationRecord).filter(LocationRecord.investigation_id == inv_id).all(),
        db.query(NumberCheck).filter(NumberCheck.investigation_id == inv_id).all(),
    )
    audit(db, "report.xlsx", user=user, request=request, entity_type="investigation", entity_id=inv_id)
    return _xlsx(data, f"{inv.ref_code}.xlsx")


@router.get("/reports/investigations.xlsx")
def report_xlsx_all(request: Request, status: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Investigation)
    if status in ("open", "closed"):
        q = q.filter(Investigation.status == status)
    invs = q.order_by(Investigation.created_at.desc()).all()
    ids = [i.id for i in invs]
    data = investigations_xlsx(
        invs,
        db.query(SourceRecord).filter(SourceRecord.investigation_id.in_(ids)).all() if ids else [],
        db.query(LocationRecord).filter(LocationRecord.investigation_id.in_(ids)).all() if ids else [],
        db.query(NumberCheck).order_by(NumberCheck.checked_at.desc()).limit(5000).all(),
    )
    audit(db, "report.xlsx_all", user=user, request=request, details={"count": len(invs)})
    return _xlsx(data, f"investigations-{datetime.now():%Y%m%d}.xlsx")
