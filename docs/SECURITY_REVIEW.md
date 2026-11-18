# Security Review — FBOSINT Analyzer 1.0.0

Review date: 2026-11-18. Scope: backend (`backend/fbosint`), web client (`frontend/src`), desktop client
(`desktop/fbosint_desktop`), packaging and deployment files.

Method: manual code review against OWASP ASVS L2 themes; automated tests for each control (references
below); static analysis with **Bandit 1.x**; dependency audit with **pip-audit** and **npm audit**.

## 1. Summary

| Area | Result |
|---|---|
| Bandit (Python SAST) | 0 high, 0 medium; 8 low — all reviewed (false positives such as `''` defaults flagged as "hardcoded password", deliberate `try/except: pass` in tolerant HTML/EXIF parsing) |
| pip-audit | **Fixed:** 42 advisories in Pillow 12.3.0 → upgraded to 13.0.0. Now: no known vulnerabilities |
| npm audit (runtime deps) | **Fixed:** react-router advisories → upgraded to 7.18.5. Now: none |
| npm audit (dev-only tooling) | **Fixed:** vite/vitest/esbuild/tinypool → upgraded (vite 7.3.8, vitest 4.1.12). **Accepted:** `picomatch` ReDoS (no patched release exists; build-time only, inputs are our own config globs, not shipped in the application) |
| Automated security tests | 30+ assertions across `backend/tests` (listed per control below) |

## 2. Controls

### 2.1 Authentication
* Passwords hashed with **scrypt** (N=2^14, r=8, p=1, 16-byte salt), constant-time comparison. Dummy hash on unknown user to reduce username enumeration by timing.
* Policy: ≥10 chars, letters + digits, must not contain the username.
* **Lockout:** 5 failures → 15 min (`423 account_locked`); login endpoint additionally rate-limited (10/min/IP).
* First-run `setup` only works while the user table is empty (`409` afterwards).
* Facebook passwords are never requested or stored. Facebook access is via official tokens / OAuth only.
* Tests: `test_password_*`, `test_account_lockout`, `test_setup_login_logout_flow`, `test_unknown_user_and_audit`.

### 2.2 Session management
* 256-bit random tokens; **only SHA-256 of the token is stored** (DB leak does not expose live sessions).
* Absolute TTL (12 h) + idle timeout (60 min); logout and password change revoke sessions; disabling a user or changing role revokes all of the user's sessions immediately.
* Web cookie: `HttpOnly`, `SameSite=Strict`, `Secure` when TLS is enabled. Raw token is never returned in JSON to web clients.
* Tests: `test_session_expiry_and_idle`, `test_user_admin`, `test_desktop_bearer_login`.

### 2.3 CSRF
* Cookie-authenticated unsafe requests require `X-CSRF-Token` equal to the per-session token (double submit + server-side comparison, constant time). Bearer-token clients (desktop) carry no ambient credentials.
* Tests: `test_web_cookie_csrf_flow`, `test_setup_login_logout_flow`.

### 2.4 Authorisation (RBAC)
* `admin` / `investigator` / `viewer`; ownership check for investigator modifications; admin-only settings, users, audit, backups. Admin cannot demote/disable self (prevents lock-out).
* Tests: `test_rbac`, `test_unauthenticated_rejected`.

### 2.5 Input validation & injection
* All bodies/queries validated with Pydantic (lengths, patterns, enums). Facebook targets parsed by a strict whitelist parser (`url_parser.py`) rejecting control/HTML characters, non-Facebook hosts, credentials in URLs, unsupported paths.
* **SQL injection:** ORM-parameterised queries only; no raw SQL. LIKE searches use `autoescape=True` (`%`/`_` are literal). Verified on SQLite and PostgreSQL.
* **XSS:** React escapes all output; no `dangerouslySetInnerHTML`; links rendered only for `http(s)` schemes with `rel="noopener noreferrer nofollow"`. Strict **CSP** (`script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`). PDF generator escapes ReportLab markup.
* **Spreadsheet formula injection:** collected text cells are written as typed strings; values starting with `=`/`@` are prefixed.
* **Uploads:** size limit (10 MB), decoded and verified with Pillow, format allow-list (JPEG/PNG/GIF/WEBP/BMP), decompression-bomb guard, stored under a content hash name, served with detected MIME + `nosniff`; path traversal checks on file and backup downloads.
* Tests: `test_parse_invalid`, `test_invalid_targets_rejected`, `test_full_investigation_lifecycle` (LIKE escaping, upload rejection), `test_formula_injection_neutralised`, `SafeLink` unit test.

