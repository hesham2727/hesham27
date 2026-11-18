"""Hardened HTTP fetcher for investigator-supplied public URLs.

* http/https only, default ports only, no credentials in URL
* DNS resolved and every hop checked against private / reserved ranges (SSRF)
* robots.txt honoured for our User-Agent
* Facebook-family domains refused (no scraping of Facebook)
* size, time and redirect limits
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

BLOCKED_DOMAINS = (
    "facebook.com", "fb.com", "fb.me", "fbcdn.net", "messenger.com", "instagram.com", "whatsapp.com",
    "whatsapp.net", "threads.net", "meta.com",
)
Resolver = Callable[[str], list[str]]


class FetchBlocked(Exception):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status  # blocked_policy | blocked_robots | error
        self.message = message


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def text(self) -> str:
        enc = "utf-8"
        ct = self.content_type.lower()
        if "charset=" in ct:
            enc = ct.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.content.decode(enc, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


def default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({i[4][0] for i in infos})


def is_blocked_domain(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def _ip_is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


class SafeFetcher:
    def __init__(
        self,
        user_agent: str,
        timeout: float = 15.0,
        max_bytes: int = 2_000_000,
        max_redirects: int = 5,
        allow_private: bool = False,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = default_resolver,
        respect_robots: bool = True,
        allow_blocked_domains: bool = False,
    ) -> None:
        self.ua = user_agent
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.allow_private = allow_private
        self.resolver = resolver
        self.respect_robots = respect_robots
        self.allow_blocked_domains = allow_blocked_domains
        self.http = httpx.Client(timeout=timeout, transport=transport, follow_redirects=False, headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,image/*;q=0.8,*/*;q=0.5"})
        self._robots: dict[str, RobotFileParser | None] = {}

    def close(self) -> None:
        self.http.close()

    def validate_url(self, url: str) -> None:
        try:
            p = urlsplit(url)
        except ValueError as exc:
            raise FetchBlocked("blocked_policy", "invalid_url") from exc
        if p.scheme not in ("http", "https"):
            raise FetchBlocked("blocked_policy", "scheme_not_allowed")
        if not p.hostname:
            raise FetchBlocked("blocked_policy", "missing_host")
        if p.username or p.password:
            raise FetchBlocked("blocked_policy", "credentials_in_url_not_allowed")
        if p.port not in (None, 80, 443, 8080, 8443):
            raise FetchBlocked("blocked_policy", "port_not_allowed")
        if not self.allow_blocked_domains and is_blocked_domain(p.hostname):
            raise FetchBlocked("blocked_policy", "facebook_family_domain_not_fetched")
        host = p.hostname
        try:
            ips = [host] if _looks_like_ip(host) else self.resolver(host)
        except OSError as exc:
            raise FetchBlocked("error", "dns_resolution_failed") from exc
        if not ips:
            raise FetchBlocked("error", "dns_resolution_failed")
        if not self.allow_private and not all(_ip_is_public(ip) for ip in ips):
            raise FetchBlocked("blocked_policy", "private_or_reserved_address")

    def _robots_allows(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                r = self._get_raw(origin + "/robots.txt", limit=500_000)
                if r.status_code in (401, 403):
                    rp.disallow_all = True  # type: ignore[union-attr]
                elif r.status_code >= 400:
                    rp = None  # no robots.txt => allowed
                else:
                    rp.parse(r.content.decode("utf-8", errors="replace").splitlines())  # type: ignore[union-attr]
            except (FetchBlocked, httpx.HTTPError):
                rp = None
            self._robots[origin] = rp
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(self.ua, url)

    def _get_raw(self, url: str, limit: int) -> FetchResult:
        current = url
        for _ in range(self.max_redirects + 1):
            self.validate_url(current)
            with self.http.stream("GET", current) as resp:
                if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                    current = urljoin(current, resp.headers["location"])
                    continue
                cl = resp.headers.get("content-length")
                if cl and cl.isdigit() and int(cl) > limit:
                    raise FetchBlocked("error", "response_too_large")
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > limit:
                        raise FetchBlocked("error", "response_too_large")
                return FetchResult(url, current, resp.status_code, resp.headers.get("content-type", ""), bytes(buf))
        raise FetchBlocked("error", "too_many_redirects")

    def fetch(self, url: str, max_bytes: int | None = None) -> FetchResult:
        self.validate_url(url)
        if not self._robots_allows(url):
            raise FetchBlocked("blocked_robots", "disallowed_by_robots_txt")
        try:
            return self._get_raw(url, max_bytes or self.max_bytes)
        except httpx.TimeoutException as exc:
            raise FetchBlocked("error", "timeout") from exc
        except httpx.HTTPError as exc:
            raise FetchBlocked("error", f"network_error: {type(exc).__name__}") from exc


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False
