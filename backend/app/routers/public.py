"""Customer-facing consent page. This is the ONLY router exposed publicly.

The page asks the device owner for explicit permission, then uses the
browser Geolocation API (HTTPS only) to send ONE point-in-time location.
No tracking, no background collection, single use.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import csrf_guard
from ..models import LocationInvitation, LocationRecord, utcnow
from ..schemas import ConsentIn
from ..security import client_ip, public_limiter, token_hash
from ..services.audit import audit
from ..services.timefmt import local

router = APIRouter(tags=["public"])

CONSENT_VERSION = "2026-11-v1"


def _page(body: str, nonce: str = "", status: int = 200, consent_version: str = "") -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>طلب مشاركة الموقع</title>
<style>
:root{{--bg:#f4f7f9;--card:#fff;--ink:#14212b;--muted:#5a6b78;--pri:#0f5e8c;--bad:#9a1c1c;--ok:#13683d}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI",Tahoma,"Noto Naskh Arabic",Arial,sans-serif;line-height:1.7}}
main{{max-width:560px;margin:0 auto;padding:20px 16px}}
.card{{background:var(--card);border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
h1{{font-size:1.3rem;margin:0 0 12px}} dl{{margin:0}} dt{{color:var(--muted);font-size:.9rem}} dd{{margin:0 0 10px}}
ul{{padding-inline-start:20px;color:var(--muted);font-size:.92rem}}
button{{font:inherit;border:0;border-radius:8px;padding:12px 16px;width:100%;margin-top:10px;cursor:pointer}}
.pri{{background:var(--pri);color:#fff}} .sec{{background:#e5eaee;color:var(--ink)}}
#msg{{margin-top:14px;font-weight:600}} .bad{{color:var(--bad)}} .ok{{color:var(--ok)}}
</style></head><body data-v="{consent_version}"><main><div class="card">{body}</div></main>
{f'<script nonce="{nonce}">{_SCRIPT}</script>' if nonce else ''}
</body></html>"""
    resp = HTMLResponse(html, status_code=status)
    resp.headers["Content-Security-Policy"] = (
        f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
    return resp


_SCRIPT = r"""
const msg = document.getElementById('msg');
const buttons = document.querySelectorAll('button');
function done(text, cls){ msg.textContent = text; msg.className = cls; buttons.forEach(b => b.disabled = true); }
async function send(payload){
  const r = await fetch(location.pathname + '/consent', {method:'POST', headers:{'Content-Type':'application/json','X-Requested-With':'tahqiq'}, body: JSON.stringify(payload)});
  const j = await r.json().catch(() => ({}));
  if(!r.ok) throw new Error(j.detail || 'تعذر الإرسال');
  return j;
}
document.getElementById('accept').addEventListener('click', () => {
  if(!window.isSecureContext || !navigator.geolocation){ done('المتصفح لا يدعم مشاركة الموقع عبر هذا الاتصال.', 'bad'); return; }
  msg.textContent = 'جارٍ طلب إذن الموقع من المتصفح...'; msg.className='';
  navigator.geolocation.getCurrentPosition(async pos => {
    try {
      await send({decision:'accept', latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy, device_timestamp_ms: Math.round(pos.timestamp), consent_text_version: document.body.dataset.v});
      done('تم إرسال موقعك مرة واحدة. شكراً لك. يمكنك إغلاق الصفحة.', 'ok');
    } catch(e){ done(e.message, 'bad'); }
  }, err => { done('لم يتم الحصول على الموقع: ' + (err.code === 1 ? 'تم رفض الإذن في المتصفح.' : 'تعذر تحديد الموقع.'), 'bad'); },
  {enableHighAccuracy:true, timeout:20000, maximumAge:0});
});
document.getElementById('decline').addEventListener('click', async () => {
  try { await send({decision:'decline', consent_text_version: document.body.dataset.v}); done('تم تسجيل رفضك. لن تتم مشاركة أي موقع.', 'ok'); }
  catch(e){ done(e.message, 'bad'); }
});
"""


def _load(db: Session, token: str) -> LocationInvitation | None:
    if not token or len(token) > 100:
        return None
    return db.query(LocationInvitation).filter(LocationInvitation.token_hash == token_hash(token)).first()


def _closed_page(inv: LocationInvitation | None) -> HTMLResponse:
    if inv is None:
        return _page("<h1>رابط غير صالح</h1><p>هذا الرابط غير صحيح أو تم حذفه.</p>", status=404)
    st = inv.effective_status
    text = {
        "expired": "انتهت صلاحية هذا الرابط.",
        "shared": "تمت مشاركة الموقع مسبقاً عبر هذا الرابط. الرابط يُستخدم مرة واحدة فقط.",
        "declined": "تم تسجيل رفضك مسبقاً. لن تتم مشاركة أي موقع.",
        "revoked": "تم إلغاء هذا الطلب من قِبل المُرسِل.",
    }.get(st, "هذا الرابط لم يعد متاحاً.")
    return _page(f"<h1>الطلب غير متاح</h1><p>{text}</p>", status=410)


@router.get("/p/{token}", response_class=HTMLResponse, include_in_schema=False)
def consent_page(token: str, request: Request, db: Session = Depends(get_db)):
    if not public_limiter.hit(f"p:{client_ip(request)}"):
        return _page("<h1>محاولات كثيرة</h1><p>يرجى المحاولة بعد دقيقة.</p>", status=429)
    inv = _load(db, token)
    if inv is None or inv.effective_status not in ("pending", "opened"):
        return _closed_page(inv)
    if inv.status == "pending":
        inv.status = "opened"
        inv.opened_at = utcnow()
        db.commit()
        audit(db, "invitation.opened", request=request, entity_type="invitation", entity_id=inv.id)
    nonce = secrets.token_urlsafe(16)
    org = escape(inv.requester_label or "الجهة المُرسِلة")
    body = f"""
<h1>طلب مشاركة موقعك مرة واحدة</h1>
<dl>
<dt>الجهة الطالبة</dt><dd>{org}</dd>
<dt>الغرض</dt><dd>{escape(inv.purpose)}</dd>
<dt>صلاحية الرابط حتى</dt><dd>{escape(local(inv.expires_at))} بتوقيت القاهرة</dd>
</dl>
<ul>
<li>المشاركة <b>اختيارية</b> بالكامل، ويمكنك الرفض دون أي أثر.</li>
<li>سيُرسَل موقعك <b>مرة واحدة فقط</b> لحظة الضغط على زر الموافقة – لا يوجد أي تتبع مستمر.</li>
<li>يُحفظ مع الموقع: وقت المشاركة، دقة الموقع، نوع المتصفح وعنوان IP كدليل على الموافقة.</li>
<li>تُحذف البيانات تلقائياً وفق سياسة الاحتفاظ لدى الجهة الطالبة.</li>
<li>سيطلب المتصفح منك إذناً منفصلاً؛ يمكنك رفضه.</li>
</ul>
<button id="accept" class="pri">أوافق وأشارك موقعي الآن (مرة واحدة)</button>
<button id="decline" class="sec">لا أوافق</button>
<p id="msg" role="status" aria-live="polite"></p>
"""
    # data-v carries the consent text version shown to the user
    return _page(body, nonce, consent_version=CONSENT_VERSION)


@router.post("/p/{token}/consent", include_in_schema=False, dependencies=[Depends(csrf_guard)])
def submit_consent(token: str, body: ConsentIn, request: Request, db: Session = Depends(get_db)):
    if not public_limiter.hit(f"p:{client_ip(request)}"):
        raise HTTPException(429, "محاولات كثيرة، حاول بعد دقيقة")
    inv = _load(db, token)
    if inv is None:
        raise HTTPException(404, "رابط غير صالح")
    if inv.effective_status not in ("pending", "opened"):
        raise HTTPException(410, "هذا الرابط لم يعد متاحاً")
    if body.consent_text_version != CONSENT_VERSION:
        raise HTTPException(409, "تم تحديث نص الموافقة، يرجى إعادة تحميل الصفحة")
    now = utcnow()
    if body.decision == "decline":
        inv.status = "declined"
        inv.responded_at = now
        db.commit()
        audit(db, "invitation.declined", request=request, entity_type="invitation", entity_id=inv.id)
        return {"status": "declined"}
    if body.latitude is None or body.longitude is None:
        raise HTTPException(422, "الإحداثيات مطلوبة عند الموافقة")
    device_ts = None
    if body.device_timestamp_ms:
        try:
            device_ts = datetime.fromtimestamp(body.device_timestamp_ms / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            device_ts = None
    rec = LocationRecord(
        invitation_id=inv.id,
        investigation_id=inv.investigation_id,
        customer_id=inv.customer_id,
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy_m=body.accuracy,
        device_timestamp=device_ts,
        collected_at=now,
        consent_text_version=body.consent_text_version,
        consent_given_at=now,
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255],
    )
    inv.status = "shared"
    inv.responded_at = now
    db.add(rec)
    db.commit()
    audit(db, "invitation.shared", request=request, entity_type="invitation", entity_id=inv.id, details={"location_id": rec.id})
    return {"status": "shared"}
