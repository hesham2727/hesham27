"""Parse and normalise Facebook profile / Page URLs and usernames.

The parser never contacts Facebook. It only interprets the string the
investigator typed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

FB_HOSTS = {
    "facebook.com", "www.facebook.com", "m.facebook.com", "mbasic.facebook.com", "web.facebook.com",
    "touch.facebook.com", "business.facebook.com", "fb.com", "www.fb.com", "fb.me", "ar-ar.facebook.com",
    "en-gb.facebook.com", "ar-ar.facebook.com",
}
RESERVED = {
    "login", "login.php", "home.php", "help", "policies", "privacy", "settings", "watch", "marketplace",
    "gaming", "events", "groups", "share", "sharer", "sharer.php", "story.php", "permalink.php", "photo.php",
    "photo", "video.php", "reel", "reels", "stories", "hashtag", "search", "messages", "notifications",
    "friends", "bookmarks", "pages", "people", "profile.php", "pg", "l.php", "dialog", "plugins", "ads",
    "business", "legal", "about", "careers", "recover", "checkpoint", "media", "live", "fundraisers",
    "groups.php", "nt", "tr", "rsrc.php", "places", "public", "directory", "terms", "cookies",
}
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,79}$")
NUMERIC_RE = re.compile(r"^\d{5,25}$")


class InvalidTargetError(ValueError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class ParsedTarget:
    target_type: str        # profile_url|username|page_url|numeric_id|authorized_account
    identifier: str         # username, numeric id or "me"
    id_kind: str            # username|numeric_id|me
    normalized_url: str
    hint: str               # page|profile|unknown


def _canonical(identifier: str, id_kind: str) -> str:
    if id_kind == "numeric_id":
        return f"https://www.facebook.com/profile.php?id={identifier}"
    if id_kind == "me":
        return ""
    return f"https://www.facebook.com/{identifier}"


def parse_target(raw: str, target_type: str = "auto") -> ParsedTarget:
    text = (raw or "").strip()
    if not text:
        raise InvalidTargetError("empty_target")
    if len(text) > 500:
        raise InvalidTargetError("target_too_long")
    if any(c in text for c in "\x00\r\n\t<>\"'`"):
        raise InvalidTargetError("invalid_characters")

    if target_type == "authorized_account" or text.lower() in {"me", "authorized"}:
        return ParsedTarget("authorized_account", "me", "me", "", "profile")

    looks_like_url = "://" in text or text.lower().startswith(("www.", "facebook.com", "m.facebook.com", "fb.com", "fb.me", "web.facebook.com"))
    if not looks_like_url:
        handle = text.lstrip("@")
        if NUMERIC_RE.match(handle):
            return ParsedTarget("numeric_id", handle, "numeric_id", _canonical(handle, "numeric_id"), "unknown")
        if USERNAME_RE.match(handle) and handle.lower() not in RESERVED and not handle.endswith("."):
            tt = target_type if target_type in {"username", "page_url", "profile_url"} else "username"
            hint = "page" if tt == "page_url" else ("profile" if tt == "profile_url" else "unknown")
            return ParsedTarget(tt, handle, "username", _canonical(handle, "username"), hint)
        raise InvalidTargetError("invalid_username")

    url = text if "://" in text else "https://" + text
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise InvalidTargetError("invalid_url") from exc
    if parts.scheme.lower() not in {"http", "https"}:
        raise InvalidTargetError("invalid_scheme")
    host = (parts.hostname or "").lower()
    if host not in FB_HOSTS and not re.fullmatch(r"[a-z]{2}-[a-z]{2}\.facebook\.com", host):
        raise InvalidTargetError("not_a_facebook_url")
    if parts.username or parts.password or (parts.port not in (None, 80, 443)):
        raise InvalidTargetError("invalid_url")

    segments = [unquote(s) for s in parts.path.split("/") if s]
    query = parse_qs(parts.query)

    def page_or_profile(default: str) -> str:
        if target_type == "page_url":
            return "page"
        if target_type == "profile_url":
            return "profile"
        return default

    # profile.php?id=123
    if segments and segments[0].lower() == "profile.php":
        ids = query.get("id", [])
        if ids and NUMERIC_RE.match(ids[0]):
            return ParsedTarget("profile_url", ids[0], "numeric_id", _canonical(ids[0], "numeric_id"), page_or_profile("profile"))
        raise InvalidTargetError("profile_id_missing")
    # /people/Name/123 and /pages/Name/123  (also /pages/category/Name/123)
    if segments and segments[0].lower() in {"people", "pages"}:
        num = next((s for s in reversed(segments) if NUMERIC_RE.match(s)), None)
        if num:
            kind = "profile" if segments[0].lower() == "people" else "page"
            tt = "profile_url" if kind == "profile" else "page_url"
            return ParsedTarget(tt, num, "numeric_id", _canonical(num, "numeric_id"), page_or_profile(kind))
        raise InvalidTargetError("profile_id_missing")
    # /pg/username/...
    if len(segments) >= 2 and segments[0].lower() == "pg":
        segments = segments[1:]
    if not segments:
        raise InvalidTargetError("no_profile_in_url")
    first = segments[0]
    if first.lower() in RESERVED:
        raise InvalidTargetError("unsupported_facebook_url")
    if NUMERIC_RE.match(first):
        return ParsedTarget("profile_url", first, "numeric_id", _canonical(first, "numeric_id"), page_or_profile("unknown"))
    if USERNAME_RE.match(first) and not first.endswith("."):
        tt = "page_url" if target_type == "page_url" else "profile_url"
        return ParsedTarget(tt, first, "username", _canonical(first, "username"), page_or_profile("unknown"))
    raise InvalidTargetError("invalid_username")
