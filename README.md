# Tahqiq (تحقيق) – Phone-Number Investigation & Consent-Based Location MVP

Low-cost, dual-platform MVP for Egypt: **Windows Desktop + Web Application** sharing **one FastAPI backend** and **one React frontend**. Zero mandatory recurring cost; every dependency is free and open-source.

| | |
|---|---|
| Users | 1–5 (individual / small team) |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic 2, Alembic, SQLite |
| Frontend | React 19 + TypeScript + Tailwind CSS (Arabic RTL) |
| Desktop | PySide6 + Qt WebEngine (same React build) + PyInstaller + Inno Setup |
| Maps | Leaflet + configurable OSM-compatible tile provider |
| Reports | ReportLab (Arabic PDF) + OpenPyXL (RTL Excel) |
| Tests | Pytest + HTTPX (59 tests) + optional Playwright end-to-end smoke test |

## 1. Implemented vs. not implemented

### Implemented and tested (free, works offline)

| Priority | Feature | Notes |
|---|---|---|
| P0 | Number validation | Offline, Google libphonenumber metadata. Validity, type, E.164, original operator of the number range (with MNP caveat), landline area. Arabic-Indic digits accepted. |
| P0 | Investigation history | Every validation is logged; investigations with mandatory lawful purpose, status, notes, re-check history. |
| P0 | Public source records | Manual capture (source, URL, observed date, reliability, summary) + documented catalogue of free sources. **No automated scraping.** |
| P0 | Arabic interface | Full RTL Arabic UI, Arabic PDF and RTL Excel. |
| P0 | Windows Desktop | Local backend on 127.0.0.1 + Qt WebEngine window; downloads, external links handled. |
| P0 | Web interface | Same build served by the backend (local, LAN, or Internet). |
| P0 | Shared backend | One FastAPI app; a separate *public-only* app exposes just the consent page. |
| P0 | Secure authentication | scrypt hashing, HttpOnly + SameSite=Strict session cookies, CSRF header, lockout, rate limiting, roles (admin/operator), first-run setup restricted to localhost. |
| P0 | PDF & Excel exports | Per investigation (PDF + Excel) and full register (Excel). |
| P1 | Consent-based GPS sharing | Single-use, expiring, revocable HTTPS invitation; customer explicitly accepts/declines; browser Geolocation API; one point-in-time location only. |
| P1 | Interactive map | Leaflet; historical points only, labelled with collection date/time and age. |
| P1 | Customer records | CRUD, linked investigations, invitations and shared locations. |
| P1 | Audit logs | All logins, views, changes, exports, invitations, consent events. Admin viewer with filters. |
| P1 | Data retention | Configurable per data type; runs at start-up, every 24 h, and on demand. |

### Safety rules enforced in code
- A phone number alone never yields a location. The UI, PDF and Excel always state: **"CURRENT LOCATION UNAVAILABLE – NO AUTHORIZED LOCATION SOURCE."**
- Shared locations are always labelled as historical with collection time; `is_current` is always `false`.
- Invitations are disabled (HTTP 409 + deployment steps) unless an externally reachable **HTTPS** URL is configured. `localhost`, private IPs and `.local` hosts are rejected.

### Not implemented (P2 – need third-party accounts, payment, or legal authorization)
Not built, not stubbed, no placeholders: paid telecom/number-intelligence providers, automated SMS (Twilio, Vonage, etc.), MDM integration, carrier integration, advanced analytics. Invitations are sent manually (copy, WhatsApp click-to-chat `wa.me`, or `sms:` link from the operator's own phone).

## 2. Quick start (from source)

```bash
# Linux/macOS
scripts/setup_linux.sh
cd backend && ../.venv/bin/python -m app.serve          # http://127.0.0.1:8000
```
Windows: `scripts\setup_windows.bat`, then `scripts\run_web_windows.bat` (web) or `python desktop\tahqiq_desktop.py` (desktop).

Open the URL, create the first admin account (only possible from the same machine), then use the app.

## 3. Documentation

| Document | Content |
|---|---|
| [docs/USER_MANUAL_AR.md](docs/USER_MANUAL_AR.md) | Arabic user manual |
| [docs/DEPLOYMENT_LOCAL.md](docs/DEPLOYMENT_LOCAL.md) | Desktop installer, local web, LAN, building the installer |
| [docs/DEPLOYMENT_INTERNET.md](docs/DEPLOYMENT_INTERNET.md) | Internet Mode: free tunnel option and VPS option |
| [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) | Controls, test evidence, residual risks |
| [docs/COST_BREAKDOWN.md](docs/COST_BREAKDOWN.md) | Actual operating cost (mandatory = 0) and optional paid items |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Every external data source with URL, limits, license |
| [docs/DATABASE_MIGRATION_POSTGRESQL.md](docs/DATABASE_MIGRATION_POSTGRESQL.md) | Alembic workflow and SQLite → PostgreSQL path |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data model, API map |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | Licenses of all dependencies |

## 4. Tests

```bash
cd backend && ../.venv/bin/python -m pytest            # 59 API/unit tests
cd frontend && npm run build                            # type-check + production build
E2E_CHROMIUM=/path/to/chrome python backend/tests_e2e/e2e_smoke.py   # optional browser E2E
```
CI (`.github/workflows/ci.yml`) runs the tests and builds the Windows installer on a `windows-latest` runner, publishing it as a build artifact.
