"""Source verification engine: corroboration, conflicts and confidence."""
from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Availability, Classification, Confidence, DataPoint, Verification
from .extraction import normalize

# Fields where several different values are normal (a business can have many e-mails).
MULTI_VALUE_FIELDS = {"email", "phone", "social_link", "website", "related_link", "category", "post_link", "address"}
SINGLE_VALUE_FIELDS = {"name", "username", "founded", "page_id", "user_id"}


def _domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def _norm_kind(field: str) -> str:
    return {"public_email": "email", "public_phone": "phone", "business_email": "email", "business_phone": "phone", "website": "website"}.get(field, field)


def recompute(db: Session, investigation_id: int) -> dict[str, int]:
    """Recalculate verification/confidence for automatically collected points.

    Manually reviewed points are left untouched.
    """
    points = list(db.scalars(select(DataPoint).where(DataPoint.investigation_id == investigation_id)))
    by_value: dict[tuple[str, str], list[DataPoint]] = defaultdict(list)
    by_field: dict[str, set[str]] = defaultdict(set)
    for p in points:
        if p.availability != Availability.available.value:
            continue
        kind = _norm_kind(p.field)
        p.normalized_value = normalize(kind, p.value)
        by_value[(kind, p.normalized_value)].append(p)
        if p.category in ("profile", "business") and kind in SINGLE_VALUE_FIELDS:
            by_field[kind].add(p.normalized_value)

    stats = {"verified": 0, "unverified": 0, "conflicting": 0}
    for p in points:
        if p.manually_reviewed or p.availability != Availability.available.value:
            continue
        if p.classification == Classification.analytical_observation.value:
            p.verification_status = Verification.unverified.value
            stats["unverified"] += 1
            continue
        kind = _norm_kind(p.field)
        peers = by_value[(kind, p.normalized_value)]
        domains = {_domain(x.source_url) for x in peers if x.source_url}
        graph = any(x.source_type == "graph_api" for x in peers)
        conflicting = kind in by_field and len(by_field[kind]) > 1
        if conflicting and not p.source_type == "graph_api":
            p.verification_status = Verification.conflicting.value
            p.confidence = Confidence.low.value
            p.classification = Classification.unverified.value
        elif p.source_type == "graph_api":
            p.verification_status = Verification.verified.value
            p.confidence = Confidence.high.value
            p.classification = Classification.fact.value
        elif graph or len(domains) >= 2:
            p.verification_status = Verification.verified.value
            p.confidence = Confidence.high.value
            p.classification = Classification.fact.value
        elif p.source_type == "input_url":
            # Identifier visible in the URL the investigator supplied: a fact about the URL itself.
            p.verification_status = Verification.verified.value
            p.confidence = Confidence.high.value
            p.classification = Classification.fact.value
        else:
            p.verification_status = Verification.unverified.value
            p.confidence = Confidence.medium.value if p.extraction_method in ("json_ld", "mailto", "tel", "meta") else Confidence.low.value
            p.classification = Classification.unverified.value
        stats[p.verification_status] += 1
    db.commit()
    return stats
