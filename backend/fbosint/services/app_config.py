"""Runtime settings stored in the DB (override env defaults) and encrypted credentials."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AppSetting, EncryptedCredential, utcnow
from ..security.crypto import decrypt, encrypt, mask

GENERAL_KEY = "general"
META_KEY = "meta"


def _get(db: Session, key: str) -> dict[str, Any]:
    row = db.get(AppSetting, key)
    return dict(row.value) if row else {}


def _put(db: Session, key: str, value: dict[str, Any]) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
        row.updated_at = utcnow()
    db.commit()


def general_settings(db: Session) -> dict[str, Any]:
    s = get_settings()
    stored = _get(db, GENERAL_KEY)
    return {
        "retention_days": stored.get("retention_days", s.retention_days),
        "graph_version": stored.get("graph_version", s.meta_graph_version),
        "default_language": stored.get("default_language", "ar"),
        "backup_keep": stored.get("backup_keep", s.backup_keep),
        "duplicate_threshold": stored.get("duplicate_threshold", 8),
    }


def update_general_settings(db: Session, changes: dict[str, Any]) -> dict[str, Any]:
    stored = _get(db, GENERAL_KEY)
    stored.update({k: v for k, v in changes.items() if v is not None})
    _put(db, GENERAL_KEY, stored)
    return general_settings(db)


# ---------- credentials ----------
def _cred(db: Session, name: str, owner: int | None) -> EncryptedCredential | None:
    q = select(EncryptedCredential).where(EncryptedCredential.name == name)
    q = q.where(EncryptedCredential.owner_user_id.is_(None) if owner is None else EncryptedCredential.owner_user_id == owner)
    return db.scalar(q)


def store_secret(db: Session, name: str, value: str, owner: int | None = None, meta: dict | None = None) -> None:
    row = _cred(db, name, owner)
    if not value:
        if row is not None:
            db.delete(row)
            db.commit()
        return
    ct = encrypt(value)
    if row is None:
        db.add(EncryptedCredential(name=name, owner_user_id=owner, ciphertext=ct, meta=meta or {}))
    else:
        row.ciphertext = ct
        row.meta = meta or row.meta
        row.updated_at = utcnow()
    db.commit()


def load_secret(db: Session, name: str, owner: int | None = None) -> str:
    row = _cred(db, name, owner)
    return decrypt(row.ciphertext) if row else ""


def secret_meta(db: Session, name: str, owner: int | None = None) -> dict:
    row = _cred(db, name, owner)
    return dict(row.meta) if row else {}


@dataclass
class MetaConfig:
    app_id: str
    app_secret: str
    access_token: str
    redirect_uri: str
    graph_version: str

    @property
    def configured(self) -> bool:
        return bool(self.access_token)

    @property
    def oauth_ready(self) -> bool:
        return bool(self.app_id and self.app_secret and self.redirect_uri)


def meta_config(db: Session) -> MetaConfig:
    """DB values take precedence over environment variables."""
    s = get_settings()
    stored = _get(db, META_KEY)
    return MetaConfig(
        app_id=stored.get("app_id") or s.meta_app_id,
        app_secret=load_secret(db, "meta_app_secret") or s.meta_app_secret,
        access_token=load_secret(db, "meta_access_token") or s.meta_access_token,
        redirect_uri=stored.get("redirect_uri") or s.meta_redirect_uri,
        graph_version=general_settings(db)["graph_version"],
    )


def update_meta_config(db: Session, app_id: str | None, app_secret: str | None, access_token: str | None, redirect_uri: str | None) -> None:
    stored = _get(db, META_KEY)
    if app_id is not None:
        stored["app_id"] = app_id
    if redirect_uri is not None:
        stored["redirect_uri"] = redirect_uri
    _put(db, META_KEY, stored)
    if app_secret is not None:
        store_secret(db, "meta_app_secret", app_secret)
    if access_token is not None:
        store_secret(db, "meta_access_token", access_token)


def meta_status(db: Session, user_id: int | None = None) -> dict[str, Any]:
    cfg = meta_config(db)
    user_token = load_secret(db, "meta_user_token", user_id) if user_id else ""
    return {
        "app_id": cfg.app_id,
        "app_secret_set": bool(cfg.app_secret),
        "access_token_set": bool(cfg.access_token),
        "access_token_masked": mask(cfg.access_token),
        "redirect_uri": cfg.redirect_uri,
        "graph_version": cfg.graph_version,
        "oauth_ready": cfg.oauth_ready,
        "user_connected": bool(user_token),
        "user_connection": secret_meta(db, "meta_user_token", user_id) if user_id else {},
    }
