"""ORM models. Portable across SQLite and PostgreSQL (no dialect-specific types)."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    admin = "admin"
    investigator = "investigator"
    viewer = "viewer"


class InvestigationStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    partial = "partial"
    failed = "failed"


class TargetType(str, enum.Enum):
    profile_url = "profile_url"
    username = "username"
    page_url = "page_url"
    numeric_id = "numeric_id"
    authorized_account = "authorized_account"


class SourceType(str, enum.Enum):
    graph_api = "graph_api"
    user_supplied_url = "user_supplied_url"
    official_website = "official_website"
    manual = "manual"
    input_url = "input_url"


class Availability(str, enum.Enum):
    available = "available"
    undisclosed = "undisclosed"
    unavailable = "unavailable"


class Verification(str, enum.Enum):
    verified = "verified"
    unverified = "unverified"
    conflicting = "conflicting"


class Confidence(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Classification(str, enum.Enum):
    fact = "fact"
    unverified = "unverified"
    analytical_observation = "analytical_observation"


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


TZDateTime = UTCDateTime()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.investigator.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    language: Mapped[str] = mapped_column(String(5), default="ar")
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client: Mapped[str] = mapped_column(String(20), default="web")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship()


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    target_input: Mapped[str] = mapped_column(String(500))
    target_type: Mapped[str] = mapped_column(String(32))
    normalized_url: Mapped[str] = mapped_column(String(500), default="")
    identifier: Mapped[str] = mapped_column(String(200), default="")
    object_type: Mapped[str] = mapped_column(String(32), default="unknown")  # page|user|unknown
    graph_object_id: Mapped[str] = mapped_column(String(64), default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    legal_basis: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    extra_urls: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default=InvestigationStatus.pending.value, index=True)
    status_message: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    created_by: Mapped[User | None] = relationship()
    data_points: Mapped[list[DataPoint]] = relationship(back_populates="investigation", cascade="all, delete-orphan", passive_deletes=True)
    posts: Mapped[list[Post]] = relationship(back_populates="investigation", cascade="all, delete-orphan", passive_deletes=True)
    media_items: Mapped[list[MediaItem]] = relationship(back_populates="investigation", cascade="all, delete-orphan", passive_deletes=True)
    sources: Mapped[list[Source]] = relationship(back_populates="investigation", cascade="all, delete-orphan", passive_deletes=True)
    events: Mapped[list[CollectionEvent]] = relationship(back_populates="investigation", cascade="all, delete-orphan", passive_deletes=True)


class DataPoint(Base):
    __tablename__ = "data_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(32))  # profile|contact|business|identifier|link|observation
    field: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text, default="")
    normalized_value: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    source_type: Mapped[str] = mapped_column(String(32))
    extraction_method: Mapped[str] = mapped_column(String(32), default="")
    collected_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    availability: Mapped[str] = mapped_column(String(20), default=Availability.available.value)
    verification_status: Mapped[str] = mapped_column(String(20), default=Verification.unverified.value)
    confidence: Mapped[str] = mapped_column(String(10), default=Confidence.low.value)
    classification: Mapped[str] = mapped_column(String(32), default=Classification.unverified.value)
    manually_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    investigation: Mapped[Investigation] = relationship(back_populates="data_points")

    __table_args__ = (Index("ix_dp_inv_cat", "investigation_id", "category"),)


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(128), default="")
    kind: Mapped[str] = mapped_column(String(20), default="post")  # post|comment|photo|video
    parent_external_id: Mapped[str] = mapped_column(String(128), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    created_time: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True, index=True)
    permalink: Mapped[str] = mapped_column(String(1000), default="")
    shared_link: Mapped[str] = mapped_column(String(1000), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    source_type: Mapped[str] = mapped_column(String(32), default=SourceType.graph_api.value)
    collected_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    investigation: Mapped[Investigation] = relationship(back_populates="posts")

    __table_args__ = (UniqueConstraint("investigation_id", "external_id", "kind", name="uq_post_ext"),)


class MediaItem(Base):
    __tablename__ = "media_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # profile_picture|cover_photo|photo|video|uploaded|web_image
    source_url: Mapped[str] = mapped_column(String(2000), default="")
    source_type: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128), default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    created_time: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    local_path: Mapped[str] = mapped_column(String(500), default="")
    mime_type: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    phash: Mapped[str] = mapped_column(String(16), default="")
    dhash: Mapped[str] = mapped_column(String(16), default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    duplicate_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="stored")  # stored|reference_only|error
    error_message: Mapped[str] = mapped_column(Text, default="")
    collected_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    investigation: Mapped[Investigation] = relationship(back_populates="media_items")


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2000))
    final_url: Mapped[str] = mapped_column(String(2000), default="")
    domain: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))  # fetched|blocked_robots|blocked_policy|not_permitted|rate_limited|not_found|error|not_configured
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    investigation: Mapped[Investigation] = relationship(back_populates="sources")


class CollectionEvent(Base):
    __tablename__ = "collection_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    step: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(10), default="info")  # info|warning|error
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    investigation: Mapped[Investigation] = relationship(back_populates="events")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)


class EncryptedCredential(Base):
    __tablename__ = "encrypted_credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))  # meta_app_secret|meta_access_token|meta_user_token
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("name", "owner_user_id", name="uq_cred_owner"),)


class OAuthState(Base):
    __tablename__ = "oauth_states"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class ReportExport(Base):
    __tablename__ = "report_exports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(8))
    language: Mapped[str] = mapped_column(String(5))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    applied_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


SCHEMA_VERSION = 1
