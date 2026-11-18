# Architecture

```
            ┌──────────────── Windows Desktop (Tahqiq.exe) ────────────────┐
            │  PySide6 window ── Qt WebEngine ──► http://127.0.0.1:<random> │
            │                                         │                     │
            │                     ┌───────────────────▼──────────────────┐  │
 Operator ──┤                     │  FastAPI  create_app()               │  │
 (browser   │                     │  /api/*  + React build + /p/<token>  │  │
  in web    │                     │  SQLAlchemy ► SQLite (%LOCALAPPDATA%)│  │
  mode)     │                     └───────────────────▲──────────────────┘  │
            │   optional --public-port ► create_public_app()  (/p/* only)   │
            └───────────────────────────────────────│───────────────────────┘
                                                    │ HTTPS (tunnel / reverse proxy)
                                             Customer's phone browser
```

* **One backend** (`backend/app`). `create_app()` serves the API, the React production build and the consent page. `create_public_app()` serves **only** the consent page and a health check – this is what gets exposed to the Internet in the zero-cost tunnel setup, so the admin UI never leaves the machine.
* **One frontend** (`frontend/`). The same `dist/` is served by the backend in web mode and loaded by Qt WebEngine in desktop mode.
* **No microservices, no message broker, no external database.** Background retention runs as an asyncio task inside the backend process.

## Modes

| Mode | How it runs | Who can reach it |
|---|---|---|
| Desktop | `Tahqiq.exe` – backend on `127.0.0.1:<random port>` | Only this Windows user |
| Local web | `python -m app.serve` – `127.0.0.1:8000` | Browsers on the same machine |
| LAN | `python -m app.serve --host 0.0.0.0` | Authorized users on the local network |
| Internet | Reverse proxy (Caddy) or tunnel (cloudflared) in front | Operators (VPS) / customers (consent page) |

## Data model (SQLite, portable to PostgreSQL)

| Table | Purpose |
|---|---|
| `users`, `auth_sessions` | Accounts (admin/operator), hashed session tokens |
| `customers` | Customer records |
| `investigations` | Number, title, mandatory lawful purpose, status, validation snapshot |
| `number_checks` | Every validation performed (investigation history) |
| `data_sources` | Catalogue of documented free sources |
| `source_records` | Manually captured public-source findings |
| `location_invitations` | Single-use invitation tokens (hash only), status, expiry |
| `location_records` | Consented point-in-time locations with consent evidence |
| `audit_logs` | Who did what, when, from where |
| `app_settings` | Admin-editable settings (map, adapters, retention, public URL) |

## API map (prefix `/api`, OpenAPI docs at `/api/docs`)

| Area | Endpoints |
|---|---|
| System | `GET /health`, `GET /system/status` |
| Auth | `POST /auth/setup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password` |
| Users (admin) | `GET/POST /users`, `PATCH /users/{id}` |
| Numbers | `POST /numbers/validate`, `GET /numbers/checks` |
| Investigations | `GET/POST /investigations`, `GET/PATCH/DELETE /investigations/{id}`, `POST /investigations/{id}/sources`, `DELETE /sources/{id}` |
| Sources catalogue | `GET/POST /data-sources`, `PATCH /data-sources/{id}` |
| Customers | `GET/POST /customers`, `GET/PATCH/DELETE /customers/{id}` |
| Location | `GET /internet-mode`, `POST/GET /invitations`, `POST /invitations/{id}/revoke`, `GET /locations`, `POST /locations/{id}/reverse-geocode` |
| Admin | `GET/PUT /settings`, `POST /retention/run`, `GET /audit` |
| Reports | `GET /reports/investigations/{id}.pdf`, `GET /reports/investigations/{id}.xlsx`, `GET /reports/investigations.xlsx` |
| Public | `GET /p/{token}`, `POST /p/{token}/consent` |

## Optional adapters

Configured in **Settings → Optional external adapters**. All are free and can be disabled:

| Adapter | Default | External call |
|---|---|---|
| `manual_share` | On | None – generates `wa.me` / `sms:` links opened on the operator's device |
| `nominatim_reverse_geocoding` | Off | `nominatim.openstreetmap.org`, on demand, ≤1 req/s, cached per location |
| Map tiles | On | Tile URL configurable (default OSM standard tiles) |

Adapter endpoints are fixed in code; only the enabled flag is editable through the API (prevents redirecting requests to arbitrary hosts).
