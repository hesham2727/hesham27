"""Minimal, strict client for Meta's official Graph API.

Only ``graph.facebook.com`` is ever contacted. Pagination URLs returned by
Meta are validated to stay on that host. Errors are mapped to typed
exceptions so the engine can record precise limitations.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

GRAPH_HOST = "graph.facebook.com"
RATE_LIMIT_CODES = {4, 17, 32, 613} | set(range(80001, 80015))
PERMISSION_CODES = {10} | set(range(200, 300))

PAGE_FIELDS = [
    "id", "name", "username", "link", "about", "description", "category", "category_list", "website",
    "emails", "phone", "single_line_address", "location", "founded", "fan_count", "followers_count",
    "verification_status", "picture.type(large){url,width,height,is_silhouette}", "cover{source,id}",
]
USER_FIELDS = ["id", "name", "link", "picture.type(large){url,width,height,is_silhouette}", "email", "location", "hometown"]
POST_FIELDS = "id,message,created_time,permalink_url,status_type,attachments{type,url,unshimmed_url,media_type,media{image{src,width,height}}}"
PHOTO_FIELDS = "id,name,created_time,link,images,width,height"


class GraphError(Exception):
    kind = "error"

    def __init__(self, message: str, code: int | None = None, subcode: int | None = None, status: int | None = None, usage: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.subcode = subcode
        self.status = status
        self.usage = usage or {}

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "code": self.code, "subcode": self.subcode, "http_status": self.status, "usage": self.usage}


class GraphAuthError(GraphError):
    kind = "auth_error"


class GraphPermissionError(GraphError):
    kind = "not_permitted"


class GraphRateLimitError(GraphError):
    kind = "rate_limited"


class GraphNotFoundError(GraphError):
    kind = "not_found"


class GraphFieldError(GraphError):
    kind = "invalid_field"

    def __init__(self, *a, bad_field: str = "", **kw) -> None:
        super().__init__(*a, **kw)
        self.bad_field = bad_field


class GraphNotConfigured(GraphError):
    kind = "not_configured"


_BAD_FIELD_RE = re.compile(r"nonexisting field \((\w+)\)", re.I)


@dataclass
class GraphResult:
    data: dict[str, Any]
    url: str
    usage: dict[str, Any] = field(default_factory=dict)


class MetaGraphClient:
    def __init__(
        self,
        access_token: str,
        version: str = "v23.0",
        app_secret: str = "",
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 2,
        sleep=time.sleep,
    ) -> None:
        if not access_token:
            raise GraphNotConfigured("meta_access_token_not_configured")
        self.token = access_token
        self.version = version
        self.app_secret = app_secret
        self.max_retries = max_retries
        self._sleep = sleep
        self.base = f"https://{GRAPH_HOST}/{version}"
        self.http = httpx.Client(timeout=timeout, transport=transport, follow_redirects=False, headers={"Accept": "application/json"})
        self.calls = 0

    def close(self) -> None:
        self.http.close()

    # ---------- low level ----------
    def _auth_params(self) -> dict[str, str]:
        p = {"access_token": self.token}
        if self.app_secret:
            p["appsecret_proof"] = hmac.new(self.app_secret.encode(), self.token.encode(), hashlib.sha256).hexdigest()
        return p

    @staticmethod
    def _usage(resp: httpx.Response) -> dict[str, Any]:
        out = {}
        for h in ("x-app-usage", "x-business-use-case-usage", "x-page-usage", "x-ad-account-usage"):
            if h in resp.headers:
                try:
                    out[h] = json.loads(resp.headers[h])
                except ValueError:
                    out[h] = resp.headers[h]
        return out

    def _raise_for(self, resp: httpx.Response, usage: dict) -> None:
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        msg = str(err.get("message") or f"HTTP {resp.status_code}")[:500]
        code = err.get("code")
        sub = err.get("error_subcode")
        kw = dict(code=code, subcode=sub, status=resp.status_code, usage=usage)
        if code in RATE_LIMIT_CODES or resp.status_code == 429:
            raise GraphRateLimitError(msg, **kw)
        if code == 190 or err.get("type") == "OAuthException" and code in (102, 463, 467):
            raise GraphAuthError(msg, **kw)
        if code in PERMISSION_CODES:
            raise GraphPermissionError(msg, **kw)
        if code == 100:
            m = _BAD_FIELD_RE.search(msg)
            if m:
                raise GraphFieldError(msg, bad_field=m.group(1), **kw)
            if sub == 33 or "does not exist" in msg or "Unsupported get request" in msg:
                raise GraphNotFoundError(msg, **kw)
        if code == 803 or resp.status_code == 404:
            raise GraphNotFoundError(msg, **kw)
        raise GraphError(msg, **kw)

    def _request(self, url: str, params: dict[str, Any] | None = None) -> GraphResult:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != GRAPH_HOST:
            raise GraphError("refused_non_graph_url")
        from urllib.parse import parse_qsl

        q = dict(parse_qsl(parts.query))  # keep cursor params of paging.next URLs
        q.update(params or {})
        q.update(self._auth_params())
        url = f"{parts.scheme}://{parts.netloc}{parts.path}"
        attempt = 0
        while True:
            self.calls += 1
            try:
                resp = self.http.get(url, params=q)
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    attempt += 1
                    self._sleep(min(2 ** attempt, 8))
                    continue
                raise GraphError(f"network_error: {type(exc).__name__}") from exc
            usage = self._usage(resp)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise GraphError("invalid_json_response") from exc
                return GraphResult(data=data, url=url, usage=usage)  # attribution URL: endpoint path only, never tokens
            # transient server errors: limited retry; rate limits are NOT retried aggressively
            if resp.status_code >= 500 and attempt < self.max_retries:
                attempt += 1
                self._sleep(min(2 ** attempt, 8))
                continue
            self._raise_for(resp, usage)

    def get(self, path: str, **params: Any) -> GraphResult:
        path = path.lstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", path):
            raise GraphError("invalid_graph_path")
        return self._request(f"{self.base}/{path}", params)

    # ---------- high level ----------
    def get_object_tolerant(self, obj: str, fields: list[str]) -> tuple[GraphResult, list[str]]:
        """Fetch an object; drop fields Meta reports as nonexisting (max 5 retries)."""
        fields = list(fields)
        dropped: list[str] = []
        for _ in range(6):
            try:
                return self.get(obj, fields=",".join(fields)), dropped
            except GraphFieldError as e:
                bad = next((f for f in fields if f.split(".")[0].split("{")[0] == e.bad_field), None)
                if not bad:
                    raise
                fields.remove(bad)
                dropped.append(e.bad_field)
        raise GraphError("too_many_invalid_fields")

    def get_page(self, alias: str) -> tuple[GraphResult, list[str]]:
        return self.get_object_tolerant(alias, PAGE_FIELDS)

    def get_me(self) -> tuple[GraphResult, list[str]]:
        return self.get_object_tolerant("me", USER_FIELDS)

    def permissions(self) -> list[dict[str, str]]:
        return self.get("me/permissions").data.get("data", [])

    def paginate(self, path: str, limit: int, **params: Any) -> tuple[list[dict], str]:
        """Follow ``paging.next`` (validated) until ``limit`` items. Returns (items, first_url)."""
        items: list[dict] = []
        params.setdefault("limit", min(100, max(limit, 1)))
        first = self.get(path, **params)
        page = first
        while True:
            items.extend(page.data.get("data", []))
            nxt = page.data.get("paging", {}).get("next")
            if len(items) >= limit or not nxt:
                break
            page = self._request(nxt)  # host validated in _request
        return items[:limit], first.url

    def page_posts(self, page_id: str, limit: int) -> tuple[list[dict], str]:
        return self.paginate(f"{page_id}/posts", limit, fields=POST_FIELDS)

    def user_posts(self, limit: int) -> tuple[list[dict], str]:
        return self.paginate("me/posts", limit, fields=POST_FIELDS)

    def photos(self, obj_id: str, limit: int) -> tuple[list[dict], str]:
        return self.paginate(f"{obj_id}/photos", limit, fields=PHOTO_FIELDS, type="uploaded")

    def comments(self, post_id: str, limit: int) -> tuple[list[dict], str]:
        return self.paginate(f"{post_id}/comments", limit, fields="id,message,created_time,permalink_url", filter="toplevel")


def debug_token(app_id: str, app_secret: str, token: str, version: str = "v23.0", transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Inspect a token with the app access token (``/debug_token``)."""
    with httpx.Client(timeout=15, transport=transport) as http:
        r = http.get(f"https://{GRAPH_HOST}/{version}/debug_token", params={"input_token": token, "access_token": f"{app_id}|{app_secret}"})
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")
        except ValueError:
            msg = f"HTTP {r.status_code}"
        raise GraphError(msg, status=r.status_code)
    d = r.json().get("data", {})
    return {k: d.get(k) for k in ("app_id", "type", "application", "is_valid", "expires_at", "data_access_expires_at", "scopes", "user_id", "profile_id")}


def exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str, version: str = "v23.0", transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """OAuth: exchange an authorisation code for a user access token."""
    with httpx.Client(timeout=15, transport=transport) as http:
        r = http.get(
            f"https://{GRAPH_HOST}/{version}/oauth/access_token",
            params={"client_id": app_id, "client_secret": app_secret, "redirect_uri": redirect_uri, "code": code},
        )
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")
        except ValueError:
            msg = f"HTTP {r.status_code}"
        raise GraphAuthError(msg, status=r.status_code)
    return r.json()
