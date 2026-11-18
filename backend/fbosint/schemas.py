"""Pydantic request/response models (input validation boundary)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,64}$")
RoleLit = Literal["admin", "investigator", "viewer"]
LangLit = Literal["ar", "en"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    client: Literal["web", "desktop"] = "web"


class SetupIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    full_name: str = Field(default="", max_length=128)
    language: LangLit = "ar"

    @field_validator("username")
    @classmethod
    def _u(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("invalid_username")
        return v


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    language: str
    last_login_at: datetime | None = None
    created_at: datetime


class LoginOut(BaseModel):
    user: UserOut
    csrf_token: str
    expires_at: datetime
    token: str | None = None  # only for desktop clients


class UserCreate(SetupIn):
    role: RoleLit = "investigator"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=128)
    role: RoleLit | None = None
    is_active: bool | None = None
    language: LangLit | None = None
    password: str | None = Field(default=None, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class PreferencesIn(BaseModel):
    language: LangLit


# ---------- investigations ----------
class InvestigationOptions(BaseModel):
    collect_posts: bool = True
    collect_photos: bool = True
    collect_comments: bool = False
    download_media: bool = True
    follow_official_website: bool = True
    max_posts: int = Field(default=100, ge=0, le=1000)


class InvestigationCreate(BaseModel):
    target: str = Field(min_length=1, max_length=500)
    target_type: Literal["auto", "profile_url", "username", "page_url", "numeric_id", "authorized_account"] = "auto"
    title: str = Field(default="", max_length=200)
    purpose: str = Field(min_length=5, max_length=2000)
    legal_basis: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=5000)
    extra_urls: list[str] = Field(default_factory=list, max_length=25)
    options: InvestigationOptions = Field(default_factory=InvestigationOptions)
    start: bool = True

    @field_validator("extra_urls")
    @classmethod
    def _urls(cls, v: list[str]) -> list[str]:
        out = []
        for u in v:
            u = u.strip()
            if not u:
                continue
            if len(u) > 2000 or not re.match(r"^https?://", u, re.I):
                raise ValueError("extra_urls_must_be_http_urls")
            out.append(u)
        return out


class InvestigationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    purpose: str | None = Field(default=None, min_length=5, max_length=2000)
    legal_basis: str | None = Field(default=None, max_length=200)


class AddUrlsIn(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=25)
    run: bool = True

    _v = field_validator("urls")(InvestigationCreate._urls.__func__)  # type: ignore[attr-defined]


class InvestigationOut(ORM):
    id: int
    reference: str
    title: str
    target_input: str
    target_type: str
    normalized_url: str
    identifier: str
    object_type: str
    graph_object_id: str
    purpose: str
    legal_basis: str
    notes: str
    options: dict
    extra_urls: list
    status: str
    status_message: str
    limitations: list
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class InvestigationSummary(InvestigationOut):
    counts: dict[str, int] = Field(default_factory=dict)
    created_by_username: str = ""


class DataPointOut(ORM):
    id: int
    category: str
    field: str
    value: str
    source_url: str
    source_type: str
    extraction_method: str
    collected_at: datetime
    availability: str
    verification_status: str
    confidence: str
    classification: str
    manually_reviewed: bool
    notes: str


class DataPointCreate(BaseModel):
    category: Literal["profile", "contact", "business", "identifier", "link", "observation"]
    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    value: str = Field(min_length=1, max_length=5000)
    source_url: str = Field(min_length=1, max_length=1000)
    notes: str = Field(default="", max_length=2000)
    classification: Literal["unverified", "analytical_observation"] = "unverified"

    @field_validator("source_url")
    @classmethod
    def _src(cls, v: str) -> str:
        if not re.match(r"^https?://", v.strip(), re.I):
            raise ValueError("source_url_must_be_http_url")
        return v.strip()


class DataPointReview(BaseModel):
    verification_status: Literal["verified", "unverified", "conflicting"]
    confidence: Literal["high", "medium", "low"]
    notes: str = Field(default="", max_length=2000)


class PostOut(ORM):
    id: int
    external_id: str
    kind: str
    parent_external_id: str
    message: str
    created_time: datetime | None
    permalink: str
    shared_link: str
    source_url: str
    source_type: str
    collected_at: datetime


class MediaOut(ORM):
    id: int
    kind: str
    source_url: str
    source_type: str
    external_id: str
    caption: str
    created_time: datetime | None
    mime_type: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    phash: str
    dhash: str
    metadata_json: dict
    duplicate_group: int | None
    status: str
    error_message: str
    collected_at: datetime


class SourceOut(ORM):
    id: int
    url: str
    final_url: str
    domain: str
    source_type: str
    status: str
    http_status: int | None
    title: str
    content_sha256: str
    error_message: str
    fetched_at: datetime


class EventOut(ORM):
    id: int
    step: str
    level: str
    message: str
    details: dict
    created_at: datetime


class AuditOut(ORM):
    id: int
    created_at: datetime
    user_id: int | None
    username: str
    action: str
    target_type: str
    target_id: str
    ip_address: str
    success: bool
    details: dict


# ---------- settings ----------
class AppSettingsIn(BaseModel):
    retention_days: int | None = Field(default=None, ge=0, le=3650)
    graph_version: str | None = Field(default=None, pattern=r"^v\d{1,2}\.\d$")
    default_language: LangLit | None = None
    backup_keep: int | None = Field(default=None, ge=1, le=365)
    duplicate_threshold: int | None = Field(default=None, ge=0, le=20)


class MetaCredentialsIn(BaseModel):
    app_id: str | None = Field(default=None, max_length=32, pattern=r"^\d*$")
    app_secret: str | None = Field(default=None, max_length=128)
    access_token: str | None = Field(default=None, max_length=1024)
    redirect_uri: str | None = Field(default=None, max_length=500)
