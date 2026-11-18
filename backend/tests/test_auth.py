from conftest import ADMIN_PW, H

from app.security import hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("Secret-123456")
    assert h.startswith("scrypt$")
    assert verify_password("Secret-123456", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "garbage")


def test_status_then_setup(client):
    assert client.get("/api/system/status").json()["setup_required"] is True
    r = client.post("/api/auth/setup", json={"username": "admin", "password": ADMIN_PW}, headers=H)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.get("/api/system/status").json()["setup_required"] is False
    # second setup refused
    r = client.post("/api/auth/setup", json={"username": "second", "password": ADMIN_PW}, headers=H)
    assert r.status_code == 409


def test_setup_rejects_weak_password(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "short"}, headers=H)
    assert r.status_code == 422


def test_setup_refused_from_remote(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    inner = create_app()

    async def remote(scope, receive, send):  # pretend the request comes from the Internet
        if scope["type"] == "http":
            scope = dict(scope, client=("203.0.113.5", 5000))
        await inner(scope, receive, send)

    with TestClient(remote) as c:
        r = c.post("/api/auth/setup", json={"username": "admin", "password": ADMIN_PW}, headers=H)
        assert r.status_code == 403


def test_csrf_header_required(admin):
    r = admin.post("/api/investigations", json={"phone": "01001234567", "title": "t", "purpose": "purpose x"})
    assert r.status_code == 403
    r = admin.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW})
    assert r.status_code == 403


def test_requires_login(client):
    assert client.get("/api/investigations").status_code == 401
    assert client.get("/api/reports/investigations.xlsx").status_code == 401


def test_cookie_flags(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": ADMIN_PW}, headers=H)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_login_logout(admin):
    admin.post("/api/auth/logout", headers=H)
    assert admin.get("/api/auth/me").status_code == 401
    r = admin.post("/api/auth/login", json={"username": "admin", "password": "bad-password1"}, headers=H)
    assert r.status_code == 401
    r = admin.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW}, headers=H)
    assert r.status_code == 200
    assert admin.get("/api/auth/me").json()["username"] == "admin"


def test_lockout(admin):
    admin.post("/api/auth/logout", headers=H)
    for _ in range(5):
        admin.post("/api/auth/login", json={"username": "admin", "password": "bad-password1"}, headers=H)
    r = admin.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW}, headers=H)
    assert r.status_code == 423


def test_roles_and_user_management(admin):
    r = admin.post("/api/users", json={"username": "op1", "password": "Operator-123", "role": "operator"}, headers=H)
    assert r.status_code == 201
    uid = r.json()["id"]
    admin.post("/api/auth/logout", headers=H)
    assert admin.post("/api/auth/login", json={"username": "op1", "password": "Operator-123"}, headers=H).status_code == 200
    assert admin.get("/api/users").status_code == 403
    assert admin.get("/api/audit").status_code == 403
    assert admin.put("/api/settings", json={"organization_name": "x"}, headers=H).status_code == 403
    # deactivate operator as admin -> operator session killed
    admin.post("/api/auth/logout", headers=H)
    admin.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW}, headers=H)
    assert admin.patch(f"/api/users/{uid}", json={"is_active": False}, headers=H).status_code == 200
    admin.post("/api/auth/logout", headers=H)
    assert admin.post("/api/auth/login", json={"username": "op1", "password": "Operator-123"}, headers=H).status_code == 401


def test_admin_cannot_demote_self(admin):
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/users/{me['id']}", json={"role": "operator"}, headers=H).status_code == 400


def test_change_password(admin):
    r = admin.post("/api/auth/change-password", json={"current_password": ADMIN_PW, "new_password": "New-Passw0rd-1"}, headers=H)
    assert r.status_code == 204
    admin.post("/api/auth/logout", headers=H)
    assert admin.post("/api/auth/login", json={"username": "admin", "password": "New-Passw0rd-1"}, headers=H).status_code == 200


def test_security_headers(client):
    r = client.get("/api/system/status")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
