"""Investigations, data points, posts, media, sources, events and dashboard."""
from __future__ import annotations

import secrets
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import (
    Classification,
    CollectionEvent,
    Confidence,
    DataPoint,
    Investigation,
    MediaItem,
    Post,
    Role,
    Source,
    SourceType,
    User,
    Verification,
    utcnow,
)
from ..schemas import (
    AddUrlsIn,
    DataPointCreate,
    DataPointOut,
    DataPointReview,
    EventOut,
    InvestigationCreate,
    InvestigationOut,
    InvestigationSummary,
    InvestigationUpdate,
    MediaOut,
    PostOut,
    SourceOut,
)
from ..services import jobs, verification
from ..services.app_config import general_settings
from ..services.audit import audit
from ..services.engine import regroup_media
from ..services.media import MediaError, analyse_image, store_bytes
from ..services.retention import delete_investigation
from ..services.url_parser import InvalidTargetError, parse_target
from .deps import client_ip, current_user, require_writer

router = APIRouter(prefix="/api", tags=["investigations"])


def _get_inv(db: Session, inv_id: int) -> Investigation:
    inv = db.get(Investigation, inv_id)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation_not_found")
    return inv


def _can_modify(user: User, inv: Investigation) -> None:
    if user.role == Role.admin.value:
        return
    if user.role == Role.investigator.value and inv.created_by_id == user.id:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "not_owner")


def _counts(db: Session, inv_id: int) -> dict[str, int]:
    def c(model, *where):
        return db.scalar(select(func.count(model.id)).where(model.investigation_id == inv_id, *where)) or 0

    return {
        "data_points": c(DataPoint, DataPoint.availability == "available"),
        "contacts": c(DataPoint, DataPoint.category == "contact", DataPoint.availability == "available"),
        "posts": c(Post, Post.kind == "post"),
        "comments": c(Post, Post.kind == "comment"),
        "media": c(MediaItem),
        "sources": c(Source),
        "verified": c(DataPoint, DataPoint.verification_status == "verified", DataPoint.availability == "available"),
    }


def _summary(db: Session, inv: Investigation) -> InvestigationSummary:
    s = InvestigationSummary.model_validate(inv)
    s.counts = _counts(db, inv.id)
    s.created_by_username = inv.created_by.username if inv.created_by else ""
    return s


