# FBOSINT Analyzer — REST API reference

Version 1.0.0. Interactive documentation: `http://<server>:8765/api/docs` (Swagger UI). Machine-readable schema: `/api/openapi.json`.

## Authentication

* **Web (browser):** `POST /api/auth/login` with `client: "web"` sets an HttpOnly `fbo_session` cookie and a readable `fbo_csrf` cookie. Every POST/PUT/PATCH/DELETE must send header `X-CSRF-Token: <fbo_csrf>`.
* **Desktop / scripts:** `POST /api/auth/login` with `client: "desktop"` returns `token`; send `Authorization: Bearer <token>`. No CSRF header required.
* Sessions expire after `FBO_SESSION_TTL_HOURS` (12) or `FBO_SESSION_IDLE_MINUTES` (60) of inactivity.
* Roles: `admin` (everything), `investigator` (create; modify own investigations), `viewer` (read & export).

## Errors

JSON `{"detail": "<code>"}`. Common codes: `not_authenticated` 401, `session_invalid_or_expired` 401, `csrf_token_invalid` 403, `insufficient_role` 403, `not_owner` 403, `investigation_not_found` 404, `investigation_running` 409, `validation_error` 422 (with `errors[]`), `account_locked` 423, `rate_limited` 429 (with `Retry-After`).

## Endpoints

### `GET /api/admin/audit`

Audit Log — access: **admin**

| Parameter | In | Type | Required |
|---|---|---|---|
| `action` | query | string | no |
| `username` | query | string | no |
| `page` | query | integer | no |
| `page_size` | query | integer | no |

### `GET /api/admin/backups`

Backups — access: **admin**

### `POST /api/admin/backups`

Make Backup — access: **admin**

### `GET /api/admin/backups/{name}`

Download Backup — access: **admin**

| Parameter | In | Type | Required |
|---|---|---|---|
| `name` | path | string | yes |

### `POST /api/admin/retention/run`

Run Retention — access: **admin**

### `GET /api/admin/users`

List Users — access: **admin**

### `POST /api/admin/users`

Create User — access: **admin**

Body (`application/json`) `UserCreate`: `username`, `password`, `full_name`, `language`, `role`

### `PATCH /api/admin/users/{user_id}`

Update User — access: **admin**

| Parameter | In | Type | Required |
|---|---|---|---|
| `user_id` | path | integer | yes |

Body (`application/json`) `UserUpdate`: `full_name`, `role`, `is_active`, `language`, `password`

### `POST /api/auth/change-password`

Change Password — access: **authenticated**

Body (`application/json`) `PasswordChange`: `current_password`, `new_password`

### `GET /api/auth/csrf`

Csrf — access: **authenticated**

### `POST /api/auth/login`

Login — access: **public (rate-limited)**

Body (`application/json`) `LoginIn`: `username`, `password`, `client`

### `POST /api/auth/logout`

Logout — access: **authenticated**

### `GET /api/auth/me`

Me — access: **authenticated**

### `PUT /api/auth/preferences`

Preferences — access: **authenticated**

Body (`application/json`) `PreferencesIn`: `language`

### `POST /api/auth/setup`

First Run Setup — access: **public (first run only)**

Body (`application/json`) `SetupIn`: `username`, `password`, `full_name`, `language`

### `GET /api/auth/setup-status`

Setup Status — access: **public (first run only)**

### `GET /api/dashboard`

Dashboard — access: **authenticated**

### `GET /api/health`

Health — access: **public**

### `GET /api/investigations`

List Investigations — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `q` | query | string | no |
| `status` | query | string `^(|pending|running|completed|partial|failed)$` | no |
| `mine` | query | boolean | no |
| `page` | query | integer | no |
| `page_size` | query | integer | no |

### `POST /api/investigations`

Create Investigation — access: **authenticated**

