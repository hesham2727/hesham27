# FBOSINT Analyzer — System Architecture

## 1. Design principles

1. **Lawful collection only.** Every data point comes from (a) Meta's official Graph API using a
   token the operator is entitled to use, (b) a public URL the investigator supplied explicitly, or
   (c) a manual observation the investigator typed in with its source URL. Nothing else.
2. **One engine, two front-ends.** All business logic lives in the Python package `fbosint`
   (backend). The React web app and the PySide6 desktop app are thin REST clients of the same API.
3. **Source attribution everywhere.** Every fact, post, media item and contact carries its
   `source_url`, `source_type`, `collected_at`, `verification_status` and `confidence`.
4. **Facts ≠ observations.** Each data point is classified as `fact`, `unverified` or
   `analytical_observation`; reports print the three groups separately.
5. **No identity inference.** The system never links two profiles, never runs facial recognition,
   and never infers private contact details.

## 2. Component diagram

```
 ┌───────────────────────┐        ┌──────────────────────────┐
 │ Web UI (React + TS)    │        │ Desktop UI (PySide6)      │
 │ cookie session + CSRF  │        │ bearer token              │
 └──────────┬────────────┘        └────────────┬─────────────┘
            │ HTTPS/HTTP REST /api/*            │ (Local mode: embedded server
            ▼                                   ▼  on 127.0.0.1 in a thread)
 ┌──────────────────────────────────────────────────────────────┐
 │ FastAPI app (fbosint.main)                                    │
 │  middleware: security headers · rate limiter · request IDs    │
 │  api/: auth · investigations · media · reports · settings ·   │
 │        admin(users, audit, backup, retention) · meta oauth     │
 ├──────────────────────────────────────────────────────────────┤
 │ services/                                                     │
 │  url_parser → investigation_engine ─┬─ graph_client (Meta)    │
 │                                     ├─ enrichment (safe_fetch, │
 │                                     │   robots.txt, SSRF guard)│
 │                                     ├─ contacts extraction     │
 │                                     ├─ media (pHash, EXIF)     │
 │                                     └─ verification engine     │
 │  reports/ pdf (Arabic shaping) · excel                        │
 │  backup · retention · audit                                   │
 ├──────────────────────────────────────────────────────────────┤
 │ SQLAlchemy 2 ORM → SQLite (default) | PostgreSQL (network)    │
 │ data dir: db, media/, backups/, reports cache, secret.key     │
 └──────────────────────────────────────────────────────────────┘
```

## 3. Deployment modes

| Mode | Backend | Database | Clients |
|---|---|---|---|
| **Local** | Started inside the desktop app on `127.0.0.1:8765` (or `FBOSINT-Server.exe`) | SQLite in `%APPDATA%\FBOSINT` | Desktop app + browser at `http://127.0.0.1:8765` |
| **Network** | `FBOSINT-Server.exe --host 0.0.0.0` (or Docker) on a designated machine, TLS recommended | SQLite or PostgreSQL on the server | Desktop apps configured with the server URL + any browser on the LAN |

Because both UIs call the same API against the same database, investigation records are
synchronised by construction (there is no second copy to reconcile).

## 4. Meta Graph API — what is and is not possible

> Verified against Meta's public developer documentation as known at the time of writing.
> Meta changes permissions and features frequently; check
> https://developers.facebook.com/docs/graph-api before production use. The Graph API version is
> configurable (`FBO_META_GRAPH_VERSION`).

### 4.1 Personal profiles (the most important limitation)

* Since Graph API v2.0 (2014) there is **no endpoint that returns data about an arbitrary
  person** by URL, username or ID. Usernames were removed from the API, and user IDs are
  app-scoped.
* An app can only read a person's data if **that person logs into the app (Facebook Login)** and
  grants permissions. `public_profile` (id, name, picture) is default; `email`, `user_link`,
  `user_location`, `user_hometown`, `user_posts`, `user_photos`, `user_videos`, etc. require
  Meta App Review.
* Work, education, relationship and religion fields were removed from the API for all apps.

**Consequence in this application:** for a personal-profile URL the tool records the URL and
the identifier visible in the URL, attempts the official lookup, and when Meta refuses (as it
will) records every profile field as `unavailable` with the Meta error as evidence. The
investigator can then add **manual observations** (with source URL) and supply other public URLs
for enrichment. The only way to get real Graph data for a person is the
"Authorized Facebook account" mode, where the person themself connects via OAuth.

### 4.2 Facebook Pages

