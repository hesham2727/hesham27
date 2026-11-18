"""Phase 3: full REST API integration (every endpoint), RBAC, CSRF, reports."""
import io

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader

from fbosint.main import create_app
from fbosint.services import engine

from .conftest import STRONG
from .fakes import FakeGraph, FakeWeb, make_image, public_resolver


@pytest.fixture()
def app_env(settings):
    fg, fw = FakeGraph(), FakeWeb()
    engine.deps = engine.EngineDeps(graph_transport=httpx.MockTransport(fg), web_transport=httpx.MockTransport(fw), resolver=public_resolver, sleep=lambda s: None)
    with TestClient(create_app()) as c:
        yield c, fg, fw
    engine.deps = engine.EngineDeps()


def login(c, username="admin", password=STRONG, client="desktop"):
    r = c.post("/api/auth/login", json={"username": username, "password": password, "client": client})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin(app_env):
    c, fg, fw = app_env
    assert c.post("/api/auth/setup", json={"username": "admin", "password": STRONG, "full_name": "Admin"}).status_code == 201
    return c, login(c), fg, fw


def mkuser(c, h, name, role):
    r = c.post("/api/admin/users", headers=h, json={"username": name, "password": STRONG, "role": role})
    assert r.status_code == 201, r.text
    return login(c, name)


def configure_meta(c, h):
    r = c.put("/api/settings/meta", headers=h, json={"app_id": "123", "app_secret": "appsecret", "access_token": "PAGE_TOKEN_XYZ", "redirect_uri": "http://127.0.0.1:8765/api/meta/oauth/callback"})
    assert r.status_code == 200 and r.json()["access_token_set"] and "PAGE_TOKEN_XYZ" not in r.text