# ---------------- dashboard ----------------
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    by_status = dict(db.execute(select(Investigation.status, func.count(Investigation.id)).group_by(Investigation.status)).all())
    since = utcnow() - timedelta(days=30)
    recent = db.scalars(select(Investigation).order_by(Investigation.created_at.desc()).limit(8)).all()
    created = db.scalars(select(Investigation.created_at).where(Investigation.created_at >= since)).all()
    per_day = Counter(d.strftime("%Y-%m-%d") for d in created)
    days = [(since + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(30)]
    return {
        "totals": {
            "investigations": sum(by_status.values()),
            "data_points": db.scalar(select(func.count(DataPoint.id)).where(DataPoint.availability == "available")) or 0,
            "contacts": db.scalar(select(func.count(DataPoint.id)).where(DataPoint.category == "contact", DataPoint.availability == "available")) or 0,
            "posts": db.scalar(select(func.count(Post.id))) or 0,
            "media": db.scalar(select(func.count(MediaItem.id))) or 0,
            "sources": db.scalar(select(func.count(Source.id))) or 0,
        },
        "by_status": by_status,
        "last_30_days": [{"date": d, "count": per_day.get(d, 0)} for d in days],
        "recent": [_summary(db, i).model_dump(mode="json") for i in recent],
    }


# ---------------- investigations ----------------
@router.get("/investigations")
def list_investigations(
    q: str = Query("", max_length=200),
    status_filter: str = Query("", alias="status", pattern=r"^(|pending|running|completed|partial|failed)$"),
    mine: bool = False,
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    stmt = select(Investigation)
    if q:
        stmt = stmt.where(or_(
            Investigation.reference.icontains(q, autoescape=True), Investigation.title.icontains(q, autoescape=True),
            Investigation.target_input.icontains(q, autoescape=True), Investigation.identifier.icontains(q, autoescape=True),
        ))
    if status_filter:
        stmt = stmt.where(Investigation.status == status_filter)
    if mine:
        stmt = stmt.where(Investigation.created_by_id == user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Investigation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [_summary(db, i).model_dump(mode="json") for i in rows]}


@router.post("/investigations", response_model=InvestigationSummary, status_code=201)
def create_investigation(body: InvestigationCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_writer)) -> InvestigationSummary:
    try:
        t = parse_target(body.target, body.target_type)
    except InvalidTargetError as e:
        raise HTTPException(422, {"code": e.code, "message": "invalid_target"}) from e
    ref = f"INV-{utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}"
    inv = Investigation(
        reference=ref, title=body.title or t.identifier, target_input=body.target.strip(), target_type=t.target_type,
        normalized_url=t.normalized_url, identifier=t.identifier,
        object_type="page" if t.hint == "page" else "user" if t.hint == "profile" and t.target_type == "authorized_account" else "unknown",
        purpose=body.purpose, legal_basis=body.legal_basis, notes=body.notes, options=body.options.model_dump(),
        extra_urls=body.extra_urls, created_by_id=user.id,
    )
    db.add(inv)
    db.commit()
    audit(db, "investigation_created", user, "investigation", inv.reference, client_ip(request), details={"target": inv.target_input, "purpose": inv.purpose[:200]})
    if body.start:
        jobs.submit(inv.id)
        db.refresh(inv)
    return _summary(db, inv)


@router.get("/investigations/{inv_id}", response_model=InvestigationSummary)
def get_investigation(inv_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> InvestigationSummary:
    return _summary(db, _get_inv(db, inv_id))


@router.patch("/investigations/{inv_id}", response_model=InvestigationOut)
def update_investigation(inv_id: int, body: InvestigationUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_writer)) -> Investigation:
    inv = _get_inv(db, inv_id)
    _can_modify(user, inv)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(inv, k, v)
    db.commit()
    audit(db, "investigation_updated", user, "investigation", inv.reference, client_ip(request), details=body.model_dump(exclude_none=True))
    return inv


@router.delete("/investigations/{inv_id}", status_code=204)
def remove_investigation(inv_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_writer)) -> None:
    inv = _get_inv(db, inv_id)
    _can_modify(user, inv)
    if inv.status == "running":
        raise HTTPException(409, "investigation_running")
    ref = inv.reference
    delete_investigation(db, inv)
    audit(db, "investigation_deleted", user, "investigation", ref, client_ip(request))


@router.post("/investigations/{inv_id}/run", response_model=InvestigationSummary)
def rerun(inv_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_writer)) -> InvestigationSummary:
    inv = _get_inv(db, inv_id)
    _can_modify(user, inv)
    if inv.status == "running" or jobs.is_running(inv.id):
        raise HTTPException(409, "investigation_running")
    inv.status = "pending"
    db.commit()
    audit(db, "investigation_run", user, "investigation", inv.reference, client_ip(request))
    jobs.submit(inv.id)
    db.refresh(inv)
    return _summary(db, inv)


@router.post("/investigations/{inv_id}/urls", response_model=InvestigationSummary)
def add_urls(inv_id: int, body: AddUrlsIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require_writer)) -> InvestigationSummary:
    inv = _get_inv(db, inv_id)
    _can_modify(user, inv)
    merged = list(dict.fromkeys([*(inv.extra_urls or []), *body.urls]))[:50]
    inv.extra_urls = merged
    db.commit()
    audit(db, "investigation_urls_added", user, "investigation", inv.reference, client_ip(request), details={"urls": body.urls})
    if body.run and inv.status != "running":
        jobs.submit(inv.id)
        db.refresh(inv)
    return _summary(db, inv)


# ---------------- data points ----------------
@router.get("/investigations/{inv_id}/datapoints", response_model=list[DataPointOut])
def list_datapoints(inv_id: int, category: str = Query("", pattern=r"^(|profile|contact|business|identifier|link|observation)$"), db: Session = Depends(get_db), user: User = Depends(current_user)):
    _get_inv(db, inv_id)
    stmt = select(DataPoint).where(DataPoint.investigation_id == inv_id)
    if category:
        stmt = stmt.where(DataPoint.category == category)
    return db.scalars(stmt.order_by(DataPoint.category, DataPoint.field, DataPoint.id)).all()


