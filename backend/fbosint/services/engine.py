"""Investigation engine: orchestrates official-API collection, enrichment,
media analysis and verification for one investigation.

Every step records a CollectionEvent; failures in one step never abort the
others. The final status is ``completed`` (no limitations), ``partial``
(some data could not be collected) or ``failed`` (unexpected error).
"""
from __future__ import annotations

import logging
import traceback
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Availability,
    Classification,
    CollectionEvent,
    Confidence,
    DataPoint,
    Investigation,
    InvestigationStatus,
    MediaItem,
    Post,
    Source,
    SourceType,
    Verification,
    utcnow,
)
from . import verification
from .app_config import general_settings, load_secret, meta_config
from .extraction import extract_page
from .graph_client import (
    GraphError,
    GraphNotConfigured,
    GraphNotFoundError,
    GraphPermissionError,
    GraphRateLimitError,
    MetaGraphClient,
)
from .media import MediaError, analyse_image, group_duplicates, store_bytes
from .safe_fetch import FetchBlocked, SafeFetcher, default_resolver, is_blocked_domain
from .url_parser import InvalidTargetError, parse_target

log = logging.getLogger("fbosint.engine")

PAGE_EXPECTED = ["name", "username", "link", "about", "description", "category", "website", "email", "phone", "address", "location", "founded", "followers_count", "profile_picture", "cover_photo"]
USER_EXPECTED = ["name", "link", "biography", "workplace", "education", "location", "hometown", "email", "website", "phone", "profile_picture", "cover_photo"]
UNKNOWN_EXPECTED = ["name", "username", "link", "biography", "category", "workplace", "education", "location", "email", "phone", "website", "address", "profile_picture", "cover_photo"]
REMOVED_USER_FIELDS = {"workplace": "removed_from_graph_api", "education": "removed_from_graph_api", "biography": "not_exposed_by_graph_api", "website": "not_exposed_by_graph_api", "phone": "not_exposed_by_graph_api", "cover_photo": "not_exposed_by_graph_api"}
FIELD_CATEGORY = {"email": "contact", "phone": "contact", "address": "contact", "website": "contact", "location": "profile", "username": "identifier", "link": "identifier", "page_id": "identifier", "user_id": "identifier"}


@dataclass
class EngineDeps:
    """Injection points (tests replace transports; production uses defaults)."""

    graph_transport: httpx.BaseTransport | None = None
    web_transport: httpx.BaseTransport | None = None
    resolver: Callable[[str], list[str]] = default_resolver
    sleep: Callable[[float], None] | None = None


deps = EngineDeps()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        if len(v) > 5 and v[-5] in "+-" and v[-3] != ":":
            v = v[:-2] + ":" + v[-2:]
        return datetime.fromisoformat(v)
    except ValueError:
        return None


