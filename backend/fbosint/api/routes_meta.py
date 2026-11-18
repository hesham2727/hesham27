"""Facebook Login (OAuth 2.0) to connect the investigator's *own* authorised account."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OAuthState, User, utcnow
from ..services import app_config, engine
from ..services.audit import audit
from ..services.graph_client import GraphError, exchange_code
from .deps import client_ip, current_user

router = APIRouter(prefix="/api/meta", tags=["meta"])
SCOPES = ["public_profile"]  # additional scopes (user_posts, user_photos, user_link) require Meta App Review


@router.post("/oauth/start")
def oauth_start(request: Request, scopes: str = Query("", max_length=200, pattern=r"^[a-z_,]*$"), db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    cfg = app_config.meta_config(db)
    if not cfg.oauth_ready:
        raise HTTPException(400, "meta_oauth_not_configured")
    state = secrets.token_urlsafe(24)
    db.add(OAuthState(state_hash=hashlib.sha256(state.encode()).hexdigest(), user_id=user.id, expires_at=utcnow() + timedelta(minutes=10)))
    db.commit()
    scope = sorted(set(SCOPES + [s for s in scopes.split(",") if s]))
    url = f"https://www.facebook.com/{cfg.graph_version}/dialog/oauth?" + urlencode({"client_id": cfg.app_id, "redirect_uri": cfg.redirect_uri, "state": state, "scope": ",".join(scope), "response_type": "code"})
    audit(db, "meta_oauth_started", user, "meta", "", client_ip(request), details={"scopes": scope})
    return {"url": url}


@router.get("/oauth/callback")
def oauth_callback(request: Request, state: str = Query(..., max_length=100), code: str = Query("", max_length=1000), error: str = Query("", max_length=200), db: Session = Depends(get_db)):
    row = db.scalar(select(OAuthState).where(OAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest()))
    if row is None or row.used or row.expires_at < utcnow():
        raise HTTPException(400, "invalid_or_expired_state")
    row.used = True
    db.commit()
    user = db.get(User, row.user_id)
    if error or not code:
        audit(db, "meta_oauth_denied", user, "meta", "", client_ip(request), False, {"error": error})
        return RedirectResponse("/settings?meta=denied", status_code=303)
    cfg = app_config.meta_config(db)
    try:
        tok = exchange_code(cfg.app_id, cfg.app_secret, cfg.redirect_uri, code, cfg.graph_version, transport=engine.deps.graph_transport)
    except GraphError as e:
        audit(db, "meta_oauth_failed", user, "meta", "", client_ip(request), False, {"error": e.message[:200]})
        return RedirectResponse("/settings?meta=error", status_code=303)
    app_config.store_secret(db, "meta_user_token", tok.get("access_token", ""), row.user_id, {"connected_at": utcnow().isoformat(), "expires_in": tok.get("expires_in")})
    audit(db, "meta_oauth_connected", user, "meta", "", client_ip(request))
    return RedirectResponse("/settings?meta=connected", status_code=303)


@router.delete("/connection", status_code=204)
def disconnect(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> None:
    app_config.store_secret(db, "meta_user_token", "", user.id)
    audit(db, "meta_oauth_disconnected", user, "meta", "", client_ip(request))