@router.post("/investigations/{inv_id}/datapoints", response_model=DataPointOut, status_code=201)
def add_manual_datapoint(inv_id: int, body: DataPointCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_writer)) -> DataPoint:
    inv = _get_inv(db, inv_id)
    _can_modify(user, inv)
    dp = DataPoint(
        investigation_id=inv.id, category=body.category, field=body.field, value=body.value, source_url=body.source_url,
        source_type=SourceType.manual.value, extraction_method="manual", notes=body.notes, classification=body.classification,
        verification_status=Verification.unverified.value, confidence=Confidence.low.value,
    )
    db.add(dp)
    db.commit()
    verification.recompute(db, inv.id)
    db.refresh(dp)
    audit(db, "datapoint_added_manual", user, "investigation", inv.reference, client_ip(request), details={"field": body.field})
    return dp


@router.patch("/investigations/{inv_id}/datapoints/{dp_id}/review", response_model=DataPointOut)
def review_datapoint(inv_id: int, dp_id: int, body: DataPointReview, request: Request, db: Session = Depends(get_db), user: User = Depends(require_writer)) -> DataPoint:
    inv = _get_inv(db, inv_id)
    _can_modify(user, inv)
    dp = db.get(DataPoint, dp_id)
    if dp is None or dp.investigation_id != inv.id:
        raise HTTPException(404, "datapoint_not_found")
    before = {"verification_status": dp.verification_status, "confidence": dp.confidence}
    dp.verification_status, dp.confidence = body.verification_status, body.confidence
    if dp.classification != Classification.analytical_observation.value:
        dp.classification = Classification.fact.value if body.verification_status == "verified" else Classification.unverified.value
    dp.manually_reviewed = True
    stamp = f"[{utcnow():%Y-%m-%d %H:%M} {user.username}] {body.notes}".strip()
    dp.notes = (dp.notes + "\n" + stamp).strip()[:2000]
    db.commit()
    audit(db, "datapoint_reviewed", user, "investigation", inv.reference, client_ip(request), details={"datapoint": dp.id, "before": before, "after": body.model_dump()})
    return dp


@router.delete("/investigations/{inv_id}/datapoints/{dp_id}", status_code=204)
def delete_manual_datapoint(inv_id: int, dp_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_writer)) -> None:
    inv = _get_inv(db, inv_id)
    _can_modify(user, inv)
    dp = db.get(DataPoint, dp_id)
    if dp is None or dp.investigation_id != inv.id:
        raise HTTPException(404, "datapoint_not_found")
    if dp.source_type != SourceType.manual.value:
        raise HTTPException(409, "only_manual_datapoints_can_be_deleted")
    db.delete(dp)
    db.commit()
    verification.recompute(db, inv.id)
    audit(db, "datapoint_deleted", user, "investigation", inv.reference, client_ip(request), details={"datapoint": dp_id})


