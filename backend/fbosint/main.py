"""FastAPI application factory."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from . import APP_NAME, __version__
from .config import get_settings
from .database import create_all, init_engine, session_scope
from .models import SCHEMA_VERSION, SchemaVersion
from .security.ratelimit import limiter

log = logging.getLogger("fbosint")

CSP_APP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; font-src 'self' data:; object-src 'none'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
CSP_DOCS = (
    "default-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "frame-ancestors 'none'; object-src 'none'"
)


def init_database() -> None:
    init_engine()
    create_all()
    with session_scope() as db:
        if db.scalar(select(SchemaVersion).limit(1)) is None:
            db.add(SchemaVersion(version=SCHEMA_VERSION))


def _frontend_dir() -> Path | None:
    s = get_settings()
    candidates = [Path(s.frontend_dist)] if s.frontend_dist else []
    here = Path(__file__).resolve().parent
    candidates += [here / "static", here.parent.parent / "frontend" / "dist"]
    for c in candidates:
        if c and (c / "index.html").is_file():
            return c
    return None


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_database()
        from .services import scheduler

        if settings.scheduler_enabled:
            scheduler.start()
        yield
        scheduler.stop()

    app = FastAPI(
        title=f"{APP_NAME} API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        path = request.url.path
        ip = request.client.host if request.client else "unknown"
        if path.startswith("/api/"):
            if path in ("/api/auth/login", "/api/auth/setup"):
                ok, retry = limiter.hit(ip, "login", settings.login_rate_limit_per_minute)
            else:
                ok, retry = limiter.hit(ip, "api", settings.rate_limit_per_minute)
            if not ok:
                return JSONResponse({"detail": "rate_limited"}, status_code=429, headers={"Retry-After": str(retry)})
        request_id = uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = CSP_DOCS if path.startswith("/api/docs") else CSP_APP
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if settings.tls_enabled:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return JSONResponse({"detail": "validation_error", "errors": errors}, status_code=422)

    from .api import routes_admin, routes_auth, routes_investigations, routes_meta, routes_reports, routes_settings

    for r in (routes_auth, routes_investigations, routes_reports, routes_settings, routes_admin, routes_meta):
        app.include_router(r.router)

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "app": APP_NAME, "version": __version__, "mode": settings.mode, "database": "sqlite" if settings.is_sqlite else "postgresql"}

    frontend = _frontend_dir()
    if frontend is not None:
        root = frontend.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404, "not_found")
            target = (root / full_path).resolve()
            if full_path and target.is_file() and root in target.parents:
                return FileResponse(target)
            return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    return app


