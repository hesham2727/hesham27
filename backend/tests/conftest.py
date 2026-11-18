from __future__ import annotations

import os

os.environ["TAHQIQ_SCRYPT_N"] = "1024"  # fast hashing in tests only

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, reset_settings
from app.security import login_limiter, public_limiter

H = {"X-Requested-With": "tahqiq"}
ADMIN_PW = "Admin-Passw0rd"


def make_settings(tmp_path, **kw) -> Settings:
    s = Settings()
    s.mode = kw.get("mode", "server")
    s.data_dir = tmp_path
    s.database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    s.public_base_url = kw.get("public_base_url", "")
    s.allow_remote_setup = False
    s.trust_proxy = False
    s.secure_cookies = None
    return s


@pytest.fixture
def settings(tmp_path):
    login_limiter.reset()
    public_limiter.reset()
    return reset_settings(make_settings(tmp_path))


@pytest.fixture
def client(settings):
    from app.main import create_app

    with TestClient(create_app(), base_url="http://testserver") as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "full_name": "مدير", "password": ADMIN_PW}, headers=H)
    assert r.status_code == 200, r.text
    return client


def enable_internet_mode(client, url="https://tahqiq.example.com"):
    r = client.put("/api/settings", json={"public_base_url": url}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["internet_mode"]["enabled"] is True


def new_investigation(client, phone="01001234567", **kw):
    body = {"phone": phone, "title": "تحقق من رقم مورد", "purpose": "التحقق من بيانات مورد قبل التعاقد"} | kw
    r = client.post("/api/investigations", json=body, headers=H)
    assert r.status_code == 201, r.text
    return r.json()