def create_page_inv(c, h, **kw):
    body = {"target": "https://www.facebook.com/qusoorfacades", "target_type": "page_url", "purpose": "Supplier due diligence", "extra_urls": ["https://directory.example.org/q"], "options": {"collect_comments": True}}
    body.update(kw)
    r = c.post("/api/investigations", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_headers_and_docs(app_env):
    c, *_ = app_env
    r = c.get("/api/health")
    assert r.json()["status"] == "ok"
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert c.get("/api/openapi.json").status_code == 200
    assert c.get("/api/docs").status_code == 200


def test_unauthenticated_rejected(app_env):
    c, *_ = app_env
    for path in ["/api/dashboard", "/api/investigations", "/api/settings", "/api/admin/users", "/api/investigations/1/report"]:
        assert c.get(path).status_code == 401, path
    assert c.post("/api/investigations", json={}).status_code in (401, 422)


def test_full_investigation_lifecycle(admin):
    c, h, fg, fw = admin
    configure_meta(c, h)
    assert c.post("/api/settings/meta/test", headers=h).status_code == 200
    inv = create_page_inv(c, h)
    assert inv["status"] == "completed" and inv["reference"].startswith("INV-")
    assert inv["counts"]["posts"] == 3 and inv["counts"]["contacts"] >= 4
    iid = inv["id"]

    # list/search/filter
    assert c.get("/api/investigations", headers=h, params={"q": "qusoor"}).json()["total"] == 1
    assert c.get("/api/investigations", headers=h, params={"q": "%"}).json()["total"] == 0  # LIKE wildcard escaped
    assert c.get("/api/investigations", headers=h, params={"status": "failed"}).json()["total"] == 0
    assert c.get("/api/investigations", headers=h, params={"status": "bogus"}).status_code == 422
    dash = c.get("/api/dashboard", headers=h).json()
    assert dash["totals"]["investigations"] == 1 and len(dash["last_30_days"]) == 30

    # datapoints
    dps = c.get(f"/api/investigations/{iid}/datapoints", headers=h).json()
    assert any(d["field"] == "name" and d["verification_status"] == "verified" for d in dps)
    contacts = c.get(f"/api/investigations/{iid}/datapoints", headers=h, params={"category": "contact"}).json()
    assert all(d["category"] == "contact" for d in contacts) and all(d["source_url"] for d in contacts)

    # manual observation, review, delete
    r = c.post(f"/api/investigations/{iid}/datapoints", headers=h, json={"category": "observation", "field": "site_visit", "value": "Showroom observed at King Fahd Rd", "source_url": "https://maps.example.com/x", "classification": "analytical_observation"})
    assert r.status_code == 201 and r.json()["source_type"] == "manual"
    manual_id = r.json()["id"]
    assert c.post(f"/api/investigations/{iid}/datapoints", headers=h, json={"category": "contact", "field": "email", "value": "x", "source_url": "javascript:alert(1)"}).status_code == 422
    sales = next(d for d in contacts if d["value"] == "sales@qusoor.example.sa")
    r = c.patch(f"/api/investigations/{iid}/datapoints/{sales['id']}/review", headers=h, json={"verification_status": "verified", "confidence": "high", "notes": "Confirmed by phone with company reception"})
    assert r.json()["manually_reviewed"] and r.json()["classification"] == "fact"
    graph_dp = next(d for d in dps if d["source_type"] == "graph_api")
    assert c.delete(f"/api/investigations/{iid}/datapoints/{graph_dp['id']}", headers=h).status_code == 409
    assert c.delete(f"/api/investigations/{iid}/datapoints/{manual_id}", headers=h).status_code == 204

    # posts: search, date range, order, timeline
    posts = c.get(f"/api/investigations/{iid}/posts", headers=h, params={"order": "asc", "kind": "post"}).json()
    assert posts["total"] == 3 and posts["items"][0]["message"].startswith("New curtain wall")
    assert c.get(f"/api/investigations/{iid}/posts", headers=h, params={"q": "glazing"}).json()["total"] == 1
    assert c.get(f"/api/investigations/{iid}/posts", headers=h, params={"q": "curtain jeddah"}).json()["total"] == 1
    assert c.get(f"/api/investigations/{iid}/posts", headers=h, params={"date_from": "2026-03-10", "date_to": "2026-03-31"}).json()["total"] == 1
    tl = c.get(f"/api/investigations/{iid}/timeline", headers=h).json()
    assert tl["months"] == [{"month": "2026-03", "count": 2}, {"month": "2026-04", "count": 1}]

    # media list + file + upload (duplicate detection with collected image)
    media = c.get(f"/api/investigations/{iid}/media", headers=h).json()
    stored = [m for m in media if m["status"] == "stored"]
    f = c.get(f"/api/investigations/{iid}/media/{stored[0]['id']}/file", headers=h)
    assert f.status_code == 200 and f.headers["content-type"] == "image/png" and f.headers["x-content-type-options"] == "nosniff"
    up = c.post(f"/api/investigations/{iid}/media/upload", headers=h, files={"file": ("shot.png", fw.img_a, "image/png")}, params={"caption": "screenshot", "source_url": "https://example.org/a"})
    assert up.status_code == 201 and up.json()["duplicate_group"] is not None
    assert c.post(f"/api/investigations/{iid}/media/upload", headers=h, files={"file": ("x.html", b"<script>alert(1)</script>", "image/png")}).status_code == 422

    # sources/events
    src = c.get(f"/api/investigations/{iid}/sources", headers=h).json()
    assert src["items"] and "verified" in src["verification"]
    assert any(s["data_points"] > 0 for s in src["items"])
    ev = c.get(f"/api/investigations/{iid}/events", headers=h).json()
    assert ev[0]["step"] == "start" and ev[-1]["step"] == "finish"

    # add URLs + rerun keeps manual upload
    r = c.post(f"/api/investigations/{iid}/urls", headers=h, json={"urls": ["https://qusoor.example.sa/contact"]})
    assert r.status_code == 200 and "https://qusoor.example.sa/contact" in r.json()["extra_urls"]
    assert c.post(f"/api/investigations/{iid}/run", headers=h).json()["status"] == "completed"
    assert any(m["kind"] == "uploaded" for m in c.get(f"/api/investigations/{iid}/media", headers=h).json())

    # patch
    assert c.patch(f"/api/investigations/{iid}", headers=h, json={"title": "Qusoor supplier check"}).json()["title"] == "Qusoor supplier check"

    # reports
    for lang in ("ar", "en"):
        pdf = c.get(f"/api/investigations/{iid}/report", headers=h, params={"format": "pdf", "lang": lang})
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.headers["x-report-sha256"]) == 64
        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
        assert inv["reference"] in text and "qusoor" in text.lower()
        xl = c.get(f"/api/investigations/{iid}/report", headers=h, params={"format": "xlsx", "lang": lang})
        wb = load_workbook(io.BytesIO(xl.content))
        assert len(wb.sheetnames) == 11
        assert wb.worksheets[0].sheet_view.rightToLeft == (lang == "ar")
        contacts_ws = wb.worksheets[5]
        assert contacts_ws.max_row > 2
    assert c.get(f"/api/investigations/{iid}/report", headers=h, params={"format": "doc"}).status_code == 422

    # audit trail
    actions = {a["action"] for a in c.get("/api/admin/audit", headers=h, params={"page_size": 500}).json()["items"]}
    assert {"investigation_created", "report_exported", "datapoint_reviewed", "media_uploaded", "meta_credentials_updated", "login_success"} <= actions
    assert "PAGE_TOKEN_XYZ" not in c.get("/api/admin/audit", headers=h, params={"page_size": 500}).text

    # delete removes media folder
    from fbosint.config import get_settings
    folder = get_settings().media_dir / str(iid)
    assert folder.exists()
    assert c.delete(f"/api/investigations/{iid}", headers=h).status_code == 204
    assert not folder.exists()
    assert c.get(f"/api/investigations/{iid}", headers=h).status_code == 404


