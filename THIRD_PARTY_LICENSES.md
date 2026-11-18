# Third-Party Licenses

All components are free and open-source. No commercial licence is required for any of them.

| Component | Version | License | Notes |
|---|---|---|---|
| FastAPI | 0.164.0 | MIT | |
| Starlette | 1.10.0 | BSD-3-Clause | |
| Uvicorn | 0.54.0 | BSD-3-Clause | |
| SQLAlchemy | 2.1.9 | MIT | |
| Pydantic | 2.14.3 | MIT | |
| Alembic | 1.20.1 | MIT | |
| phonenumbers | 9.0.43 | Apache-2.0 | Port of Google libphonenumber |
| ReportLab (open-source toolkit) | 5.1.0 | BSD-3-Clause | |
| openpyxl | 3.1.5 | MIT | |
| arabic-reshaper | 3.1.0 | MIT | |
| python-bidi | 0.6.12 | LGPL-3.0 | Used unmodified as a separate library |
| tzdata | 2026.6 | Apache-2.0 | |
| React / React DOM | 19.3.1 | MIT | |
| React Router | 7.18.5 | MIT | |
| Leaflet | 1.9.4 | BSD-2-Clause | |
| Tailwind CSS | 3.4.19 | MIT | Build-time |
| Vite | 8.3.8 | MIT | Build-time |
| TypeScript | 5.9.3 | Apache-2.0 | Build-time |
| PySide6 / Qt 6 (incl. Qt WebEngine) | 6.12.0 | LGPL-3.0 | Shipped as separate shared libraries in the one-folder bundle so they can be replaced by the user, as LGPL requires. Qt WebEngine includes Chromium components under BSD-style and other permissive licences. |
| PyInstaller | 6.22.3 | GPL-2.0 with bootloader exception | The exception permits distributing the generated application under any terms |
| Inno Setup | 6.x | Inno Setup License (free, incl. commercial use) | Build-time |
| DejaVu Sans fonts | 2.37 | Bitstream Vera / DejaVu free licence | `backend/app/assets/fonts/LICENSE-DejaVu.txt` |
| OpenStreetMap data (tiles) | – | ODbL 1.0 | Attribution "© OpenStreetMap contributors" shown on the map |
| cloudflared (optional, not bundled) | – | Apache-2.0 | Downloaded separately by the user if Option 1 of Internet Mode is used |

LGPL obligations for PySide6/Qt and python-bidi: the libraries are not modified, are dynamically loaded, and can be replaced by the user in the installation folder. Their licence texts are available at the projects' official sources and inside the installed `PySide6` folder.
