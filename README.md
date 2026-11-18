# FBOSINT Analyzer — Facebook Public Profile Intelligence & OSINT Analyzer

Collects and organises **legally accessible** information about Facebook Pages and profiles into
structured, source-attributed intelligence reports — using **only Meta's official Graph API** and
public URLs supplied by the investigator.

* **Two front-ends, one engine:** Windows desktop app (PySide6) and responsive web app (React + TypeScript),
  both thin clients of the same FastAPI backend and database.
* **Arabic (RTL, default) and English (LTR)** in both interfaces and in PDF/Excel reports.
* **Local mode** (single Windows PC) and **Network mode** (central server, LAN clients, TLS, RBAC).

> Meta does not expose personal-profile data through the official API unless that person authorises
> the app. The tool records this as an explicit limitation instead of working around it. See
> [docs/ARCHITECTURE.md §4](docs/ARCHITECTURE.md).

## Repository layout

| Path | Content |
|---|---|
| `backend/fbosint/` | FastAPI app: models, API routes, investigation engine, Graph client, enrichment, media hashing, verification, reports, backup, CLI |
| `backend/tests/` | Pytest unit + integration tests (simulated Meta API and websites) |
| `frontend/` | React + TypeScript web app, Vitest unit tests, Playwright E2E (`e2e/run-e2e.mjs`) |
| `desktop/` | PySide6 desktop client + tests |
| `shared/i18n/` | Arabic/English dictionaries shared by web and desktop |
| `packaging/` | PyInstaller spec, Inno Setup installer script, server entry point |
| `docker/` | Dockerfile + docker-compose (PostgreSQL) |
| `scripts/` | Windows build script, backup/restore/server batch files, icon and API-doc generators |
| `docs/` | Architecture & Meta API limits, schema (SQLite/PostgreSQL), API reference, Arabic install guide & user manual, security review |
| `.github/workflows/ci.yml` | CI: Linux tests (SQLite + PostgreSQL, web E2E, desktop) and Windows build → installer → silent install → self-test → uninstall |

## Quick start (from source)

```bash
pip install -r backend/requirements.txt -r desktop/requirements.txt
cd frontend && npm ci && npm run build && cd ..
cd backend && python -m fbosint.cli serve        # web: http://127.0.0.1:8765
python desktop/run_desktop.py                    # desktop app (starts the server itself in Local mode)
```

Windows installer: `scripts/build_windows.ps1` → `dist/installer/FBOSINT-Setup-1.0.0.exe`.
Full instructions (Arabic): [docs/INSTALL_AR.md](docs/INSTALL_AR.md). User manual: [docs/USER_MANUAL_AR.md](docs/USER_MANUAL_AR.md).

## Tests

```bash
python -m pytest backend/tests -q                       # 76 tests (SQLite)
FBO_TEST_DATABASE_URL=postgresql+psycopg://u:p@host/db python -m pytest backend/tests -q   # same on PostgreSQL
QT_QPA_PLATFORM=offscreen python -m pytest desktop/tests -q   # 8 tests
cd frontend && npx tsc -b && npx vitest run && node e2e/run-e2e.mjs   # 6 unit + 17 browser E2E steps
FBOSINT.exe --self-test                                  # packaged-application smoke test
```

## Documentation
* [Architecture & Meta Graph API limitations](docs/ARCHITECTURE.md)
* [REST API reference](docs/API.md) (also live at `/api/docs`)
* [Database schema — SQLite](docs/schema.sql) · [PostgreSQL](docs/schema.postgresql.sql)
* [Security review](docs/SECURITY_REVIEW.md)
* [Configuration template](.env.example)