def test_invalid_targets_rejected(admin):
    c, h, *_ = admin
    for t in ["https://evil.com/x", "https://www.facebook.com/groups/1", "", "<script>alert(1)</script>"]:
        r = c.post("/api/investigations", headers=h, json={"target": t, "purpose": "Testing invalid input"})
        assert r.status_code == 422, t
    assert c.post("/api/investigations", headers=h, json={"target": "qusoor", "purpose": "x"}).status_code == 422  # purpose too short
    assert c.post("/api/investigations", headers=h, json={"target": "qusoor", "purpose": "valid purpose", "extra_urls": ["file:///etc/passwd"]}).status_code == 422


def test_private_profile_and_rate_limit_via_api(admin):
    c, h, fg, fw = admin
    configure_meta(c, h)
    inv = c.post("/api/investigations", headers=h, json={"target": "https://www.facebook.com/john.doe.123", "purpose": "Background check (consented)"}).json()
    assert inv["status"] == "partial" and inv["limitations"][0]["code"] == "graph_not_found"
    fg.mode = "rate_limited"
    inv2 = create_page_inv(c, h)
    assert inv2["status"] == "partial" and inv2["limitations"][0]["code"] == "graph_rate_limited"
    # reports still work for partial investigations and list limitations
    pdf = c.get(f"/api/investigations/{inv2['id']}/report", headers=h, params={"format": "pdf", "lang": "en"})
    assert "rate limit" in "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages).lower()


def test_rbac(admin):
    c, h, *_ = admin
    configure_meta(c, h)
    hi = mkuser(c, h, "investigator1", "investigator")
    hi2 = mkuser(c, h, "investigator2", "investigator")
    hv = mkuser(c, h, "viewer1", "viewer")
    inv = create_page_inv(c, hi)
    iid = inv["id"]
    # viewer: read + export, no writes
    assert c.get(f"/api/investigations/{iid}", headers=hv).status_code == 200
    assert c.get(f"/api/investigations/{iid}/report", headers=hv, params={"format": "xlsx"}).status_code == 200
    assert c.post("/api/investigations", headers=hv, json={"target": "qusoor", "purpose": "viewer attempt"}).status_code == 403
    assert c.delete(f"/api/investigations/{iid}", headers=hv).status_code == 403
    # other investigator can read but not modify
    assert c.get(f"/api/investigations/{iid}", headers=hi2).status_code == 200
    assert c.patch(f"/api/investigations/{iid}", headers=hi2, json={"title": "hijack"}).status_code == 403
    assert c.post(f"/api/investigations/{iid}/run", headers=hi2).status_code == 403
    # admin-only endpoints
    for path in ["/api/admin/users", "/api/admin/audit", "/api/admin/backups"]:
        assert c.get(path, headers=hi).status_code == 403
    assert c.put("/api/settings/meta", headers=hi, json={"access_token": "x"}).status_code == 403
    assert c.put("/api/settings", headers=hv, json={"retention_days": 1}).status_code == 403
    # settings readable by all, but token never exposed
    s = c.get("/api/settings", headers=hv).json()
    assert s["meta"]["access_token_set"] and "PAGE_TOKEN_XYZ" not in str(s)
    # admin can modify anything
    assert c.patch(f"/api/investigations/{iid}", headers=h, json={"notes": "admin note"}).status_code == 200


def test_user_admin(admin):
    c, h, *_ = admin
    r = c.post("/api/admin/users", headers=h, json={"username": "weak", "password": "123", "role": "viewer"})
    assert r.status_code == 422
    hu = mkuser(c, h, "analyst", "investigator")
    uid = next(u["id"] for u in c.get("/api/admin/users", headers=h).json() if u["username"] == "analyst")
    assert c.post("/api/admin/users", headers=h, json={"username": "analyst", "password": STRONG}).status_code == 409
    # disabling revokes sessions immediately
    assert c.patch(f"/api/admin/users/{uid}", headers=h, json={"is_active": False}).status_code == 200
    assert c.get("/api/auth/me", headers=hu).status_code == 401
    me_id = c.get("/api/auth/me", headers=h).json()["id"]
    assert c.patch(f"/api/admin/users/{me_id}", headers=h, json={"role": "viewer"}).status_code == 409
    # password change
    assert c.post("/api/auth/change-password", headers=h, json={"current_password": "bad", "new_password": "N3wPassword99"}).status_code == 400
    assert c.post("/api/auth/change-password", headers=h, json={"current_password": STRONG, "new_password": "N3wPassword99"}).status_code == 204
    assert c.get("/api/auth/me", headers=h).status_code == 401  # sessions revoked
    h2 = login(c, password="N3wPassword99")
    assert c.put("/api/auth/preferences", headers=h2, json={"language": "en"}).json()["language"] == "en"


