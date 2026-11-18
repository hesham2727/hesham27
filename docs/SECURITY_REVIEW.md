# Security Review – Tahqiq MVP 1.0.0

Scope: backend API, consent page, React UI, desktop shell, deployment configurations. Reviewed against OWASP ASVS level-1 themes appropriate for a 1–5 user internal tool that exposes one public page.

## 1. Threat model (summary)

| Asset | Threats considered |
|---|---|
| Investigation data, customer records | Unauthorized access, tampering, leakage through exports |
| Shared locations (personal data) | Covert collection, over-retention, misrepresentation as "current" |
| Operator accounts | Password guessing, session theft, CSRF |
| Public consent page | Token guessing, replay, XSS, abuse/flooding |
| Host machine | Exposure of admin UI to the Internet |

## 2. Controls implemented

| Area | Control | Evidence |
|---|---|---|
| Passwords | scrypt (N=2^17, r=8, p=1, 16-byte salt), constant-time compare; dummy hash on unknown users to equalize timing; minimum 10 chars with letters and digits | `app/security.py`, `test_password_hash_roundtrip`, `test_setup_rejects_weak_password` |
| Brute force | Account lock 15 min after 5 failures; per-IP login rate limit (20 / 5 min) | `test_lockout` |
| Sessions | 256-bit random tokens, **only SHA-256 hash stored**; HttpOnly, SameSite=Strict, Secure when served over HTTPS; 12 h expiry; sessions revoked on password change, password reset and deactivation | `test_cookie_flags`, `test_roles_and_user_management`, `test_change_password` |
| CSRF | Mutating requests require `X-Requested-With: tahqiq` (forces CORS pre-flight, which is never granted) plus SameSite=Strict | `test_csrf_header_required` |
| Authorization | Roles admin/operator enforced server-side; admin-only: users, audit, settings, retention, deletions; admin cannot demote/deactivate self | `test_roles_and_user_management`, `test_admin_cannot_demote_self` |
| First-run takeover | `/auth/setup` only when no user exists **and** request comes from loopback (unless explicitly overridden) | `test_setup_refused_from_remote` |
| Input validation | Pydantic schemas with length limits, enums, coordinate ranges; URLs restricted to http/https (blocks `javascript:`); future dates rejected | `test_public_source_records`, `test_consent_validation` |
| Injection | SQLAlchemy ORM only; LIKE wildcards escaped | `test_validate_logs_history` (`%` search) |
| XSS | React escaping; consent page HTML-escapes all dynamic values; strict nonce-based CSP on consent page; app CSP `default-src 'self'` | `test_full_consent_flow` (CSP header) |
| Clickjacking & headers | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on API | `test_security_headers` |
| Exposure minimization | `create_public_app()` exposes only `/p/*` and `/api/health`; no docs/OpenAPI | `test_public_only_app_exposes_nothing_else` |
| Invitation tokens | 256-bit, hash-only storage, single use, expiry (1–168 h), revocable, consent-text version check, per-IP rate limit | `test_full_consent_flow`, `test_decline_and_revoke`, `test_expired_invitation` |
| Location integrity of claims | Never labelled current; fixed "CURRENT LOCATION UNAVAILABLE" statement in UI/PDF/Excel | `test_never_claims_location`, `test_full_consent_flow`, `test_xlsx_exports` |
| Internet Mode gate | HTTPS required; localhost/private/link-local/`.local`/single-label hosts rejected | `test_public_url_policy` (10 cases) |
| SSRF | Adapter endpoints fixed in code; API only toggles `enabled`; unknown adapters rejected; tile URL must be https | `test_adapter_endpoint_not_editable`, `test_map_tile_settings` |
| Audit | Logins (success/failure/locked), views, creates/updates/deletes, exports, invitation lifecycle, settings, retention | `test_audit_log_records_actions` |
| Retention | Configurable purge of locations, invitations, checks, closed investigations, audit logs, expired sessions | `test_retention_purges_old_data` |
| Dependencies | `pip-audit` and `npm audit` on 2026-11-18: **0 known vulnerabilities** after upgrading all pins to current releases | CI can repeat both commands |

## 3. Findings fixed during review

| # | Finding | Fix |
|---|---|---|
| 1 | Initial pins (Starlette 0.41) carried 7 published advisories | Upgraded backend and frontend dependencies to current releases; re-ran all tests, E2E and desktop build |
| 2 | Frontend toolchain (postcss, esbuild, react-router) had 6 npm advisories | Upgraded; `npm audit` clean |
| 3 | Adapter settings could have redirected reverse-geocoding requests to an arbitrary host | Endpoint no longer editable via API |
| 4 | E.164 was reported for invalid-but-possible numbers, implying existence | E.164 only returned for valid numbers |

## 4. Residual risks (accepted for MVP, with mitigations)

| Risk | Level | Mitigation / recommendation |
|---|---|---|
| SQLite database is not encrypted at rest | Medium | Enable Windows BitLocker / Device Encryption where available; restrict the Windows account; encrypted backups |
| Location coordinates are self-reported by the customer's device and can be spoofed (fake-GPS apps) | Medium | Treat as customer-declared evidence, not proof; accuracy and consent evidence (time, IP, user agent) recorded |
| Messaging apps' link previews may fetch the invitation page and set status to "opened" | Low | Only explicit accept/decline changes the outcome; "opened" is informational |
| No multi-factor authentication | Medium (Internet/VPS mode) | Keep the admin UI off the Internet (public-only app); on a VPS, add Caddy IP allow-list or VPN |
| All operators see all investigations (no per-record ACL) | Low for 1–5 trusted users | Add ownership scoping if the team grows |
| Rate-limit and lock-out counters for IPs are in memory | Low | Account lock-out is persisted in the database; process restart only resets IP counters |
| LAN mode over plain HTTP | Medium | Use only on trusted networks or Caddy `tls internal` |
| Installer not code-signed | Low | Verify the SHA-256 of the installer from CI; signing requires a paid certificate (not approved) |
| Audit log can be altered by someone with file-system access to the DB | Low | OS-level access control; periodic export of audit log to read-only storage |
| Other local processes can reach the desktop backend port on 127.0.0.1 | Low | Authentication is still required for all data |

## 5. Legal and privacy notes (not legal advice)

* Location is collected only with explicit, informed, revocable consent, for a stated purpose, once, and deleted per retention settings – aligned with the principles of Egypt's Personal Data Protection Law No. 151 of 2020. Obtain legal counsel's confirmation of your specific use and any registration/licensing obligations.
* The application contains no covert tracking, no telecom-network access, and no capability to derive a location from a number.

## 6. How to re-run the checks

```bash
cd backend && ../.venv/bin/python -m pytest
../.venv/bin/pip install pip-audit && ../.venv/bin/pip-audit -r requirements.txt
cd ../frontend && npm audit
```
