"""Phase 1: security primitives and authentication."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fbosint.api import routes_auth
from fbosint.models import User, UserSession, utcnow
from fbosint.security import crypto
from fbosint.security.passwords import hash_password, password_problems, verify_password
from fbosint.security.ratelimit import SlidingWindowLimiter
from fbosint.security.sessions import create_session, resolve_session

from .conftest import STRONG


def test_password_hash_roundtrip_and_salt():
    h1, h2 = hash_password("abc12345678"), hash_password("abc12345678")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert verify_password("abc12345678", h1)
    assert not verify_password("wrong", h1)
    assert not verify_password("x", "garbage")


def test_password_policy():
    assert "password_too_short" in password_problems("a1")
    assert "password_needs_letters_and_digits" in password_problems("abcdefghijkl")
    assert "password_contains_username" in password_problems("hesham12345", "hesham")
    assert password_problems(STRONG) == []
    assert password_problems("كلمةمرورقوية123") == []


def test_encryption_roundtrip_and_key_file(settings):
    ct = crypto.encrypt("EAAG-secret-token")
    assert "EAAG" not in ct
    assert crypto.decrypt(ct) == "EAAG-secret-token"
    key_file = settings.data_dir / "secret.key"
    assert key_file.exists()
    import os, stat, sys
    if not sys.platform.startswith("win"):
        assert stat.S_IMODE(os.stat(key_file).st_mode) == 0o600
    with pytest.raises(ValueError):
        crypto.decrypt(ct[:-4] + "AAAA")
    assert crypto.mask("EAAGabcdefgh1234") == "EAAG••••1234"


def test_rate_limiter_window():
    lim = SlidingWindowLimiter()
    assert all(lim.hit("1.1.1.1", "b", 3)[0] for _ in range(3))
    ok, retry = lim.hit("1.1.1.1", "b", 3)
    assert not ok and retry >= 1
    assert lim.hit("2.2.2.2", "b", 3)[0]


def test_session_expiry_and_idle(db, settings):
    u = User(username="u1", password_hash=hash_password(STRONG))
    db.add(u); db.commit()
    token, sess = create_session(db, u, "web", "1.2.3.4", "ua")
    assert resolve_session(db, token).id == sess.id
    assert resolve_session(db, token + "x") is None
    sess.last_seen_at = utcnow() - timedelta(minutes=settings.session_idle_minutes + 1)
    db.commit()
    assert resolve_session(db, token) is None
    assert db.get(UserSession, sess.id).revoked


@pytest.fixture()
def client(settings):
    app = FastAPI()
    app.include_router(routes_auth.router)
    return TestClient(app)


def test_setup_login_logout_flow(client):
    assert client.get("/api/auth/setup-status").json() == {"needs_setup": True}
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "short"})
    assert r.status_code == 422
    r = client.post("/api/auth/setup", json={"username": "admin", "password": STRONG})
    assert r.status_code == 201 and r.json()["role"] == "admin"
    assert client.post("/api/auth/setup", json={"username": "xx2", "password": STRONG}).status_code == 409

    assert client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "admin", "password": STRONG})
    assert r.status_code == 200
    assert r.json()["token"] is None  # web clients never get the raw token in JSON
    assert "fbo_session" in r.cookies and "httponly" in r.headers["set-cookie"].lower()
    csrf = r.json()["csrf_token"]
    assert client.get("/api/auth/me").json()["username"] == "admin"
    # cookie-authenticated unsafe request without CSRF header is rejected
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_desktop_bearer_login(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": STRONG})
    r = client.post("/api/auth/login", json={"username": "admin", "password": STRONG, "client": "desktop"})
    token = r.json()["token"]
    assert token and "fbo_session" not in r.cookies
    c2 = TestClient(client.app)
    h = {"Authorization": f"Bearer {token}"}
    assert c2.get("/api/auth/me", headers=h).status_code == 200
    assert c2.post("/api/auth/logout", headers=h).status_code == 204  # no CSRF needed for bearer
    assert c2.get("/api/auth/me", headers=h).status_code == 401


def test_account_lockout(client, settings):
    client.post("/api/auth/setup", json={"username": "admin", "password": STRONG})
    for _ in range(settings.login_max_failures):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": STRONG}).status_code == 423


def test_unknown_user_and_audit(client, db):
    from fbosint.models import AuditLog
    assert client.post("/api/auth/login", json={"username": "ghost", "password": "x"}).status_code == 401
    log = db.query(AuditLog).filter_by(action="login_failed").one()
    assert log.username == "ghost" and not log.success
