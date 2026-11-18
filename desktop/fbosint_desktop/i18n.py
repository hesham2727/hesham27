"""Uses the same dictionaries as the web application (shared/i18n)."""
from __future__ import annotations

import json

from .paths import shared_i18n_dir

_dicts: dict[str, dict[str, str]] = {}
_lang = "ar"


def load() -> None:
    for lang in ("ar", "en"):
        _dicts[lang] = json.loads((shared_i18n_dir() / f"{lang}.json").read_text(encoding="utf-8"))


def set_lang(lang: str) -> None:
    global _lang
    _lang = lang if lang in ("ar", "en") else "ar"


def lang() -> str:
    return _lang


def t(key: str) -> str:
    if not _dicts:
        load()
    return _dicts.get(_lang, {}).get(key) or _dicts.get("en", {}).get(key) or key


def enum(prefix: str, value: str) -> str:
    k = f"{prefix}.{value}"
    r = t(k)
    return value if r == k else r
