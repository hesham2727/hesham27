# Local Deployment (Desktop, Local Web, LAN)

All options below are free and work without Internet access (except map background tiles).

## A. Windows Desktop – installer

1. Obtain `Tahqiq-Setup-1.0.0.exe` (from the CI artifact, or build it – section D).
2. Run it. It installs **per user** (no administrator rights) to `%LOCALAPPDATA%\Programs\Tahqiq` and creates Start-menu/desktop shortcuts.
3. Launch **Tahqiq**. On first launch create the administrator account.

* Data: `%LOCALAPPDATA%\Tahqiq\tahqiq.db` (SQLite). Uninstalling does **not** delete it.
* Backup: close the app, copy `tahqiq.db` (and `tahqiq.db-wal` if present) to a safe place.
* The installer is **not code-signed** (a code-signing certificate is a paid item). Windows SmartScreen will show "Windows protected your PC" → *More info* → *Run anyway*.

## B. Local web mode (from source)

Requirements: Python 3.12+ and Node.js 20.19+ (both free).

```bat
scripts\setup_windows.bat
scripts\run_web_windows.bat
```
Open `http://127.0.0.1:8000`. Linux/macOS: `scripts/setup_linux.sh`, then `cd backend && ../.venv/bin/python -m app.serve`.

Environment variables (all optional):

| Variable | Default | Meaning |
|---|---|---|
| `TAHQIQ_DATA_DIR` | `%LOCALAPPDATA%\Tahqiq` / `~/.tahqiq` | Database and WebEngine data |
| `TAHQIQ_DATABASE_URL` | SQLite in data dir | e.g. `postgresql+psycopg://…` later |
| `TAHQIQ_PUBLIC_BASE_URL` | empty | Public HTTPS URL for invitations (overrides Settings) |
| `TAHQIQ_SESSION_HOURS` | 12 | Session lifetime |
| `TAHQIQ_TRUST_PROXY` | 0 | Trust `X-Forwarded-For` / `CF-Connecting-IP` from a local proxy |
| `TAHQIQ_SECURE_COOKIES` | auto | Force the `Secure` cookie flag |
| `TAHQIQ_ALLOW_REMOTE_SETUP` | 0 | Allow first admin creation from a non-local address (avoid) |

Create an admin from the command line (useful on a headless server):
```bash
cd backend && ../.venv/bin/python -m app.serve create-admin admin
```

## C. LAN access for authorized users

```bash
python -m app.serve --host 0.0.0.0 --port 8000
```
Users open `http://<server-LAN-IP>:8000`. Allow port 8000 in Windows Firewall **for the Private profile only**.

Security note: plain HTTP on a LAN sends passwords unencrypted across the network. Use only on a trusted network. For encrypted LAN access, put Caddy in front with its internal CA (`tls internal`) – free – and install Caddy's root certificate on each client.

## D. Building the Windows installer

Free tools: Python 3.12+, Node.js 20.19+, Inno Setup 6.

```powershell
.\desktop\build_windows.ps1
```
Output: `dist\installer\Tahqiq-Setup-1.0.0.exe`. Steps performed: create build venv → install `requirements-desktop.txt` → `npm ci && npm run build` → `pyinstaller desktop\tahqiq.spec` → `iscc desktop\installer.iss`.

Alternatively push to GitHub: `.github/workflows/ci.yml` builds the installer on `windows-latest` and attaches it as the artifact **Tahqiq-Windows-Installer** (GitHub Actions is free for public repositories and has a monthly free quota for private ones; Windows minutes consume that quota faster).

Expected size: the bundled Qt WebEngine (Chromium) dominates; the installed folder is roughly 0.5 GB.

## E. Verification checklist after installation

1. App opens and shows **الإعداد الأول** on first run.
2. Validate `01001234567` → valid, mobile, Vodafone (original range operator) with MNP warning.
3. Create an investigation, add a public source record, export PDF and Excel.
4. Location tab shows the *Internet Mode not configured* explanation (expected until section 3 of the Internet guide is done).
