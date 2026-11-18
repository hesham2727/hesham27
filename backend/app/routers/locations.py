"""Consent-based location invitations and shared location records."""
from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Customer, Investigation, LocationInvitation, LocationRecord, User, utcnow
from ..schemas import InvitationCreated, InvitationIn, InvitationOut, LocationOut
from ..security import new_token, token_hash
from ..services.app_settings import internet_mode_status, load_all
from ..services.audit import audit
from ..services.geocoding import GeocodingUnavailable, reverse_geocode
from ..services.phone import CURRENT_LOCATION_UNAVAILABLE, CURRENT_LOCATION_UNAVAILABLE_AR, to_e164_or_empty
from ..services.timefmt import age_ar, local

router = APIRouter(prefix="/api", tags=["locations"])


def invitation_out(i: LocationInvitation) -> InvitationOut:
    return InvitationOut.model_validate(i)


def location_out(l: LocationRecord) -> LocationOut:
    out = LocationOut.model_validate(l)
    out.is_current = False  # a shared snapshot is never a current location
    out.label = f"موقع تاريخي – تم الجمع {local(l.collected_at)} بتوقيت القاهرة ({age_ar(l.collected_at)})"
    return out


@router.get("/internet-mode")
def get_internet_mode(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return internet_mode_status(db)


@router.post("/invitations", response_model=InvitationCreated, status_code=201)
def create_invitation(body: InvitationIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mode = internet_mode_status(db)
    if not mode["enabled"]:
        raise HTTPException(409, {"message": "دعوات العملاء الخارجية معطّلة: " + mode["message"], "steps": mode["steps"]})
    inv = db.get(Investigation, body.investigation_id) if body.investigation_id else None
    if body.investigation_id and inv is None:
        raise HTTPException(404, "التحقيق غير موجود")
    cust = db.get(Customer, body.customer_id) if body.customer_id else None
    if body.customer_id and cust is None:
        raise HTTPException(404, "العميل غير موجود")
    if inv is None and cust is None:
        raise HTTPException(422, "يجب ربط الدعوة بتحقيق أو عميل")
    if inv is not None and cust is None and inv.customer_id:
        cust = db.get(Customer, inv.customer_id)
    phone = to_e164_or_empty(body.phone) if body.phone else ""
    if body.phone and not phone:
        raise HTTPException(422, "رقم الهاتف غير صالح")
    phone = phone or (inv.phone_e164 if inv else "") or (cust.phone_e164 if cust else "")

    settings = load_all(db)
    token = new_token()
    invitation = LocationInvitation(
        token_hash=token_hash(token),
        investigation_id=inv.id if inv else None,
        customer_id=cust.id if cust else None,
        phone_e164=phone,
        purpose=body.purpose,
        requester_label=settings.get("organization_name") or "",
        created_by=user.id,
        expires_at=utcnow() + timedelta(hours=body.hours),
    )
    db.add(invitation)
    db.commit()

    link = f"{mode['public_base_url']}/p/{token}"
    org = settings.get("organization_name") or "فريق العمل"
    text = (
        f"مرحباً، {org} يطلب منك مشاركة موقعك مرة واحدة لغرض: {body.purpose}.\n"
        f"المشاركة اختيارية تماماً ويمكنك الرفض. الرابط صالح حتى {local(invitation.expires_at)} بتوقيت القاهرة:\n{link}"
    )
    manual = settings["adapters"]["manual_share"]["enabled"]
    digits = re.sub(r"\D", "", phone)
    out = InvitationCreated(
        **invitation_out(invitation).model_dump(),
        link=link,
        message_text=text,
        whatsapp_url=f"https://wa.me/{digits}?text={quote(text)}" if (manual and digits) else "",
        sms_uri=f"sms:{phone}?body={quote(text)}" if (manual and phone) else "",
    )
    audit(db, "invitation.create", user=user, request=request, entity_type="invitation", entity_id=invitation.id,
          details={"investigation_id": invitation.investigation_id, "customer_id": invitation.customer_id, "hours": body.hours})
    return out


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(investigation_id: int | None = None, customer_id: int | None = None, _: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(LocationInvitation)
    if investigation_id:
        q = q.filter(LocationInvitation.investigation_id == investigation_id)
    if customer_id:
        q = q.filter(LocationInvitation.customer_id == customer_id)
    return [invitation_out(i) for i in q.order_by(LocationInvitation.created_at.desc()).limit(500).all()]


@router.post("/invitations/{inv_id}/revoke", response_model=InvitationOut)
def revoke_invitation(inv_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    i = db.get(LocationInvitation, inv_id)
    if i is None:
        raise HTTPException(404, "الدعوة غير موجودة")
    if i.status in ("pending", "opened"):
        i.status = "revoked"
        i.responded_at = utcnow()
        db.commit()
        audit(db, "invitation.revoke", user=user, request=request, entity_type="invitation", entity_id=i.id)
    return invitation_out(i)


@router.get("/locations")
def list_locations(request: Request, investigation_id: int | None = None, customer_id: int | None = None,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(LocationRecord)
    if investigation_id:
        q = q.filter(LocationRecord.investigation_id == investigation_id)
    if customer_id:
        q = q.filter(LocationRecord.customer_id == customer_id)
    rows = q.order_by(LocationRecord.collected_at.desc()).limit(1000).all()
    audit(db, "location.list", user=user, request=request,
          details={"investigation_id": investigation_id, "customer_id": customer_id, "count": len(rows)})
    return {
        "current_location": CURRENT_LOCATION_UNAVAILABLE,
        "current_location_ar": CURRENT_LOCATION_UNAVAILABLE_AR,
        "historical": [location_out(l) for l in rows],
    }


@router.post("/locations/{loc_id}/reverse-geocode", response_model=LocationOut)
def geocode_location(loc_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    adapter = load_all(db)["adapters"]["nominatim_reverse_geocoding"]
    if not adapter.get("enabled"):
        raise HTTPException(409, "خدمة العنوان التقريبي (Nominatim) معطّلة من الإعدادات")
    loc = db.get(LocationRecord, loc_id)
    if loc is None:
        raise HTTPException(404, "السجل غير موجود")
    if not loc.address_text:
        try:
            loc.address_text = reverse_geocode(adapter["endpoint"], loc.latitude, loc.longitude)
        except GeocodingUnavailable as exc:
            raise HTTPException(503, f"تعذر الاتصال بخدمة العنوان: {exc}") from exc
        db.commit()
        audit(db, "location.reverse_geocode", user=user, request=request, entity_type="location", entity_id=loc.id)
    return location_out(loc)
