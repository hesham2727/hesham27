"""Symmetric encryption of stored credentials (Fernet: AES-128-CBC + HMAC-SHA256)."""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().resolve_encryption_key().encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:  # wrong key or tampered value
        raise ValueError("credential_decryption_failed") from exc


def mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "••••"
    return f"{secret[:4]}••••{secret[-4:]}"
