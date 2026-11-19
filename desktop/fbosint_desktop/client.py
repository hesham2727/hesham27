"""REST client: the desktop app holds NO business logic; it calls the shared API."""
from __future__ import annotations

from typing import Any

import httpx

from . import __version__


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def direct_connection(url: str) -> bool:
    """True for the built-in server and LAN servers: such requests must never go through a
    system/corporate proxy (on Windows, httpx reads the Internet Options proxy from the registry,
    which made http://127.0.0.1 unreachable on machines with a proxy configured)."""
    import ipaddress
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").strip("[]").lower()
    if host in ("localhost", "") or host.endswith((".local", ".lan", ".home", ".internal", ".corp")) or "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        return False


class ApiClient:
    def __init__(self, base_url: str, verify: bool | str = True, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = ""
        self.user: dict[str, Any] = {}
        self.http = httpx.Client(base_url=self.base_url, verify=verify, timeout=timeout, transport=transport, trust_env=not direct_connection(self.base_url), headers={"User-Agent": f"FBOSINT-Desktop/{__version__}"})

    def close(self) -> None:
        self.http.close()

    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        headers = kw.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = self.http.request(method, path, headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise ApiError(0, "network") from exc
        if r.status_code >= 400:
            code = "generic"
            try:
                d = r.json().get("detail")
                code = d if isinstance(d, str) else (d[0] if isinstance(d, list) and d and isinstance(d[0], str) else (d.get("message") if isinstance(d, dict) else "generic"))
            except ValueError:
                pass
            raise ApiError(r.status_code, str(code))
        return r

    def get(self, path: str, **params) -> Any:
        return self._req("GET", path, params={k: v for k, v in params.items() if v not in (None, "")}).json()

    def post(self, path: str, body: Any = None, **kw) -> Any:
        r = self._req("POST", path, json=body, **kw)
        return r.json() if r.content else None

    def put(self, path: str, body: Any) -> Any:
        return self._req("PUT", path, json=body).json()

    def patch(self, path: str, body: Any) -> Any:
        return self._req("PATCH", path, json=body).json()

    def delete(self, path: str) -> None:
        self._req("DELETE", path)

    def download(self, path: str, **params) -> tuple[bytes, str]:
        r = self._req("GET", path, params=params)
        cd = r.headers.get("content-disposition", "")
        name = cd.split("filename=")[-1].strip('"') if "filename=" in cd else "download.bin"
        return r.content, name

    # ---- auth ----
    def health(self) -> dict:
        return self.get("/api/health")

    def needs_setup(self) -> bool:
        return bool(self.get("/api/auth/setup-status")["needs_setup"])

    def setup(self, username: str, password: str, full_name: str = "") -> None:
        self.post("/api/auth/setup", {"username": username, "password": password, "full_name": full_name})

    def login(self, username: str, password: str) -> dict:
        r = self.post("/api/auth/login", {"username": username, "password": password, "client": "desktop"})
        self.token = r["token"]
        self.user = r["user"]
        return self.user

    def logout(self) -> None:
        if self.token:
            try:
                self.post("/api/auth/logout")
            finally:
                self.token = ""
