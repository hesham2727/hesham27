"""FastAPI application factory.

* create_app()        – full application (API + React UI + public consent page)
* create_public_app() – ONLY the customer consent page; safe to expose through
                        a tunnel or reverse proxy while the admin UI stays local.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import get_settings
from .db import SessionLocal, init_engine, run_migrations
from .routers import admin, auth, investigations, locations, public
from .services.data_sources import seed_data_sources
from .services.retention import run_retention

log = logging.getLogger("tahqiq")

APP_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; connect-src 'self'; font-src 'self' data:; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def _bootstrap() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    init_engine(settings.database_url)
    run_migrations(settings.database_url)
    with SessionLocal() as db:
        seed_data_sources(db)
        try:
            run_retention(db)
        except Exception:  # pragma: no cover - never block start-up
            log.exception("retention failed")


async def _retention_loop() -> None:
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            with SessionLocal() as db:
                run_retention(db)
        except Exception:  # pragma: no cover
            log.exception("retention failed")


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    _bootstrap()
    task = asyncio.create_task(_retention_loop())
    try:
        yield
    finally:
        task.cancel()


def _security_headers(app: FastAPI, csp: str | None) -> None:
    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if csp:
            response.headers.setdefault("Content-Security-Policy", csp)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse({"detail": "بيانات غير صالحة", "errors": errors}, status_code=422)


def create_app() -> FastAPI:
    app = FastAPI(title="Tahqiq API", version=__version__, lifespan=_lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    _security_headers(app, APP_CSP)
    _error_handlers(app)
    for r in (auth.router, investigations.router, locations.router, admin.router, public.router):
        app.include_router(r)

    dist = get_settings().frontend_dist
    index = dist / "index.html"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith(("api/", "p/")):
            raise StarletteHTTPException(404)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse(
            {"detail": "واجهة المستخدم غير مبنية. نفّذ: cd frontend && npm run build"}, status_code=503
        )

    return app


def create_public_app() -> FastAPI:
    app = FastAPI(title="Tahqiq Public", version=__version__, lifespan=_lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    _security_headers(app, None)  # the consent page sets its own nonce CSP
    _error_handlers(app)
    app.include_router(public.router)

    @app.get("/api/health", include_in_schema=False)
    def health():
        return {"status": "ok", "public_only": True}

    return app


