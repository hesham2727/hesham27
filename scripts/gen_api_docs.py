"""Generate docs/API.md from the application's OpenAPI schema."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fbosint.config import load_settings, set_settings  # noqa: E402

set_settings(load_settings({"FBO_DATA_DIR": tempfile.mkdtemp()}))
from fbosint.main import create_app  # noqa: E402

spec = create_app().openapi()
ROLES = {
    "/api/admin": "admin", "/api/settings/meta": "admin (PUT/POST)", "/api/health": "public", "/api/auth/setup": "public (first run only)",
    "/api/auth/login": "public (rate-limited)", "/api/auth/setup-status": "public", "/api/meta/oauth/callback": "public (state-validated)",
}
lines = [
    "# FBOSINT Analyzer — REST API reference", "",
    f"Version {spec['info']['version']}. Interactive documentation: `http://<server>:8765/api/docs` (Swagger UI). Machine-readable schema: `/api/openapi.json`.", "",
    "## Authentication", "",
    "* **Web (browser):** `POST /api/auth/login` with `client: \"web\"` sets an HttpOnly `fbo_session` cookie and a readable `fbo_csrf` cookie. Every POST/PUT/PATCH/DELETE must send header `X-CSRF-Token: <fbo_csrf>`.",
    "* **Desktop / scripts:** `POST /api/auth/login` with `client: \"desktop\"` returns `token`; send `Authorization: Bearer <token>`. No CSRF header required.",
    "* Sessions expire after `FBO_SESSION_TTL_HOURS` (12) or `FBO_SESSION_IDLE_MINUTES` (60) of inactivity.",
    "* Roles: `admin` (everything), `investigator` (create; modify own investigations), `viewer` (read & export).", "",
    "## Errors", "",
    "JSON `{\"detail\": \"<code>\"}`. Common codes: `not_authenticated` 401, `session_invalid_or_expired` 401, `csrf_token_invalid` 403, `insufficient_role` 403, `not_owner` 403, `investigation_not_found` 404, `investigation_running` 409, `validation_error` 422 (with `errors[]`), `account_locked` 423, `rate_limited` 429 (with `Retry-After`).", "",
    "## Endpoints", "",
]
for path, ops in sorted(spec["paths"].items()):
    for method, op in ops.items():
        access = next((v for k, v in ROLES.items() if path.startswith(k)), "authenticated")
        lines.append(f"### `{method.upper()} {path}`")
        lines.append("")
        lines.append(f"{op.get('summary', '')} — access: **{access}**")
        params = [p for p in op.get("parameters", []) if p.get("in") in ("query", "path")]
        if params:
            lines.append("")
            lines.append("| Parameter | In | Type | Required |")
            lines.append("|---|---|---|---|")
            for p in params:
                sch = p.get("schema", {})
                typ = sch.get("type") or "/".join(x.get("type", "") for x in sch.get("anyOf", []))
                if sch.get("pattern"):
                    typ += f" `{sch['pattern']}`"
                lines.append(f"| `{p['name']}` | {p['in']} | {typ} | {'yes' if p.get('required') else 'no'} |")
        body = op.get("requestBody", {}).get("content", {})
        for ct, c in body.items():
            ref = c.get("schema", {}).get("$ref", "")
            if ref:
                name = ref.split("/")[-1]
                props = spec["components"]["schemas"][name].get("properties", {})
                lines.append("")
                lines.append(f"Body (`{ct}`) `{name}`: " + ", ".join(f"`{k}`" for k in props))
            elif ct.startswith("multipart"):
                lines.append("")
                lines.append("Body: multipart form with `file`")
        lines.append("")
(ROOT / "docs" / "API.md").write_text("\n".join(lines), encoding="utf-8")
print("written docs/API.md")
