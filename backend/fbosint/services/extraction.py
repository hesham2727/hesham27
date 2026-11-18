"""Extract explicitly published information from a public web page.

Only *published* contact data is extracted:
  * schema.org JSON-LD  (telephone, email, address, url, sameAs)      -> medium confidence
  * ``mailto:`` / ``tel:`` links                                       -> medium confidence
  * e-mail addresses printed in visible text                          -> low confidence
Phone numbers are NOT harvested from free text (too error-prone and risks
capturing private numbers); only explicitly marked-up numbers are taken.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}(?![\w-])")
SOCIAL_HOSTS = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "tiktok.com", "snapchat.com", "t.me", "wa.me", "threads.net", "github.com")
IGNORED_EMAIL_DOMAINS = ("example.com", "example.org", "sentry.io", "wixpress.com", "domain.com", "email.com")


@dataclass
class Extracted:
    kind: str          # email|phone|address|website|social_link|title|description|image|organization_name
    value: str
    method: str        # json_ld|mailto|tel|text|meta|og|link
    confidence: str    # medium|low|high


@dataclass
class PageExtraction:
    title: str = ""
    items: list[Extracted] = field(default_factory=list)

    def add(self, kind: str, value: str, method: str, confidence: str) -> None:
        value = value.strip()
        if not value or len(value) > 1000:
            return
        for it in self.items:
            if it.kind == kind and normalize(kind, it.value) == normalize(kind, value):
                return
        self.items.append(Extracted(kind, value, method, confidence))


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip = 0
        self._jsonld = False
        self.jsonld_blocks: list[str] = []
        self._buf: list[str] = []
        self.text: list[str] = []
        self.links: list[str] = []
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag in ("script", "style", "noscript", "template"):
            if tag == "script" and "ld+json" in a.get("type", "").lower():
                self._jsonld = True
                self._buf = []
            else:
                self._skip += 1
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._jsonld:
            self._jsonld = False
            self.jsonld_blocks.append("".join(self._buf))
        elif tag in ("script", "style", "noscript", "template") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._jsonld:
            self._buf.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skip:
            self.text.append(data)


def normalize(kind: str, value: str) -> str:
    v = value.strip()
    if kind == "email":
        return v.lower()
    if kind == "phone":
        digits = re.sub(r"[^\d+]", "", v)
        if digits.startswith("00"):
            digits = "+" + digits[2:]
        return digits
    if kind in ("website", "social_link"):
        p = urlsplit(v if "://" in v else "https://" + v)
        host = (p.hostname or "").lower().removeprefix("www.")
        return f"{host}{p.path.rstrip('/')}".lower()
    return re.sub(r"\s+", " ", v).lower()


def _walk_jsonld(node, out: PageExtraction, base: str) -> None:
    if isinstance(node, list):
        for n in node:
            _walk_jsonld(n, out, base)
        return
    if not isinstance(node, dict):
        return
    if "@graph" in node:
        _walk_jsonld(node["@graph"], out, base)
    types = node.get("@type", [])
    types = [types] if isinstance(types, str) else (types or [])
    is_entity = any(t in {"Organization", "LocalBusiness", "Corporation", "Store", "Restaurant", "ProfessionalService", "Person", "NGO", "GovernmentOrganization", "EducationalOrganization", "MedicalOrganization", "HomeAndConstructionBusiness", "GeneralContractor"} or str(t).endswith("Business") for t in types)
    if is_entity:
        if isinstance(node.get("name"), str) and "Person" not in types:
            out.add("organization_name", node["name"], "json_ld", "medium")
        for key, kind in (("telephone", "phone"), ("email", "email")):
            vals = node.get(key)
            for v in ([vals] if isinstance(vals, str) else (vals or [])):
                if isinstance(v, str):
                    out.add(kind, v.replace("mailto:", "").replace("tel:", ""), "json_ld", "medium")
        if isinstance(node.get("url"), str):
            out.add("website", urljoin(base, node["url"]), "json_ld", "medium")
        addr = node.get("address")
        if isinstance(addr, str):
            out.add("address", addr, "json_ld", "medium")
        elif isinstance(addr, dict):
            parts = [addr.get(k, "") for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")]
            parts = [p if isinstance(p, str) else (p.get("name", "") if isinstance(p, dict) else "") for p in parts]
            joined = ", ".join(p for p in parts if p)
            if joined:
                out.add("address", joined, "json_ld", "medium")
        same = node.get("sameAs")
        for s in ([same] if isinstance(same, str) else (same or [])):
            if isinstance(s, str) and s.startswith("http"):
                out.add("social_link", s, "json_ld", "low")
        cp = node.get("contactPoint")
        _walk_jsonld(cp if isinstance(cp, list) else [cp] if cp else [], out, base)
    elif "ContactPoint" in types:
        for key, kind in (("telephone", "phone"), ("email", "email")):
            v = node.get(key)
            if isinstance(v, str):
                out.add(kind, v, "json_ld", "medium")
    for k, v in node.items():
        if k not in ("@graph", "contactPoint") and isinstance(v, (dict, list)):
            _walk_jsonld(v, out, base)


def _valid_email(e: str) -> bool:
    e = e.lower()
    domain = e.split("@")[-1]
    return not any(domain == d or domain.endswith("." + d) for d in IGNORED_EMAIL_DOMAINS) and not re.search(r"\.(png|jpg|jpeg|gif|svg|webp)$", e)


def _valid_phone(p: str) -> bool:
    digits = re.sub(r"\D", "", p)
    return 6 <= len(digits) <= 16


def extract_page(html: str, base_url: str) -> PageExtraction:
    parser = _Parser()
    try:
        parser.feed(html[:2_000_000])
        parser.close()
    except Exception:  # malformed HTML must never crash a collection run
        pass
    out = PageExtraction(title=re.sub(r"\s+", " ", parser.title).strip()[:500])
    if out.title:
        out.add("title", out.title, "meta", "high")
    desc = parser.meta.get("description") or parser.meta.get("og:description")
    if desc:
        out.add("description", desc[:1000], "meta", "high")
    if parser.meta.get("og:image"):
        out.add("image", urljoin(base_url, parser.meta["og:image"]), "og", "medium")
    if parser.meta.get("og:site_name"):
        out.add("organization_name", parser.meta["og:site_name"], "og", "low")

    for block in parser.jsonld_blocks:
        try:
            _walk_jsonld(json.loads(block), out, base_url)
        except (ValueError, RecursionError):
            continue

    for href in parser.links:
        h = href.strip()
        low = h.lower()
        if low.startswith("mailto:"):
            addr = unquote(h[7:].split("?")[0]).strip()
            if EMAIL_RE.fullmatch(addr) and _valid_email(addr):
                out.add("email", addr, "mailto", "medium")
        elif low.startswith("tel:"):
            num = unquote(h[4:]).strip()
            if _valid_phone(num):
                out.add("phone", num, "tel", "medium")
        elif low.startswith(("http://", "https://", "//")):
            host = (urlsplit(urljoin(base_url, h)).hostname or "").lower()
            if any(host == s or host.endswith("." + s) for s in SOCIAL_HOSTS):
                out.add("social_link", urljoin(base_url, h), "link", "low")

    # remove invalid json-ld values
    out.items = [i for i in out.items if not (i.kind == "email" and not (EMAIL_RE.fullmatch(i.value) and _valid_email(i.value))) and not (i.kind == "phone" and not _valid_phone(i.value))]

    text = " ".join(parser.text)
    for m in EMAIL_RE.finditer(text):
        if _valid_email(m.group(0)):
            out.add("email", m.group(0), "text", "low")
    return out
