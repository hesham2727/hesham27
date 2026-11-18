"""scrypt password hashing (stdlib, memory-hard) and password policy."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32
_PREFIX = "scrypt"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=64 * 1024 * 1024)
    return "$".join([_PREFIX, str(_N), str(_R), str(_P), base64.b64encode(salt).decode(), base64.b64encode(dk).decode()])


def verify_password(password: str, stored: str) -> bool:
    try:
        prefix, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if prefix != _PREFIX:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# A hash of a random value, used to equalise timing when the username doesn't exist.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problems(password: str, username: str = "") -> list[str]:
    problems: list[str] = []
    if len(password) < 10:
        problems.append("password_too_short")
    if len(password) > 256:
        problems.append("password_too_long")
    if not re.search(r"[A-Za-z؀-ۿ]", password) or not re.search(r"\d", password):
        problems.append("password_needs_letters_and_digits")
    if username and username.lower() in password.lower():
        problems.append("password_contains_username")
    return problems