* `GET /{page-id|page-username}?fields=...` works for Pages the token can see:
  * Pages you manage → Page access token (`pages_read_engagement`, `pages_show_list`).
  * Pages you don't manage → requires the **Page Public Metadata Access** (metadata only) or
    **Page Public Content Access** (posts, photos) *features*, granted after App Review and
    Business Verification.
* Typical fields: `id, name, username, link, about, description, category, website, emails,
  phone, single_line_address, location, founded, fan_count, followers_count, picture, cover`.
  Some are absent when the Page hasn't published them → reported as `undisclosed`.
* Posts: `/{page-id}/posts`; photos: `/{page-id}/photos?type=uploaded`; comments on posts need
  additional permission and are often redacted (no commenter identity) for non-managed Pages.

### 4.3 Rate limits and errors handled

| Code | Meaning | Handling |
|---|---|---|
| 4, 17, 32, 613, 80001-80014 | App / user / page / BUC rate limit | stop that collection step, record `rate_limited`, mark investigation `partial`, surface `X-App-Usage` / `X-Business-Use-Case-Usage` headers |
| 190 | Invalid/expired token | `auth_error`, prompt to reconnect |
| 10, 200-299 | Permission missing | `not_permitted` with the missing permission message |
| 100 (nonexisting field) | Field not available for object type | drop field and retry (max 5) |
| 100/803 (object not found / unsupported get) | Not a Page, private, deleted or personal profile | all fields `unavailable` |

The client also sends `appsecret_proof` when the App Secret is configured.

### 4.4 Explicitly out of scope (by design)

HTML scraping of facebook.com, headless browsers, unofficial endpoints, CAPTCHA solving, login
with someone's password, facial recognition, linking profiles by name/photo similarity,
private phone numbers / addresses / messages. The enrichment fetcher **refuses** Facebook,
Instagram, Messenger and WhatsApp domains so that it cannot be used as a Facebook scraper.

## 5. Enrichment (user-supplied public URLs)

* Only `http(s)`, standard ports, max 5 redirects, max 2 MB, 15 s timeout.
* DNS is resolved and every hop is checked against private/loopback/link-local/reserved ranges
  (SSRF protection).
* `robots.txt` is honoured for the configured User-Agent.
* Extraction: title, meta description, OpenGraph, schema.org JSON-LD (Organization /
  LocalBusiness / Person `telephone`, `email`, `address`, `url`, `sameAs`), `mailto:` and `tel:`
  links, and e-mail addresses printed in visible text (lower confidence).
* `sameAs` / social links are recorded as *related links, association unverified*.

## 6. Verification & confidence model

| Situation | verification_status | confidence |
|---|---|---|
| Returned by Graph API for the object itself | verified | high |
| Same normalised value from ≥2 independent domains | verified | high |
| Structured, explicit publication (JSON-LD, mailto:, tel:) on one site | unverified | medium |
| Regex match in page text / manual observation | unverified | low |
| Same field, different values across sources | conflicting | low |
| Investigator manually confirms with note | verified (manual) | as set |

Availability of each profile field: `available`, `undisclosed` (source accessible, value not
published), `unavailable` (source refused / not permitted / not found).

## 7. Security architecture (summary — full review in SECURITY_REVIEW.md)

* scrypt password hashing, account lockout, rate-limited login.
* Server-side sessions (random 256-bit token, only SHA-256 stored), absolute + idle timeout,
  logout revocation. Web: HttpOnly SameSite=Strict cookie + double-submit CSRF header.
  Desktop: bearer token (no ambient credentials → no CSRF surface).
* RBAC: `admin`, `investigator`, `viewer`.
* Meta App Secret and access tokens encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256);
  key from `FBO_ENCRYPTION_KEY` or a generated key file with owner-only permissions.
* ORM-parameterised queries only, Pydantic validation on every input, LIKE wildcards escaped.
* Strict CSP, `X-Frame-Options: DENY`, `nosniff`; React escapes output; no `dangerouslySetInnerHTML`.
* Append-only audit log for logins, investigations, exports, deletions, settings changes.
* Retention policy (auto purge after N days) + hard delete including media files.

## 8. Data model

See `docs/schema.sql` (generated from the ORM) and `fbosint/models.py`.
Core tables: `users`, `sessions`, `investigations`, `data_points`, `posts`, `media_items`,
`sources`, `collection_events`, `audit_logs`, `app_settings`, `encrypted_credentials`,
`oauth_states`, `report_exports`.
