from datetime import timedelta
from urllib.parse import urlparse

import pytest
from conftest import H, enable_internet_mode, new_investigation

from app.services.app_settings import check_public_url
from app.services.phone import CURRENT_LOCATION_UNAVAILABLE


@pytest.mark.parametrize(
    "url,ok",
    [
        ("", False),
        ("http://example.com", False),
        ("https://localhost:8000", False),
        ("https://127.0.0.1", False),
        ("https://192.168.1.10", False),
        ("https://10.0.0.5:8443", False),
        ("https://myhost.local", False),
        ("https://intranet", False),
        ("https://abc-def.trycloudflare.com", True),
        ("https://tahqiq.example.com", True),
    ],
)
def test_public_url_policy(url, ok):
    assert check_public_url(url)[0] is ok


def test_invitations_disabled_without_internet_mode(admin):
    inv = new_investigation(admin)
    mode = admin.get("/api/internet-mode").json()
    assert mode["enabled"] is False and mode["steps"]
    r = admin.post("/api/invitations", json={"investigation_id": inv["id"], "purpose": "تأكيد عنوان التسليم"}, headers=H)
    assert r.status_code == 409
    assert "steps" in r.json()["detail"]


def test_settings_reject_private_url(admin):
    r = admin.put("/api/settings", json={"public_base_url": "https://192.168.1.5"}, headers=H)
    assert r.status_code == 422


def _invite(admin, inv_id, hours=24):
    r = admin.post("/api/invitations", json={"investigation_id": inv_id, "purpose": "تأكيد عنوان التسليم", "hours": hours}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


def test_full_consent_flow(admin):
    enable_internet_mode(admin)
    inv = new_investigation(admin)
    created = _invite(admin, inv["id"])
    assert created["link"].startswith("https://tahqiq.example.com/p/")
    assert created["whatsapp_url"].startswith("https://wa.me/201001234567?text=")
    assert created["sms_uri"].startswith("sms:+201001234567")
    path = urlparse(created["link"]).path

    page = admin.get(path)
    assert page.status_code == 200
    assert "اختيارية" in page.text and "مرة واحدة" in page.text
    assert "nonce-" in page.headers["content-security-policy"]
    version = page.text.split('data-v="')[1].split('"')[0]

    r = admin.post(f"{path}/consent", json={"decision": "accept", "latitude": 30.0444, "longitude": 31.2357,
                                           "accuracy": 15, "device_timestamp_ms": 1763000000000,
                                           "consent_text_version": version}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "shared"

    # single use
    again = admin.post(f"{path}/consent", json={"decision": "accept", "latitude": 1, "longitude": 1,
                                               "consent_text_version": version}, headers=H)
    assert again.status_code == 410
    assert admin.get(path).status_code == 410

    locs = admin.get("/api/locations", params={"investigation_id": inv["id"]}).json()
    assert locs["current_location"] == CURRENT_LOCATION_UNAVAILABLE
    assert len(locs["historical"]) == 1
    loc = locs["historical"][0]
    assert loc["is_current"] is False
    assert "موقع تاريخي" in loc["label"] and loc["collected_at"]
    invites = admin.get("/api/invitations", params={"investigation_id": inv["id"]}).json()
    assert invites[0]["status"] == "shared"


def test_decline_and_revoke(admin):
    enable_internet_mode(admin)
    inv = new_investigation(admin)
    c1 = _invite(admin, inv["id"])
    path = urlparse(c1["link"]).path
    version = admin.get(path).text.split('data-v="')[1].split('"')[0]
    assert admin.post(f"{path}/consent", json={"decision": "decline", "consent_text_version": version}, headers=H).json()["status"] == "declined"
    assert admin.get("/api/locations", params={"investigation_id": inv["id"]}).json()["historical"] == []

    c2 = _invite(admin, inv["id"])
    assert admin.post(f"/api/invitations/{c2['id']}/revoke", headers=H).json()["status"] == "revoked"
    assert admin.get(urlparse(c2["link"]).path).status_code == 410


def test_consent_validation(admin):
    enable_internet_mode(admin)
    inv = new_investigation(admin)
    path = urlparse(_invite(admin, inv["id"])["link"]).path
    version = admin.get(path).text.split('data-v="')[1].split('"')[0]
    # accept without coordinates
    assert admin.post(f"{path}/consent", json={"decision": "accept", "consent_text_version": version}, headers=H).status_code == 422
    # bad coordinates
    assert admin.post(f"{path}/consent", json={"decision": "accept", "latitude": 99, "longitude": 0, "consent_text_version": version}, headers=H).status_code == 422
    # wrong consent version
    assert admin.post(f"{path}/consent", json={"decision": "accept", "latitude": 1, "longitude": 1, "consent_text_version": "old"}, headers=H).status_code == 409
    # missing CSRF header
    assert admin.post(f"{path}/consent", json={"decision": "decline", "consent_text_version": version}).status_code == 403
    assert admin.get("/p/not-a-real-token").status_code == 404


def test_expired_invitation(admin):
    from app.db import SessionLocal
    from app.models import LocationInvitation, utcnow

    enable_internet_mode(admin)
    inv = new_investigation(admin)
    created = _invite(admin, inv["id"])
    with SessionLocal() as db:
        row = db.get(LocationInvitation, created["id"])
        row.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert admin.get(urlparse(created["link"]).path).status_code == 410
    assert admin.get("/api/invitations").json()[0]["effective_status"] == "expired"


def test_public_only_app_exposes_nothing_else(settings):
    from fastapi.testclient import TestClient

    from app.main import create_public_app

    with TestClient(create_public_app()) as c:
        assert c.get("/api/health").json()["public_only"] is True
        for path in ("/api/investigations", "/api/auth/me", "/api/users", "/api/docs", "/"):
            assert c.get(path).status_code == 404
        assert c.post("/api/auth/login", json={}, headers=H).status_code in (404, 405)


def test_geocoding_adapter_disabled_by_default(admin):
    s = admin.get("/api/settings").json()
    assert s["adapters"]["nominatim_reverse_geocoding"]["enabled"] is False
    assert admin.post("/api/locations/1/reverse-geocode", headers=H).status_code == 409


def test_adapter_endpoint_not_editable(admin):
    r = admin.put("/api/settings", json={"adapters": {"nominatim_reverse_geocoding": {"enabled": True, "endpoint": "https://evil.example"}}}, headers=H)
    assert r.status_code == 200
    assert r.json()["adapters"]["nominatim_reverse_geocoding"]["endpoint"].startswith("https://nominatim.openstreetmap.org")
    assert admin.put("/api/settings", json={"adapters": {"twilio": {"enabled": True}}}, headers=H).status_code == 422