### 2.6 SSRF and outbound requests
* Enrichment fetcher: http/https only, standard ports, no URL credentials, DNS resolution checked against private/loopback/link-local/reserved ranges **on every redirect hop**, max 5 redirects, 2 MB, 15 s, robots.txt honoured.
* Facebook-family domains are refused by the generic fetcher (no scraping). Graph API client only talks to `graph.facebook.com` and validates `paging.next` URLs.
* Residual risk: DNS rebinding between validation and connection (TOCTOU). Mitigation: run network-mode servers on segments where internal services require authentication; option `FBO_ENRICH_ALLOW_PRIVATE_NETWORKS` is **off** by default.
* Tests: `test_fetch_blocked` (localhost, 127.0.0.1, ::1, 169.254.169.254, private DNS, redirect to internal, robots, oversize, Facebook domains), `test_graph_pagination_validated`.

### 2.7 Secrets and cryptography
* Meta App Secret, access tokens and OAuth user tokens encrypted at rest with **Fernet** (AES-128-CBC + HMAC-SHA256). Key from `FBO_ENCRYPTION_KEY` or generated `secret.key` created with mode 0600.
* Secrets are never returned by the API (masked), never written to audit logs, never included in stored source URLs (Graph attribution uses the endpoint path only). `appsecret_proof` is sent when the App Secret is configured.
* OAuth: single-use, hashed, 10-minute `state`; replay rejected.
* Tests: `test_encryption_roundtrip_and_key_file`, `test_oauth_authorized_account`, token-leak assertions in `test_page_investigation_full` and `test_full_investigation_lifecycle`.

### 2.8 Rate limiting
* Sliding-window per client IP: 240 req/min API, 10 req/min login/setup (configurable), `429` + `Retry-After`.
* Meta rate limits are respected — no aggressive retries on codes 4/17/32/613/800xx; the investigation is marked partial.
* Tests: `test_rate_limiter_window`, `test_rate_limiting_middleware`, `test_graph_failures_recorded`.

### 2.9 Audit, retention, deletion
* Append-only audit log: logins (success/failure), setup, investigations (create/update/run/delete/URLs), manual data/reviews (before/after), uploads, exports (with SHA-256 of the file), settings/credential changes (field names only), OAuth, backups, retention purges.
* Retention: automatic purge after N days (default 365), hard delete including media files; manual delete per investigation.
* Tests: `test_settings_backup_retention`, audit assertions in lifecycle test.

### 2.10 HTTP hardening
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cache-Control: no-store` on API responses, HSTS when TLS is on, `server` header suppressed. CORS disabled unless explicitly configured.

### 2.11 Privacy-by-design constraints
No facial recognition; GPS EXIF coordinates are not extracted; no free-text phone harvesting; related profile links are recorded as *association not verified*; analytical observations are separated from facts in UI and reports.

## 3. Deployment recommendations
1. **Network mode:** always enable TLS (`gen-cert`, or a certificate from your internal CA); restrict the firewall rule to the private profile/subnet.
2. Back up `secret.key` separately from database backups (and protect both — backups contain investigation data).
3. Use PostgreSQL with a dedicated least-privilege role for multi-user deployments; run Docker as provided (non-root UID 10001).
4. Rotate Meta tokens periodically; prefer Page tokens with minimal permissions.
5. Keep dependencies current: CI runs the full test suite; re-run `pip-audit` and `npm audit` before each release.

## 4. Known limitations / accepted risks
| Item | Rationale |
|---|---|
| In-memory rate limiter | Per-process; sufficient for single-server deployments. Behind a load balancer use a shared limiter or the proxy's limits. |
| DNS-rebinding TOCTOU in enrichment | See 2.6. |
| `picomatch` ReDoS (dev tooling) | No upstream fix yet; not part of the shipped application. |
| Self-signed TLS by default in network mode | Trust must be established by installing the certificate on client devices. |
