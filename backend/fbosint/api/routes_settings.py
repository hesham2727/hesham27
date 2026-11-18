"""Application settings and Meta API credentials (admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..database import get_db
from ..models import User
from ..schemas import AppSettingsIn, MetaCredentialsIn
from ..services import app_config
from ..services.audit import audit
from ..services.graph_client import GraphError, MetaGraphClient, debug_token
from ..services import engine
from .deps import client_ip, current_user, require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_app_settings(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    s = get_settings()
    return {
        "general": app_config.general_settings(db),
        "meta": app_config.meta_status(db, user.id),
        "system": {
            "version": __version__, "mode": s.mode, "database": "sqlite" if s.is_sqlite else "postgresql", "data_dir": str(s.data_dir) if user.role == "admin" else "",
            "tls": s.tls_enabled, "session_idle_minutes": s.session_idle_minutes, "session_ttl_hours": s.session_ttl_hours,
            "update_manifest_url": s.update_manifest_url,
        },
    }


@router.put("")
def update_app_settings(body: AppSettingsIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict:
    changes = body.model_dump(exclude_none=True)
    result = app_config.update_general_settings(db, changes)
    audit(db, "settings_updated", user, "settings", "general", client_ip(request), details=changes)
    return result


@router.put("/meta")
def update_meta(body: MetaCredentialsIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict:
    app_config.update_meta_config(db, body.app_id, body.app_secret, body.access_token, body.redirect_uri)
    changed = [k for k, v in body.model_dump().items() if v is not None]
    audit(db, "meta_credentials_updated", user, "settings", "meta", client_ip(request), details={"fields": changed})  # values never logged
    return app_config.meta_status(db, user.id)


@router.post("/meta/test")
def test_meta(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict:
    """Validate the configured token with Meta (debug_token when app credentials exist, else /me)."""
    cfg = app_config.meta_config(db)
    if not cfg.access_token:
        raise HTTPException(400, "meta_access_token_not_configured")
    try:
        if cfg.app_id and cfg.app_secret:
            info = debug_token(cfg.app_id, cfg.app_secret, cfg.access_token, cfg.graph_version, transport=engine.deps.graph_transport)
        else:
            c = MetaGraphClient(cfg.access_token, cfg.graph_version, transport=engine.deps.graph_transport)
            try:
                res = c.get("me", fields="id,name")
            finally:
                c.close()
            info = {"is_valid": True, "profile": res.data}
    except GraphError as e:
        audit(db, "meta_token_test", user, "settings", "meta", client_ip(request), False, {"error": e.kind})
        return {"ok": False, "error": e.as_dict()}
    audit(db, "meta_token_test", user, "settings", "meta", client_ip(request), True)
    return {"ok": bool(info.get("is_valid", True)), "info": info}
