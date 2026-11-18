"""Number validation, investigations, public-source records and customers."""
from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, require_admin
from ..models import (
    Customer,
    DataSource,
    Investigation,
    LocationInvitation,
    LocationRecord,
    NumberCheck,
    SourceRecord,
    User,
    utcnow,
)
from ..schemas import (
    CustomerIn,
    CustomerOut,
    CustomerUpdate,
    DataSourceIn,
    DataSourceOut,
    InvestigationIn,
    InvestigationOut,
    InvestigationUpdate,
    NumberCheckOut,
    SourceRecordIn,
    SourceRecordOut,
    ValidateIn,
)
from ..services.audit import audit
from ..services.phone import analyze_number, to_e164_or_empty
from .locations import invitation_out, location_out

router = APIRouter(prefix="/api", tags=["investigations"])


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ------------------------------------------------------------------ numbers
def check_out(c: NumberCheck) -> NumberCheckOut:
    out = NumberCheckOut.model_validate(c)
    out.checked_by_username = c.checker.username if c.checker else ""
    return out


@router.post("/numbers/validate", response_model=NumberCheckOut)
def validate_number(body: ValidateIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.investigation_id is not None and db.get(Investigation, body.investigation_id) is None:
        raise HTTPException(404, "التحقيق غير موجود")
    result = analyze_number(body.number, body.region.upper())
    check = NumberCheck(
        raw_input=body.number,
        e164=result["e164"],
        is_valid=result["is_valid"],
        result=result,
        investigation_id=body.investigation_id,
        checked_by=user.id,
    )
    db.add(check)
    db.commit()
    audit(db, "number.validate", user=user, request=request, entity_type="number_check", entity_id=check.id,
          details={"e164": result["e164"], "valid": result["is_valid"]})
    return check_out(check)


@router.get("/numbers/checks", response_model=list[NumberCheckOut])
def list_checks(
    q: str = "",
    limit: int = Query(100, ge=1, le=1000),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(NumberCheck)
    if q:
        query = query.filter(or_(NumberCheck.raw_input.like(_like(q), escape="\\"), NumberCheck.e164.like(_like(q), escape="\\")))
    return [check_out(c) for c in query.order_by(NumberCheck.checked_at.desc()).limit(limit).all()]


# ------------------------------------------------------------------ investigations
def inv_out(inv: Investigation) -> InvestigationOut:
    out = InvestigationOut.model_validate(inv)
    out.customer_name = inv.customer.full_name if inv.customer else ""
    out.created_by_username = inv.creator.username if inv.creator else ""
    return out


def _get_inv(db: Session, inv_id: int) -> Investigation:
    inv = db.get(Investigation, inv_id)
    if inv is None:
        raise HTTPException(404, "التحقيق غير موجود")
    return inv


def _new_ref(db: Session) -> str:
    while True:
        ref = f"INV-{datetime.now():%Y%m%d}-{secrets.token_hex(2).upper()}"
        if not db.query(Investigation).filter(Investigation.ref_code == ref).first():
            return ref


@router.get("/investigations", response_model=list[InvestigationOut])
def list_investigations(
    q: str = "",
    status: str = "",
    customer_id: int | None = None,
    limit: int = Query(200, ge=1, le=2000),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Investigation)
    if q:
        like = _like(q)
        query = query.filter(
            or_(
                Investigation.ref_code.like(like, escape="\\"),
                Investigation.title.like(like, escape="\\"),
                Investigation.phone_raw.like(like, escape="\\"),
                Investigation.phone_e164.like(like, escape="\\"),
            )
        )
    if status in ("open", "closed"):
        query = query.filter(Investigation.status == status)
    if customer_id:
        query = query.filter(Investigation.customer_id == customer_id)
    return [inv_out(i) for i in query.order_by(Investigation.created_at.desc()).limit(limit).all()]


@router.post("/investigations", response_model=InvestigationOut, status_code=201)
def create_investigation(body: InvestigationIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.customer_id is not None and db.get(Customer, body.customer_id) is None:
        raise HTTPException(404, "العميل غير موجود")
    result = analyze_number(body.phone)
    inv = Investigation(
        ref_code=_new_ref(db),
        phone_raw=body.phone,
        phone_e164=result["e164"],
        title=body.title,
        purpose=body.purpose,
        customer_id=body.customer_id,
        notes=body.notes,
        validation=result,
        created_by=user.id,
    )
    db.add(inv)
    db.flush()
    db.add(NumberCheck(raw_input=body.phone, e164=result["e164"], is_valid=result["is_valid"], result=result,
                       investigation_id=inv.id, checked_by=user.id))
    db.commit()
    audit(db, "investigation.create", user=user, request=request, entity_type="investigation", entity_id=inv.id,
          details={"ref": inv.ref_code, "e164": inv.phone_e164})
    return inv_out(inv)


@router.get("/investigations/{inv_id}")
def get_investigation(inv_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _get_inv(db, inv_id)
    sources = db.query(SourceRecord).filter(SourceRecord.investigation_id == inv.id).order_by(SourceRecord.observed_at.desc()).all()
    locs = db.query(LocationRecord).filter(LocationRecord.investigation_id == inv.id).order_by(LocationRecord.collected_at.desc()).all()
    invites = db.query(LocationInvitation).filter(LocationInvitation.investigation_id == inv.id).order_by(LocationInvitation.created_at.desc()).all()
    checks = db.query(NumberCheck).filter(NumberCheck.investigation_id == inv.id).order_by(NumberCheck.checked_at.desc()).all()
    audit(db, "investigation.view", user=user, request=request, entity_type="investigation", entity_id=inv.id)
    return {
        "investigation": inv_out(inv),
        "sources": [source_out(s) for s in sources],
        "locations": [location_out(l) for l in locs],
        "invitations": [invitation_out(i) for i in invites],
        "checks": [check_out(c) for c in checks],
    }


@router.patch("/investigations/{inv_id}", response_model=InvestigationOut)
def update_investigation(inv_id: int, body: InvestigationUpdate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _get_inv(db, inv_id)
    changes = body.model_dump(exclude_unset=True)
    if "customer_id" in changes and changes["customer_id"] is not None and db.get(Customer, changes["customer_id"]) is None:
        raise HTTPException(404, "العميل غير موجود")
    for k, v in changes.items():
        setattr(inv, k, v)
    if changes.get("status") == "closed" and inv.closed_at is None:
        inv.closed_at = utcnow()
    elif changes.get("status") == "open":
        inv.closed_at = None
    db.commit()
    audit(db, "investigation.update", user=user, request=request, entity_type="investigation", entity_id=inv.id,
          details={k: (v if k != "notes" else "…") for k, v in changes.items()})
    return inv_out(inv)


@router.delete("/investigations/{inv_id}", status_code=204)
def delete_investigation(inv_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    inv = _get_inv(db, inv_id)
    ref = inv.ref_code
    db.delete(inv)
    db.commit()
    audit(db, "investigation.delete", user=admin, request=request, entity_type="investigation", entity_id=inv_id, details={"ref": ref})


# ------------------------------------------------------------------ data sources & records
def source_out(s: SourceRecord) -> SourceRecordOut:
    out = SourceRecordOut.model_validate(s)
    out.created_by_username = s.creator.username if s.creator else ""
    return out


@router.get("/data-sources", response_model=list[DataSourceOut])
def list_data_sources(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(DataSource).order_by(DataSource.is_builtin.desc(), DataSource.name).all()


@router.post("/data-sources", response_model=DataSourceOut, status_code=201)
def create_data_source(body: DataSourceIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(DataSource).filter(DataSource.key == body.key).first():
        raise HTTPException(409, "المعرّف مستخدم")
    ds = DataSource(**body.model_dump(), access_method="manual", is_builtin=False)
    db.add(ds)
    db.commit()
    audit(db, "data_source.create", user=admin, request=request, entity_type="data_source", entity_id=ds.id)
    return ds


@router.patch("/data-sources/{ds_id}", response_model=DataSourceOut)
def toggle_data_source(ds_id: int, enabled: bool, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ds = db.get(DataSource, ds_id)
    if ds is None:
        raise HTTPException(404, "المصدر غير موجود")
    ds.enabled = enabled
    db.commit()
    audit(db, "data_source.toggle", user=admin, request=request, entity_type="data_source", entity_id=ds.id, details={"enabled": enabled})
    return ds


@router.post("/investigations/{inv_id}/sources", response_model=SourceRecordOut, status_code=201)
def add_source_record(inv_id: int, body: SourceRecordIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = _get_inv(db, inv_id)
    if body.data_source_id is not None and db.get(DataSource, body.data_source_id) is None:
        raise HTTPException(404, "المصدر غير موجود في الدليل")
    if body.observed_at > utcnow():
        raise HTTPException(422, "تاريخ الاطلاع لا يمكن أن يكون في المستقبل")
    rec = SourceRecord(investigation_id=inv.id, created_by=user.id, **body.model_dump())
    db.add(rec)
    db.commit()
    audit(db, "source_record.create", user=user, request=request, entity_type="investigation", entity_id=inv.id,
          details={"source_record_id": rec.id, "source": rec.source_name})
    return source_out(rec)


@router.delete("/sources/{rec_id}", status_code=204)
def delete_source_record(rec_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rec = db.get(SourceRecord, rec_id)
    if rec is None:
        raise HTTPException(404, "السجل غير موجود")
    if user.role != "admin" and rec.created_by != user.id:
        raise HTTPException(403, "يمكن حذف السجل بواسطة منشئه أو المدير فقط")
    inv_id = rec.investigation_id
    db.delete(rec)
    db.commit()
    audit(db, "source_record.delete", user=user, request=request, entity_type="investigation", entity_id=inv_id,
          details={"source_record_id": rec_id})


# ------------------------------------------------------------------ customers
@router.get("/customers", response_model=list[CustomerOut])
def list_customers(q: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(Customer)
    if q:
        like = _like(q)
        query = query.filter(or_(Customer.full_name.like(like, escape="\\"), Customer.phone_e164.like(like, escape="\\")))
    return query.order_by(Customer.full_name).limit(1000).all()


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = body.model_dump()
    phone = data.pop("phone")
    e164 = to_e164_or_empty(phone) if phone else ""
    if phone and not e164:
        raise HTTPException(422, "رقم هاتف العميل غير صالح")
    c = Customer(phone_e164=e164, created_by=user.id, **data)
    db.add(c)
    db.commit()
    audit(db, "customer.create", user=user, request=request, entity_type="customer", entity_id=c.id)
    return c


@router.get("/customers/{cid}")
def get_customer(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if c is None:
        raise HTTPException(404, "العميل غير موجود")
    invs = db.query(Investigation).filter(Investigation.customer_id == cid).order_by(Investigation.created_at.desc()).all()
    locs = db.query(LocationRecord).filter(LocationRecord.customer_id == cid).order_by(LocationRecord.collected_at.desc()).all()
    invites = db.query(LocationInvitation).filter(LocationInvitation.customer_id == cid).order_by(LocationInvitation.created_at.desc()).all()
    audit(db, "customer.view", user=user, request=request, entity_type="customer", entity_id=cid)
    return {
        "customer": CustomerOut.model_validate(c),
        "investigations": [inv_out(i) for i in invs],
        "locations": [location_out(l) for l in locs],
        "invitations": [invitation_out(i) for i in invites],
    }


@router.patch("/customers/{cid}", response_model=CustomerOut)
def update_customer(cid: int, body: CustomerUpdate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if c is None:
        raise HTTPException(404, "العميل غير موجود")
    changes = body.model_dump(exclude_unset=True)
    if "phone" in changes:
        phone = changes.pop("phone") or ""
        e164 = to_e164_or_empty(phone) if phone else ""
        if phone and not e164:
            raise HTTPException(422, "رقم هاتف العميل غير صالح")
        c.phone_e164 = e164
    for k, v in changes.items():
        if v is not None:
            setattr(c, k, v)
    db.commit()
    audit(db, "customer.update", user=user, request=request, entity_type="customer", entity_id=c.id, details={"fields": list(body.model_dump(exclude_unset=True))})
    return c


@router.delete("/customers/{cid}", status_code=204)
def delete_customer(cid: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if c is None:
        raise HTTPException(404, "العميل غير موجود")
    db.delete(c)
    db.commit()
    audit(db, "customer.delete", user=admin, request=request, entity_type="customer", entity_id=cid)
