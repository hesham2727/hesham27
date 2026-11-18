"""Password hashing, session tokens and request helpers (stdlib only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from .config import get_settings

# scrypt parameters (OWASP-recommended minimum: N=2^17, r=8, p=1).
_SCRYPT_N = int(os.environ.get("TAHQIQ_SCRYPT_N", str(2**17)))  # lowered only in tests
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 256 * 1024 * 1024

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM, dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


# A pre-computed hash used to keep login timing constant for unknown users.
_DUMMY_HASH: str | None = None


def dummy_verify(password: str) -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("dummy-password-for-timing")
    verify_password(password, _DUMMY_HASH)


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"يجب ألا تقل كلمة المرور عن {MIN_PASSWORD_LENGTH} أحرف")
    if password.isdigit() or password.isalpha():
        problems.append("يجب أن تحتوي كلمة المرور على أحرف وأرقام")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
        cf = request.headers.get("cf-connecting-ip")
        if cf:
            return cf.strip()[:64]
    return (request.client.host if request.client else "")[:64]


def is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    if host in {"testclient", "localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class RateLimiter:
    """Simple in-memory sliding-window limiter (adequate for 1–5 users)."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Register a hit; return False when the key is over the limit."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = RateLimiter(limit=20, window_seconds=300)
public_limiter = RateLimiter(limit=30, window_seconds=60)

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15
