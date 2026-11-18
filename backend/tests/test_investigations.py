from conftest import H, new_investigation


def test_validate_logs_history(admin):
    r = admin.post("/api/numbers/validate", json={"number": "01001234567"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["is_valid"] and body["e164"] == "+201001234567"
    assert body["checked_by_username"] == "admin"
    hist = admin.get("/api/numbers/checks").json()
    assert len(hist) == 1 and hist[0]["e164"] == "+201001234567"
    assert admin.get("/api/numbers/checks", params={"q": "0100"}).json()
    assert admin.get("/api/numbers/checks", params={"q": "%"}).json() == []  # wildcard escaped


def test_investigation_crud_and_history(admin):
    inv = new_investigation(admin)
    assert inv["ref_code"].startswith("INV-")
    assert inv["validation"]["is_valid"] is True
    detail = admin.get(f"/api/investigations/{inv['id']}").json()
    assert len(detail["checks"]) == 1
    assert detail["locations"] == []
    r = admin.patch(f"/api/investigations/{inv['id']}", json={"status": "closed"}, headers=H)
    assert r.json()["status"] == "closed" and r.json()["closed_at"]
    assert len(admin.get("/api/investigations", params={"status": "closed"}).json()) == 1
    assert len(admin.get("/api/investigations", params={"q": "+2010"}).json()) == 1
    assert admin.delete(f"/api/investigations/{inv['id']}", headers=H).status_code == 204
    assert admin.get(f"/api/investigations/{inv['id']}").status_code == 404


def test_purpose_mandatory(admin):
    r = admin.post("/api/investigations", json={"phone": "01001234567", "title": "t", "purpose": ""}, headers=H)
    assert r.status_code == 422


def test_invalid_number_still_recorded(admin):
    inv = new_investigation(admin, phone="0100123")
    assert inv["validation"]["is_valid"] is False and inv["phone_e164"] == ""


def test_public_source_records(admin):
    inv = new_investigation(admin)
    catalog = admin.get("/api/data-sources").json()
    keys = {d["key"] for d in catalog}
    assert {"libphonenumber", "ntra_egypt", "osm_tiles", "manual_public_web"} <= keys
    for d in catalog:  # every source documented
        assert d["name"] and d["information"] and d["limitations"] and d["license"]
    manual = next(d for d in catalog if d["key"] == "manual_public_web")
    body = {
        "data_source_id": manual["id"],
        "source_name": "موقع الشركة الرسمي",
        "source_url": "https://example.com/contact",
        "source_type": "website",
        "observed_at": "2026-11-01T10:00:00Z",
        "summary": "الرقم مدرج كرقم خدمة العملاء",
        "reliability": "likely",
    }
    r = admin.post(f"/api/investigations/{inv['id']}/sources", json=body, headers=H)
    assert r.status_code == 201, r.text
    bad = body | {"source_url": "javascript:alert(1)"}
    assert admin.post(f"/api/investigations/{inv['id']}/sources", json=bad, headers=H).status_code == 422
    future = body | {"observed_at": "2099-01-01T00:00:00Z"}
    assert admin.post(f"/api/investigations/{inv['id']}/sources", json=future, headers=H).status_code == 422
    detail = admin.get(f"/api/investigations/{inv['id']}").json()
    assert len(detail["sources"]) == 1
    assert admin.delete(f"/api/sources/{r.json()['id']}", headers=H).status_code == 204


def test_customers(admin):
    r = admin.post("/api/customers", json={"full_name": "أحمد علي", "phone": "01212345678"}, headers=H)
    assert r.status_code == 201 and r.json()["phone_e164"] == "+201212345678"
    cid = r.json()["id"]
    assert admin.post("/api/customers", json={"full_name": "x", "phone": "123"}, headers=H).status_code == 422
    inv = new_investigation(admin, customer_id=cid)
    assert inv["customer_name"] == "أحمد علي"
    d = admin.get(f"/api/customers/{cid}").json()
    assert len(d["investigations"]) == 1
    assert admin.patch(f"/api/customers/{cid}", json={"notes": "عميل منذ 2024"}, headers=H).json()["notes"]
    assert admin.get("/api/customers", params={"q": "أحمد"}).json()


def test_audit_log_records_actions(admin):
    inv = new_investigation(admin)
    admin.get(f"/api/investigations/{inv['id']}")
    actions = [a["action"] for a in admin.get("/api/audit").json()]
    for a in ("auth.setup", "investigation.create", "investigation.view"):
        assert a in actions
    filtered = admin.get("/api/audit", params={"action": "investigation."}).json()
    assert all(a["action"].startswith("investigation.") for a in filtered)