# ---------------- posts ----------------
@router.get("/investigations/{inv_id}/posts")
def list_posts(
    inv_id: int,
    q: str = Query("", max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    kind: str = Query("", pattern=r"^(|post|comment)$"),
    order: str = Query("desc", pattern=r"^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    _get_inv(db, inv_id)
    stmt = select(Post).where(Post.investigation_id == inv_id)
    if q:
        terms = [t for t in q.split() if t][:8]
        for t in terms:
            stmt = stmt.where(or_(Post.message.icontains(t, autoescape=True), Post.shared_link.icontains(t, autoescape=True)))
    if date_from:
        stmt = stmt.where(Post.created_time >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(Post.created_time <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if kind:
        stmt = stmt.where(Post.kind == kind)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = Post.created_time.asc() if order == "asc" else Post.created_time.desc()
    rows = db.scalars(stmt.order_by(col, Post.id).offset(offset).limit(limit)).all()
    return {"total": total, "items": [PostOut.model_validate(p).model_dump(mode="json") for p in rows]}


@router.get("/investigations/{inv_id}/timeline")
def timeline(inv_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    _get_inv(db, inv_id)
    times = db.scalars(select(Post.created_time).where(Post.investigation_id == inv_id, Post.kind == "post", Post.created_time.is_not(None))).all()
    months = Counter(t.strftime("%Y-%m") for t in times)
    weekdays = Counter(t.strftime("%a") for t in times)
    hours = Counter(t.hour for t in times)
    return {
        "months": [{"month": k, "count": v} for k, v in sorted(months.items())],
        "weekdays": dict(weekdays),
        "hours_utc": {str(h): hours.get(h, 0) for h in range(24)},
        "first": min(times).isoformat() if times else None,
        "last": max(times).isoformat() if times else None,
    }


# ---------------- media ----------------
@router.get("/investigations/{inv_id}/media", response_model=list[MediaOut])
def list_media(inv_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _get_inv(db, inv_id)
    return db.scalars(select(MediaItem).where(MediaItem.investigation_id == inv_id).order_by(MediaItem.duplicate_group.is_(None), MediaItem.duplicate_group, MediaItem.id)).all()


@router.get("/investigations/{inv_id}/media/{media_id}/file")
def media_file(inv_id: int, media_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(MediaItem, media_id)
    if m is None or m.investigation_id != inv_id or not m.local_path:
        raise HTTPException(404, "media_not_found")
    root = get_settings().media_dir.resolve()
    path = (root / m.local_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "media_not_found")
    return FileResponse(path, media_type=m.mime_type or "application/octet-stream", headers={"Content-Disposition": f'inline; filename="{Path(m.local_path).name}"', "Cache-Control": "private, max-age=3600"})


@router.post("/investigations/{inv_id}/media/upload", response_model=MediaOut, status_code=201)
async def upload_media(inv_id: int, request: Request, file: UploadFile = File(...), caption: str = Query("", max_length=500), source_url: str = Query("", max_length=1000), db: Session = Depends(get_db), user: User = Depends(require_writer)) -> MediaItem:
    inv = _get_inv(db, inv_id)
    _can_modify(user, inv)
    limit = get_settings().media_max_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "file_too_large")
    try:
        info = analyse_image(data)
    except MediaError as e:
        raise HTTPException(422, str(e)) from e
    if source_url and not source_url.lower().startswith(("http://", "https://")):
        raise HTTPException(422, "source_url_must_be_http_url")
    m = MediaItem(
        investigation_id=inv.id, kind="uploaded", source_url=source_url, source_type=SourceType.investigator_upload.value, caption=caption,
        local_path=store_bytes(get_settings().media_dir, inv.id, info, data), mime_type=info.mime_type, size_bytes=len(data), width=info.width,
        height=info.height, sha256=info.sha256, phash=info.phash, dhash=info.dhash, metadata_json={**info.metadata, "original_filename": (file.filename or "")[:200]}, status="stored",
    )
    db.add(m)
    db.commit()
    regroup_media(db, inv.id, int(general_settings(db).get("duplicate_threshold", 8)))
    db.refresh(m)
    audit(db, "media_uploaded", user, "investigation", inv.reference, client_ip(request), details={"sha256": info.sha256})
    return m


# ---------------- sources / events ----------------
@router.get("/investigations/{inv_id}/sources")
def list_sources(inv_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    _get_inv(db, inv_id)
    sources = db.scalars(select(Source).where(Source.investigation_id == inv_id).order_by(Source.id)).all()
    points = db.scalars(select(DataPoint).where(DataPoint.investigation_id == inv_id, DataPoint.availability == "available")).all()
    usage = Counter()
    for p in points:
        for s in sources:
            if p.source_url and (p.source_url == s.final_url or p.source_url == s.url):
                usage[s.id] += 1
    stats = Counter(p.verification_status for p in points)
    conf = Counter(p.confidence for p in points)
    return {
        "items": [{**SourceOut.model_validate(s).model_dump(mode="json"), "data_points": usage.get(s.id, 0)} for s in sources],
        "verification": dict(stats),
        "confidence": dict(conf),
    }


@router.get("/investigations/{inv_id}/events", response_model=list[EventOut])
def list_events(inv_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _get_inv(db, inv_id)
    return db.scalars(select(CollectionEvent).where(CollectionEvent.investigation_id == inv_id).order_by(CollectionEvent.id)).all()
