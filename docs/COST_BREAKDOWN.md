# Operating Cost Breakdown

## Mandatory recurring cost: **0 EGP**

The core application (all P0 and P1 features) runs on an existing Windows PC with no subscriptions, no paid APIs, no hosting and no licence fees.

| Item | Used for | Cost | Basis |
|---|---|---|---|
| Python, FastAPI, Starlette, Uvicorn, SQLAlchemy, Pydantic, Alembic | Backend | 0 | MIT / BSD licences |
| SQLite | Database | 0 | Public domain, embedded |
| phonenumbers (libphonenumber data) | Number validation | 0 | Apache-2.0, offline |
| ReportLab, OpenPyXL, arabic-reshaper, python-bidi, DejaVu fonts | PDF/Excel exports | 0 | BSD / MIT / LGPL-3.0 / free font licence |
| React, React Router, Tailwind CSS, Vite, TypeScript | Web UI | 0 | MIT / Apache-2.0 |
| Leaflet + OpenStreetMap tiles | Map | 0 | BSD-2 / ODbL with attribution; light use per OSMF policy |
| PySide6 / Qt WebEngine | Desktop window | 0 | LGPL-3.0 (dynamically linked, licence texts shipped) |
| PyInstaller, Inno Setup | Windows installer | 0 | GPL with bootloader exception / Inno Setup licence (free incl. commercial) |
| Manual invitation sending (copy / WhatsApp link / SMS from own phone) | Customer invitations | 0 app cost | Normal mobile tariffs of the operator's own line apply if SMS is used |
| Cloudflare Quick Tunnel (`cloudflared`) | Internet Mode, pilot | 0 | No account required; Apache-2.0 client |
| GitHub Actions | Automated Windows build | 0 | Free for public repos; monthly free quota for private repos |
| Existing PC, electricity, office Internet | Hosting in desktop mode | Existing overhead | Not incremental |

Resource footprint: backend idle RAM is small (tens of MB); the desktop window adds Qt WebEngine (Chromium) memory similar to one browser tab. Disk: ~0.5 GB installed, database grows by kilobytes per investigation.

## Optional items that cost money (NOT activated – require explicit approval)

| Item | Why someone might want it | Without it |
|---|---|---|
| VPS (e.g. 1 vCPU / 1 GB) | Stable 24/7 Internet Mode and remote operator access | Use the free tunnel from the office PC (URL changes on restart) |
| Domain name | Fixed, branded invitation URL | Random `trycloudflare.com` URL or free dynamic-DNS name |
| Code-signing certificate | Remove the Windows SmartScreen warning | Users click *More info → Run anyway* once |
| Paid SMS gateway | Automatic sending of invitations | Manual sending (implemented) |
| Paid telecom / number-intelligence APIs, MDM, carrier integration (P2) | Additional data | Not available – and also subject to legal authorization |

Prices for these items are not quoted here: they vary by provider and exchange rate and must be obtained as current written quotes before any approval.

## Hidden-cost checks performed
* No dependency requires an API key, account, credit card or prepaid balance.
* No telemetry or external calls at start-up. The only outbound calls are map tiles (when the map is displayed) and Nominatim (disabled by default, on demand).
* All fonts and assets are bundled; the UI works fully offline.
