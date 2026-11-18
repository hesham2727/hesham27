import io
from datetime import timedelta
from urllib.parse import urlparse

from conftest import H, enable_internet_mode, new_investigation
from openpyxl import load_workbook

from app.db import SessionLocal
from app.models import LocationRecord, NumberCheck, utcnow


def _seed(admin):
    enable_internet_mode(admin)
    inv = new_investigation(admin)
    admin.post(f"/api/investigations/{inv['id']}/sources", json={
        "source_name": "دليل أعمال", "source_url": "https://example.com", "observed_at": "2026-11-01T10:00:00Z",
        "summary": "الرقم مسجل باسم شركة توريدات", "reliability": "unverified"}, headers=H)
    r = admin.post("/api/invitations", json={"investigation_id": inv["id"], "purpose": "تأكيد موقع التسليم"}, headers=H)
    path = urlparse(r.json()["link"]).path
    v = admin.get(path).text.split('data-v="')[1].split('"')[0]
    admin.post(f"{path}/consent", json={"decision": "accept", "latitude": 31.2, "longitude": 29.9, "accuracy": 20,
                                       "consent_text_version": v}, headers=H)
    return inv


def test_pdf_export(admin):
    inv = _seed(admin)
    r = admin.get(f"/api/reports/investigations/{inv['id']}.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and len(r.content) > 3000
    assert inv["ref_code"] in r.headers["content-disposition"]


def test_xlsx_exports(admin):
    inv = _seed(admin)
    r = admin.get(f"/api/reports/investigations/{inv['id']}.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[:4] == ["التحقيقات", "المصادر العامة", "مواقع تاريخية", "سجل التحقق"]
    ws = wb["التحقيقات"]
    assert ws.sheet_view.rightToLeft is True
    assert ws.cell(2, 1).value == inv["ref_code"]
    assert wb["مواقع تاريخية"].max_row == 2
    assert "ليس موقعاً حالياً" in wb["مواقع تاريخية"].cell(2, 7).value
    r = admin.get("/api/reports/investigations.xlsx")
    assert r.status_code == 200 and load_workbook(io.BytesIO(r.content))["التحقيقات"].max_row == 2


def test_retention_purges_old_data(admin):
    _seed(admin)
    with SessionLocal() as db:
        for l in db.query(LocationRecord).all():
            l.collected_at = utcnow() - timedelta(days=31)
        for c in db.query(NumberCheck).all():
            c.checked_at = utcnow() - timedelta(days=200)
        db.commit()
    r = admin.post("/api/retention/run", headers=H)
    assert r.status_code == 200
    assert r.json()["location_records"] == 1 and r.json()["number_checks"] >= 1
    with SessionLocal() as db:
        assert db.query(LocationRecord).count() == 0


def test_retention_settings_validation(admin):
    assert admin.put("/api/settings", json={"retention": {"location_records_days": -1}}, headers=H).status_code == 422
    r = admin.put("/api/settings", json={"retention": {"location_records_days": 7}}, headers=H)
    assert r.json()["retention"]["location_records_days"] == 7
    assert r.json()["retention"]["audit_logs_days"] == 730  # other keys preserved


def test_map_tile_settings(admin):
    assert admin.put("/api/settings", json={"map": {"tile_url": "http://x/{z}/{x}/{y}.png"}}, headers=H).status_code == 422
    r = admin.put("/api/settings", json={"map": {"tile_url": "https://tiles.example.org/{z}/{x}/{y}.png", "attribution": "x"}}, headers=H)
    assert r.status_code == 200 and r.json()["map"]["enabled"] is True


def test_migrations_idempotent(settings):
    from app.db import run_migrations

    run_migrations(settings.database_url)
    run_migrations(settings.database_url)