class InvestigationRunner:
    def __init__(self, db: Session, inv: Investigation) -> None:
        self.db = db
        self.inv = inv
        self.settings = get_settings()
        self.general = general_settings(db)
        self.limitations: list[dict[str, str]] = []
        self.had_problem = False
        self.graph: MetaGraphClient | None = None
        self.website_from_graph: list[str] = []
        self._web: SafeFetcher | None = None
        self._cdn: SafeFetcher | None = None

    # ---------- helpers ----------
    def event(self, step: str, message: str, level: str = "info", **details: Any) -> None:
        self.db.add(CollectionEvent(investigation_id=self.inv.id, step=step, level=level, message=message[:2000], details=details))
        self.db.commit()

    def limit(self, code: str, message: str) -> None:
        self.had_problem = True
        if not any(lim["code"] == code for lim in self.limitations):
            self.limitations.append({"code": code, "message": message[:500]})

    def point(self, category: str, field: str, value: Any, source_url: str, source_type: str, method: str = "", availability: str = Availability.available.value, notes: str = "", classification: str | None = None) -> DataPoint:
        dp = DataPoint(
            investigation_id=self.inv.id,
            category=category,
            field=field,
            value="" if value is None else str(value)[:5000],
            source_url=source_url[:1000],
            source_type=source_type,
            extraction_method=method,
            availability=availability,
            notes=notes[:2000],
            verification_status=Verification.unverified.value,
            confidence=Confidence.low.value,
            classification=classification or Classification.unverified.value,
        )
        self.db.add(dp)
        return dp

    def source(self, url: str, source_type: str, status: str, **kw: Any) -> Source:
        src = Source(investigation_id=self.inv.id, url=url[:2000], domain=(urlsplit(url).hostname or "")[:255], source_type=source_type, status=status, **kw)
        self.db.add(src)
        self.db.commit()
        return src

    @property
    def web(self) -> SafeFetcher:
        if self._web is None:
            s = self.settings
            self._web = SafeFetcher(s.user_agent, s.http_timeout, s.enrich_max_bytes, allow_private=s.enrich_allow_private_networks, transport=deps.web_transport, resolver=deps.resolver)
        return self._web

    @property
    def cdn(self) -> SafeFetcher:
        """Fetcher for media URLs returned by the Graph API itself (Meta CDN)."""
        if self._cdn is None:
            s = self.settings
            self._cdn = SafeFetcher(s.user_agent, s.http_timeout, s.media_max_bytes, allow_private=s.enrich_allow_private_networks, transport=deps.web_transport, resolver=deps.resolver, respect_robots=False, allow_blocked_domains=True)
        return self._cdn

    # ---------- main ----------
    def run(self) -> None:
        inv = self.inv
        inv.status = InvestigationStatus.running.value
        inv.started_at = utcnow()
        inv.status_message = ""
        self.db.commit()
        self.event("start", f"Investigation {inv.reference} started")
        try:
            self._clear_previous_auto_data()
            parsed_ok = self.step_identify()
            if parsed_ok:
                self.step_graph()
            self.step_enrichment()
            self.step_media_groups()
            self.step_observations()
            stats = verification.recompute(self.db, inv.id)
            self.event("verification", "Verification recomputed", **stats)
            inv.status = InvestigationStatus.partial.value if self.had_problem else InvestigationStatus.completed.value
            inv.status_message = "completed_with_limitations" if self.had_problem else "completed"
        except Exception as exc:  # pragma: no cover - defensive; tested via forced failure
            self.db.rollback()
            log.exception("investigation %s failed", inv.reference)
            inv.status = InvestigationStatus.failed.value
            inv.status_message = f"unexpected_error: {type(exc).__name__}"
            self.event("error", f"Unexpected error: {type(exc).__name__}: {exc}", "error", trace=traceback.format_exc()[-2000:])
        finally:
            inv.limitations = self.limitations
            inv.completed_at = utcnow()
            self.db.commit()
            for c in (self.graph, self._web, self._cdn):
                if c is not None:
                    c.close()
            self.event("finish", f"Finished with status {inv.status}", "info" if inv.status == "completed" else "warning")

    def _clear_previous_auto_data(self) -> None:
        """Re-runs replace automatically collected data; manual entries and uploads are kept."""
        inv_id = self.inv.id
        for dp in self.db.scalars(select(DataPoint).where(DataPoint.investigation_id == inv_id, DataPoint.source_type != SourceType.manual.value)):
            self.db.delete(dp)
        for p in self.db.scalars(select(Post).where(Post.investigation_id == inv_id)):
            self.db.delete(p)
        for m in self.db.scalars(select(MediaItem).where(MediaItem.investigation_id == inv_id, MediaItem.source_type != SourceType.investigator_upload.value)):
            self.db.delete(m)
        for s in self.db.scalars(select(Source).where(Source.investigation_id == inv_id)):
            self.db.delete(s)
        self.db.commit()

    # ---------- steps ----------
    def step_identify(self) -> bool:
        inv = self.inv
        try:
            t = parse_target(inv.target_input, inv.target_type if inv.target_type != "auto" else "auto")
        except InvalidTargetError as e:
            self.limit("invalid_target", f"Target could not be parsed: {e.code}")
            self.event("identify", f"Invalid target: {e.code}", "error")
            return False
        inv.target_type, inv.identifier, inv.normalized_url = t.target_type, t.identifier, t.normalized_url
        if t.hint in ("page", "profile"):
            inv.object_type = "page" if t.hint == "page" else "user"
        self.db.commit()
        if t.id_kind != "me":
            self.point("identifier", "profile_url", t.normalized_url, inv.target_input if inv.target_input.startswith("http") else t.normalized_url, SourceType.input_url.value, "url_parse")
            self.point("identifier", "username" if t.id_kind == "username" else "numeric_id", t.identifier, t.normalized_url, SourceType.input_url.value, "url_parse", notes="identifier_visible_in_url")
            self.db.commit()
        self.event("identify", f"Target parsed as {t.target_type} ({t.id_kind})", identifier=t.identifier)
        return True

    def _graph_client(self, token: str) -> MetaGraphClient:
        cfg = meta_config(self.db)
        kwargs: dict[str, Any] = {"version": cfg.graph_version, "app_secret": cfg.app_secret, "timeout": self.settings.http_timeout, "transport": deps.graph_transport}
        if deps.sleep is not None:
            kwargs["sleep"] = deps.sleep
        return MetaGraphClient(token, **kwargs)

    def _graph_failure(self, step: str, err: GraphError, fallback_url: str = "") -> None:
        self.source(fallback_url or f"https://graph.facebook.com/{self.inv.identifier}", SourceType.graph_api.value, err.kind, error_message=err.message, http_status=err.status)
        self.event(step, f"Graph API {err.kind}: {err.message}", "warning", graph_error=err.as_dict())
        msgs = {
            "not_configured": "No Meta access token is configured; official API collection was skipped.",
            "auth_error": "The Meta access token is invalid or expired.",
            "rate_limited": "Meta rate limit reached; collection stopped early. Retry later.",
            "not_permitted": "The access token lacks the permission/feature required by Meta for this data.",
            "not_found": "Meta returned no accessible object. Personal profiles are not available through the official API unless the person authorised this app; the object may also be private, restricted or deleted.",
        }
        self.limit(f"graph_{err.kind}" if step == "graph_profile" else f"{step}_{err.kind}", msgs.get(err.kind, f"Graph API error: {err.message}"))

    def _mark_fields(self, expected: list[str], availability: str, source_url: str, note: str) -> None:
        for f in expected:
            self.point(FIELD_CATEGORY.get(f, "profile"), f, "", source_url, SourceType.graph_api.value, "graph_api", availability, note)
        self.db.commit()

    def step_graph(self) -> None:
        inv = self.inv
        cfg = meta_config(self.db)
        is_me = inv.target_type == "authorized_account"
        token = load_secret(self.db, "meta_user_token", inv.created_by_id) if is_me else cfg.access_token
        expected = USER_EXPECTED if (is_me or inv.object_type == "user") else PAGE_EXPECTED if inv.object_type == "page" else UNKNOWN_EXPECTED
        src_url = inv.normalized_url or "https://graph.facebook.com/me"
        try:
            self.graph = self._graph_client(token)
        except GraphNotConfigured as e:
            if is_me:
                e = GraphNotConfigured("authorized_account_not_connected")
            self._graph_failure("graph_profile", e)
            self._mark_fields(expected, Availability.unavailable.value, src_url, "official_api_not_configured")
            return
        try:
            res, dropped = self.graph.get_me() if is_me else self.graph.get_page(inv.identifier)
        except GraphError as e:
            self._graph_failure("graph_profile", e)
            self._mark_fields(expected, Availability.unavailable.value, src_url, f"graph_{e.kind}")
            return
        data = res.data
        if dropped:
            self.event("graph_profile", f"Fields not available for this object type: {', '.join(dropped)}", "info")
        self.source(res.url, SourceType.graph_api.value, "fetched", http_status=200, title=str(data.get("name", ""))[:500])
        inv.graph_object_id = str(data.get("id", ""))
        inv.object_type = "user" if is_me else "page"
        if is_me:
            inv.normalized_url = data.get("link", "") or inv.normalized_url
        self.db.commit()
        self._store_profile(data, res.url, is_me)
        self.event("graph_profile", f"Official profile data collected for {data.get('name', inv.identifier)}", usage=res.usage)
        oid = inv.graph_object_id or inv.identifier
        opts = inv.options or {}
        if opts.get("collect_posts", True):
            self._collect_posts(oid, is_me, int(opts.get("max_posts", 100)), bool(opts.get("collect_comments", False)))
        if opts.get("collect_photos", True):
            self._collect_photos("me" if is_me else oid)

    def _store_profile(self, d: dict, url: str, is_me: bool) -> None:
        gt = SourceType.graph_api.value
        present: set[str] = set()

        def add(cat: str, field: str, value: Any, method: str = "graph_api") -> None:
            if value in (None, "", [], {}):
                return
            present.add(field)
            self.point(cat, field, value, url, gt, method)

        add("identifier", "user_id" if is_me else "page_id", d.get("id"))
        add("identifier", "username", d.get("username"))
        add("identifier", "link", d.get("link"))
        add("profile", "name", d.get("name"))
        add("profile", "about", d.get("about"))
        add("profile", "description", d.get("description"))
        add("business", "category", d.get("category"))
        for c in d.get("category_list") or []:
            if isinstance(c, dict) and c.get("name") and c.get("name") != d.get("category"):
                self.point("business", "category", c["name"], url, gt, "graph_api")
        add("business", "founded", d.get("founded"))
        add("business", "followers_count", d.get("followers_count"))
        add("business", "fan_count", d.get("fan_count"))
        add("business", "verification_status", d.get("verification_status"))
        for e in d.get("emails") or ([d["email"]] if d.get("email") else []):
            add("contact", "email", e)
        add("contact", "phone", d.get("phone"))
        add("contact", "address", d.get("single_line_address"))
        websites = [w for w in str(d.get("website") or "").replace(",", " ").split() if w]
        for w in websites:
            w = w if "://" in w else "https://" + w
            add("contact", "website", w)
            self.website_from_graph.append(w)
        loc = d.get("location")
        if isinstance(loc, dict):
            parts = [loc.get(k) for k in ("street", "city", "state", "zip", "country") if loc.get(k)]
            add("profile", "location", ", ".join(map(str, parts)) or loc.get("name"))
        elif isinstance(loc, (str,)):
            add("profile", "location", loc)
        for key in ("location", "hometown"):
            v = d.get(key)
            if is_me and isinstance(v, dict) and v.get("name"):
                add("profile", key, v["name"])
        pic = (d.get("picture") or {}).get("data") or {}
        if pic.get("url") and not pic.get("is_silhouette"):
            present.add("profile_picture")
            self._add_media("profile_picture", pic["url"], gt, external_id="")
        cover = d.get("cover") or {}
        if cover.get("source"):
            present.add("cover_photo")
            self._add_media("cover_photo", cover["source"], gt, external_id=str(cover.get("id", "")))
        if d.get("about") or d.get("description"):
            present.add("biography")
        # Fields the object exposes in principle but has not published -> undisclosed;
        # fields Meta never exposes for users -> unavailable.
        expected = USER_EXPECTED if is_me else PAGE_EXPECTED
        for f in expected:
            if f in present:
                continue
            if is_me and f in REMOVED_USER_FIELDS:
                self.point(FIELD_CATEGORY.get(f, "profile"), f, "", url, gt, "graph_api", Availability.unavailable.value, REMOVED_USER_FIELDS[f])
            else:
                self.point(FIELD_CATEGORY.get(f, "profile"), f, "", url, gt, "graph_api", Availability.undisclosed.value, "not_published_by_owner")
        self.db.commit()

    def _collect_posts(self, oid: str, is_me: bool, limit: int, comments: bool) -> None:
        if self.graph is None:
            return
        limit = min(limit, self.settings.max_posts)
        if limit <= 0:
            return
        try:
            items, url = self.graph.user_posts(limit) if is_me else self.graph.page_posts(oid, limit)
        except GraphError as e:
            self._graph_failure("graph_posts", e, f"https://graph.facebook.com/{oid}/posts")
            return
        self.source(url, SourceType.graph_api.value, "fetched", http_status=200, title=f"{len(items)} posts")
        n = 0
        for it in items:
            shared = ""
            for att in ((it.get("attachments") or {}).get("data") or []):
                if att.get("type") in ("share", "link") or att.get("media_type") == "link":
                    shared = att.get("unshimmed_url") or att.get("url") or ""
                    break
            self.db.add(Post(investigation_id=self.inv.id, external_id=str(it.get("id", ""))[:128], kind="post", message=(it.get("message") or "")[:20000], created_time=_parse_time(it.get("created_time")), permalink=(it.get("permalink_url") or "")[:1000], shared_link=shared[:1000], source_url=url[:1000], source_type=SourceType.graph_api.value))
            if shared:
                self.point("link", "shared_link", shared, it.get("permalink_url") or url, SourceType.graph_api.value, "graph_api")
            n += 1
        self.db.commit()
        self.event("graph_posts", f"{n} public posts collected")
        if comments and items:
            seen: set[str] = set()
            for it in items[:10]:
                try:
                    cs, curl = self.graph.comments(str(it.get("id")), 25)
                except GraphError as e:
                    self._graph_failure("graph_comments", e, f"https://graph.facebook.com/{it.get('id')}/comments")
                    break
                for c in cs:
                    cid = str(c.get("id", ""))
                    if not cid or cid in seen:
                        continue
                    seen.add(cid)
                    self.db.add(Post(investigation_id=self.inv.id, external_id=str(c.get("id", ""))[:128], kind="comment", parent_external_id=str(it.get("id", ""))[:128], message=(c.get("message") or "")[:20000], created_time=_parse_time(c.get("created_time")), permalink=(c.get("permalink_url") or "")[:1000], source_url=curl[:1000], source_type=SourceType.graph_api.value))
                self.db.commit()
            self.event("graph_comments", "Public comments collected where permitted")

    def _collect_photos(self, oid: str) -> None:
        if self.graph is None:
            return
        try:
            items, url = self.graph.photos(oid, 50)
        except GraphError as e:
            self._graph_failure("graph_photos", e, f"https://graph.facebook.com/{oid}/photos")
            return
        self.source(url, SourceType.graph_api.value, "fetched", http_status=200, title=f"{len(items)} photos")
        for it in items:
            imgs = sorted(it.get("images") or [], key=lambda i: i.get("width", 0), reverse=True)
            src = imgs[0]["source"] if imgs and imgs[0].get("source") else ""
            if src:
                self._add_media("photo", src, SourceType.graph_api.value, external_id=str(it.get("id", "")), caption=it.get("name") or "", created=_parse_time(it.get("created_time")))
        self.event("graph_photos", f"{len(items)} public photos referenced")

    def _add_media(self, kind: str, url: str, source_type: str, external_id: str = "", caption: str = "", created: datetime | None = None) -> None:
        item = MediaItem(investigation_id=self.inv.id, kind=kind, source_url=url[:2000], source_type=source_type, external_id=external_id[:128], caption=caption[:5000], created_time=created, status="reference_only")
        self.db.add(item)
        self.db.commit()
        if not (self.inv.options or {}).get("download_media", True):
            return
        host = (urlsplit(url).hostname or "").lower()
        fetcher = self.cdn if source_type == SourceType.graph_api.value else self.web
        if source_type == SourceType.graph_api.value and not (host.endswith("fbcdn.net") or host.endswith("facebook.com") or host.endswith("fbsbx.com")):
            item.status, item.error_message = "error", "unexpected_media_host"
            self.db.commit()
            return
        try:
            r = fetcher.fetch(url, self.settings.media_max_bytes)
            if r.status_code != 200:
                raise MediaError(f"http_{r.status_code}")
            info = analyse_image(r.content)
            item.local_path = store_bytes(self.settings.media_dir, self.inv.id, info, r.content)
            item.sha256, item.phash, item.dhash = info.sha256, info.phash, info.dhash
            item.mime_type, item.width, item.height, item.size_bytes = info.mime_type, info.width, info.height, len(r.content)
            item.metadata_json = info.metadata
            item.status = "stored"
        except (FetchBlocked, MediaError) as e:
            item.status = "error"
            item.error_message = getattr(e, "message", None) or str(e)
        self.db.commit()

    def step_enrichment(self) -> None:
        inv = self.inv
        urls = [(u, SourceType.user_supplied_url.value) for u in (inv.extra_urls or [])]
        if (inv.options or {}).get("follow_official_website", True):
            urls += [(u, SourceType.official_website.value) for u in self.website_from_graph if u not in (inv.extra_urls or [])]
        seen: set[str] = set()
        for url, stype in urls:
            if url in seen:
                continue
            seen.add(url)
            self._enrich_one(url, stype)

    def _enrich_one(self, url: str, stype: str) -> None:
        host = urlsplit(url).hostname or ""
        if is_blocked_domain(host):
            self.source(url, stype, "blocked_policy", error_message="facebook_family_domain_not_fetched")
            self.event("enrichment", f"Skipped {url}: Facebook-family domains are only accessed through the official API", "warning")
            return
        try:
            r = self.web.fetch(url)
        except FetchBlocked as e:
            self.source(url, stype, e.status, error_message=e.message)
            self.event("enrichment", f"{url}: {e.status} ({e.message})", "warning")
            if e.status == "error":
                self.limit("enrichment_error", "One or more supplied URLs could not be fetched.")
            return
        if r.status_code != 200:
            self.source(url, stype, "error", http_status=r.status_code, final_url=r.final_url, error_message=f"http_{r.status_code}")
            self.event("enrichment", f"{url}: HTTP {r.status_code}", "warning")
            self.limit("enrichment_error", "One or more supplied URLs could not be fetched.")
            return
        if "html" not in r.content_type.lower() and "xml" not in r.content_type.lower():
            self.source(url, stype, "fetched", http_status=200, final_url=r.final_url, content_sha256=r.sha256, error_message="non_html_content_not_parsed")
            return
        ex = extract_page(r.text, r.final_url)
        self.source(url, stype, "fetched", http_status=200, final_url=r.final_url, content_sha256=r.sha256, title=ex.title)
        n = 0
        for it in ex.items:
            if it.kind in ("email", "phone", "address", "website"):
                self.point("contact", it.kind, it.value, r.final_url, stype, it.method)
            elif it.kind == "social_link":
                self.point("link", "related_link", it.value, r.final_url, stype, it.method, notes="association_with_target_not_verified")
            elif it.kind == "organization_name":
                self.point("business", "organization_name", it.value, r.final_url, stype, it.method)
            elif it.kind == "description":
                self.point("business", "web_description", it.value, r.final_url, stype, it.method)
            elif it.kind == "image" and (self.inv.options or {}).get("download_media", True):
                self._add_media("web_image", it.value, stype)
                continue
            else:
                continue
            n += 1
        self.db.commit()
        self.event("enrichment", f"{url}: {n} published data points extracted")

    def step_media_groups(self) -> None:
        regroup_media(self.db, self.inv.id, int(self.general.get("duplicate_threshold", 8)))

    def step_observations(self) -> None:
        inv_id = self.inv.id
        posts = list(self.db.scalars(select(Post).where(Post.investigation_id == inv_id, Post.kind == "post")))
        dated = sorted(p.created_time for p in posts if p.created_time)
        if dated:
            months = Counter(d.strftime("%Y-%m") for d in dated)
            top, cnt = months.most_common(1)[0]
            self.point("observation", "activity_summary", f"{len(posts)} public posts between {dated[0].date()} and {dated[-1].date()}; most active month {top} ({cnt} posts).", self.inv.normalized_url or "", SourceType.analysis.value, "analysis", classification=Classification.analytical_observation.value)
        media = list(self.db.scalars(select(MediaItem).where(MediaItem.investigation_id == inv_id)))
        groups = {m.duplicate_group for m in media if m.duplicate_group}
        if groups:
            self.point("observation", "image_reuse", f"{sum(1 for m in media if m.duplicate_group)} images fall into {len(groups)} duplicate/near-duplicate groups within this dataset (perceptual hash).", "", SourceType.analysis.value, "analysis", classification=Classification.analytical_observation.value)
        related = self.db.scalars(select(DataPoint).where(DataPoint.investigation_id == inv_id, DataPoint.field == "related_link")).all()
        if related:
            self.point("observation", "related_links", f"{len(related)} related social/profile links were published on supplied websites. They are NOT assumed to belong to the target; each requires independent verification.", "", SourceType.analysis.value, "analysis", classification=Classification.analytical_observation.value)
        self.db.commit()


def regroup_media(db: Session, investigation_id: int, threshold: int = 8) -> None:
    items = list(db.scalars(select(MediaItem).where(MediaItem.investigation_id == investigation_id)))
    mapping = group_duplicates([(m.id, m.sha256, m.phash) for m in items if m.status == "stored"], threshold)
    for m in items:
        m.duplicate_group = mapping.get(m.id)
    db.commit()


def run_investigation(investigation_id: int) -> None:
    """Entry point for background execution (own DB session)."""
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        inv = db.get(Investigation, investigation_id)
        if inv is None:
            return
        InvestigationRunner(db, inv).run()
    finally:
        db.close()


__all__ = ["EngineDeps", "InvestigationRunner", "deps", "regroup_media", "run_investigation", "GraphPermissionError", "GraphRateLimitError", "GraphNotFoundError"]