Body (`application/json`) `InvestigationCreate`: `target`, `target_type`, `title`, `purpose`, `legal_basis`, `notes`, `extra_urls`, `options`, `start`

### `GET /api/investigations/{inv_id}`

Get Investigation — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

### `PATCH /api/investigations/{inv_id}`

Update Investigation — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

Body (`application/json`) `InvestigationUpdate`: `title`, `notes`, `purpose`, `legal_basis`

### `DELETE /api/investigations/{inv_id}`

Remove Investigation — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

### `GET /api/investigations/{inv_id}/datapoints`

List Datapoints — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |
| `category` | query | string `^(|profile|contact|business|identifier|link|observation)$` | no |

### `POST /api/investigations/{inv_id}/datapoints`

Add Manual Datapoint — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

Body (`application/json`) `DataPointCreate`: `category`, `field`, `value`, `source_url`, `notes`, `classification`

### `DELETE /api/investigations/{inv_id}/datapoints/{dp_id}`

Delete Manual Datapoint — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |
| `dp_id` | path | integer | yes |

### `PATCH /api/investigations/{inv_id}/datapoints/{dp_id}/review`

Review Datapoint — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |
| `dp_id` | path | integer | yes |

Body (`application/json`) `DataPointReview`: `verification_status`, `confidence`, `notes`

### `GET /api/investigations/{inv_id}/events`

List Events — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

### `GET /api/investigations/{inv_id}/media`

List Media — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

### `POST /api/investigations/{inv_id}/media/upload`

Upload Media — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |
| `caption` | query | string | no |
| `source_url` | query | string | no |

Body (`multipart/form-data`) `Body_upload_media_api_investigations__inv_id__media_upload_post`: `file`

### `GET /api/investigations/{inv_id}/media/{media_id}/file`

Media File — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |
| `media_id` | path | integer | yes |

### `GET /api/investigations/{inv_id}/posts`

List Posts — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |
| `q` | query | string | no |
| `date_from` | query | string/null | no |
| `date_to` | query | string/null | no |
| `kind` | query | string `^(|post|comment)$` | no |
| `order` | query | string `^(asc|desc)$` | no |
| `limit` | query | integer | no |
| `offset` | query | integer | no |

### `GET /api/investigations/{inv_id}/report`

Export Report — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |
| `format` | query | string `^(pdf|xlsx)$` | no |
| `lang` | query | string `^(ar|en)$` | no |

### `POST /api/investigations/{inv_id}/run`

Rerun — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

### `GET /api/investigations/{inv_id}/sources`

List Sources — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

### `GET /api/investigations/{inv_id}/timeline`

Timeline — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

### `POST /api/investigations/{inv_id}/urls`

Add Urls — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `inv_id` | path | integer | yes |

Body (`application/json`) `AddUrlsIn`: `urls`, `run`

### `DELETE /api/meta/connection`

Disconnect — access: **authenticated**

### `GET /api/meta/oauth/callback`

Oauth Callback — access: **public (state-validated)**

| Parameter | In | Type | Required |
|---|---|---|---|
| `state` | query | string | yes |
| `code` | query | string | no |
| `error` | query | string | no |

### `POST /api/meta/oauth/start`

Oauth Start — access: **authenticated**

| Parameter | In | Type | Required |
|---|---|---|---|
| `scopes` | query | string `^[a-z_,]*$` | no |

### `GET /api/settings`

Get App Settings — access: **authenticated**

### `PUT /api/settings`

Update App Settings — access: **authenticated**

Body (`application/json`) `AppSettingsIn`: `retention_days`, `graph_version`, `default_language`, `backup_keep`, `duplicate_threshold`

### `PUT /api/settings/meta`

Update Meta — access: **admin (PUT/POST)**

Body (`application/json`) `MetaCredentialsIn`: `app_id`, `app_secret`, `access_token`, `redirect_uri`

### `POST /api/settings/meta/test`

Test Meta — access: **admin (PUT/POST)**
