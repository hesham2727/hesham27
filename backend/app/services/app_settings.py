"""Admin-editable application settings stored in the database."""
from __future__ import annotations

import ipaddress
from copy import deepcopy
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AppSetting

OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

DEFAULTS: dict = {
    "organization_name": "",
    "public_base_url": "",
    "invitation_default_hours": 24,
    "map": {
        "enabled": True,
        "tile_url": OSM_TILE_URL,
        "attribution": OSM_ATTRIBUTION,
        "max_zoom": 19,
    },
    # Optional external adapters. All are FREE; every one can be disabled.
    "adapters": {
        # Manual sharing (copy link / WhatsApp click-to-chat / sms: URI). No account needed.
        "manual_share": {"enabled": True},
        # OpenStreetMap Nominatim reverse geocoding. Free, but subject to the
        # OSMF usage policy (max 1 request/second, no bulk use). Off by default.
        "nominatim_reverse_geocoding": {
            "enabled": False,
            "endpoint": "https://nominatim.openstreetmap.org/reverse",
        },
    },
    "retention": {
        "location_records_days": 30,
        "invitations_days": 30,
        "number_checks_days": 180,
        "audit_logs_days": 730,
        "closed_investigations_days": 0,  # 0 = keep until deleted manually
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_all(db: Session) -> dict:
    stored = {row.key: row.value for row in db.query(AppSetting).all()}
    return _merge(DEFAULTS, stored)


def save(db: Session, updates: dict) -> dict:
    current = load_all(db)
    merged = _merge(current, updates)
    for key in updates:
        if key not in DEFAULTS:
            continue
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=merged[key]))
        else:
            row.value = merged[key]
    db.commit()
    return merged


def effective_public_base_url(db: Session) -> tuple[str, str]:
    """Return (url, origin) where origin is 'env' or 'settings' or ''."""
    env = get_settings().public_base_url.strip()
    if env:
        return env.rstrip("/"), "env"
    stored = (load_all(db).get("public_base_url") or "").strip()
    return stored.rstrip("/"), "settings" if stored else ""


DEPLOYMENT_STEPS_AR = [
    "دعوات العملاء تتطلب رابط HTTPS يمكن الوصول إليه من الإنترنت.",
    "لا يمكن للعميل فتح عنوان localhost أو عنوان شبكة محلية (192.168.x.x / 10.x.x.x).",
    "الخيار المجاني: تشغيل المنفذ العام (Public-only) وربطه بنفق Cloudflare السريع (trycloudflare.com) – راجع docs/DEPLOYMENT_INTERNET.md.",
    "الخيار الإنتاجي: خادم VPS مع نطاق وشهادة Let's Encrypt المجانية (يتطلب اعتماد تكلفة الخادم).",
    "بعد الحصول على الرابط، أدخله في الإعدادات ← عنوان الوصول العام.",
]


def check_public_url(url: str) -> tuple[bool, str]:
    """Validate that `url` is plausibly reachable by customers over HTTPS."""
    if not url:
        return False, "لم يتم ضبط عنوان الوصول العام (Internet Mode غير مفعّل)."
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False, "يجب أن يبدأ عنوان الوصول العام بـ https:// لأن المتصفحات تمنع مشاركة الموقع بدون HTTPS."
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "عنوان الوصول العام غير صالح."
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".lan"):
        return False, "العنوان يشير إلى الجهاز المحلي أو شبكة محلية ولا يمكن للعملاء الوصول إليه من الإنترنت."
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            return False, "العنوان عنوان IP خاص/محلي ولا يمكن الوصول إليه من الإنترنت."
    except ValueError:
        if "." not in host:
            return False, "اسم المضيف ليس اسم نطاق عام."
    return True, "Internet Mode مفعّل – روابط الدعوة ستستخدم هذا العنوان."


def internet_mode_status(db: Session) -> dict:
    url, origin = effective_public_base_url(db)
    ok, message = check_public_url(url)
    return {
        "enabled": ok,
        "public_base_url": url,
        "configured_from": origin,
        "message": message,
        "steps": [] if ok else DEPLOYMENT_STEPS_AR,
    }