def test_web_cookie_csrf_flow(app_env):
    c, *_ = app_env
    c.post("/api/auth/setup", json={"username": "admin", "password": STRONG})
    r = c.post("/api/auth/login", json={"username": "admin", "password": STRONG})
    csrf = r.json()["csrf_token"]
    body = {"target": "qusoorfacades", "purpose": "cookie session test", "start": False}
    assert c.post("/api/investigations", json=body).status_code == 403
    assert c.post("/api/investigations", json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert c.post("/api/investigations", json=body, headers={"X-CSRF-Token": csrf}).status_code == 201
    assert c.get("/api/auth/csrf").json()["csrf_token"] == csrf


def test_settings_backup_retention(admin, settings):
    c, h, *_ = admin
    r = c.put("/api/settings", headers=h, json={"retention_days": 30, "duplicate_threshold": 6, "default_language": "en"})
    assert r.json()["retention_days"] == 30
    assert c.put("/api/settings", headers=h, json={"graph_version": "latest"}).status_code == 422
    inv = c.post("/api/investigations", headers=h, json={"target": "qusoorfacades", "purpose": "retention test", "start": False}).json()
    # age the investigation beyond retention
    from datetime import timedelta
    from fbosint.database import SessionLocal
    from fbosint.models import Investigation, utcnow
    db = SessionLocal(); row = db.get(Investigation, inv["id"]); row.created_at = utcnow() - timedelta(days=31); db.commit(); db.close()
    b = c.post("/api/admin/backups", headers=h)
    assert b.status_code == 201
    name = b.json()["name"]
    assert c.get("/api/admin/backups", headers=h).json()[0]["name"] == name
    dl = c.get(f"/api/admin/backups/{name}", headers=h)
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    assert c.get("/api/admin/backups/..%2Fsecret.key", headers=h).status_code == 404
    assert c.post("/api/admin/retention/run", headers=h).json() == {"deleted": 1}
    assert c.get(f"/api/investigations/{inv['id']}", headers=h).status_code == 404


def test_oauth_authorized_account(admin):
    c, h, fg, fw = admin
    assert c.post("/api/meta/oauth/start", headers=h).status_code == 400  # not configured
    configure_meta(c, h)
    url = c.post("/api/meta/oauth/start", headers=h).json()["url"]
    assert url.startswith("https://www.facebook.com/v23.0/dialog/oauth?") and "client_id=123" in url
    state = httpx.URL(url).params["state"]
    assert c.get("/api/meta/oauth/callback", params={"state": "forged", "code": "x"}).status_code == 400

    orig = fg.__call__
    def handler(req):
        if req.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "USER_TOKEN_ABC", "token_type": "bearer", "expires_in": 5000000})
        return orig(req)
    engine.deps.graph_transport = httpx.MockTransport(handler)
    r = c.get("/api/meta/oauth/callback", params={"state": state, "code": "CODE"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings?meta=connected"
    assert c.get("/api/meta/oauth/callback", params={"state": state, "code": "CODE"}).status_code == 400  # replay
    assert c.get("/api/settings", headers=h).json()["meta"]["user_connected"]
    inv = c.post("/api/investigations", headers=h, json={"target": "me", "target_type": "authorized_account", "purpose": "Own account review"}).json()
    assert inv["object_type"] == "user" and inv["graph_object_id"] == "777"
    assert c.delete("/api/meta/connection", headers=h).status_code == 204
    assert not c.get("/api/settings", headers=h).json()["meta"]["user_connected"]


def test_rate_limiting_middleware(settings):
    settings.rate_limit_per_minute = 5
    from fbosint.security.ratelimit import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        codes = [c.get("/api/health").status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_formula_injection_neutralised(admin):
    from fbosint.reports.excel import _safe
    assert _safe("=HYPERLINK(\"http://evil\")").startswith("'=")
    assert _safe("+966 12 555") == "+966 12 555"
