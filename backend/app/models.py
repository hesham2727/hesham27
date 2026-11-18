"""SQLAlchemy ORM models.

Only portable column types are used so the schema migrates to PostgreSQL
without changes (see docs/DATABASE_MIGRATION_POSTGRESQL.md).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator):
    """Timezone-aware UTC datetime. SQLite stores naive values, so we
    normalise to UTC on write and re-attach UTC on read (PostgreSQL keeps tz)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            value = value.astimezone(timezone.utc)
            if dialect.name == "sqlite":
                value = value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="operator")  # admin | operator
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime())
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")

    user: Mapped[User] = relationship()


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160))
    phone_e164: Mapped[str] = mapped_column(String(20), default="", index=True)
    email: Mapped[str] = mapped_column(String(160), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    phone_raw: Mapped[str] = mapped_column(String(40))
    phone_e164: Mapped[str] = mapped_column(String(20), default="", index=True)
    title: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(Text)  # documented lawful purpose (mandatory)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open | closed
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    validation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    customer: Mapped[Customer | None] = relationship()
    creator: Mapped[User | None] = relationship()


class NumberCheck(Base):
    """Every validation request is logged – this is the investigation history."""

    __tablename__ = "number_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_input: Mapped[str] = mapped_column(String(40))
    e164: Mapped[str] = mapped_column(String(20), default="", index=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict] = mapped_column(JSON)
    investigation_id: Mapped[int | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    checked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)

    checker: Mapped[User | None] = relationship()


class DataSource(Base):
    """Catalogue of documented public data sources (name, URL, license...)."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(String(300))
    information: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[str] = mapped_column(Text, default="")
    update_frequency: Mapped[str] = mapped_column(String(160), default="")
    license: Mapped[str] = mapped_column(Text, default="")
    access_method: Mapped[str] = mapped_column(String(32), default="manual")  # manual | bundled | api
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class SourceRecord(Base):
    """A finding captured by an operator from a public source."""

    __tablename__ = "source_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    data_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str] = mapped_column(String(500), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="website")
    observed_at: Mapped[datetime] = mapped_column(TZDateTime())  # when the operator viewed it
    summary: Mapped[str] = mapped_column(Text)
    reliability: Mapped[str] = mapped_column(String(16), default="unverified")  # confirmed|likely|unverified
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)

    data_source: Mapped[DataSource | None] = relationship()
    creator: Mapped[User | None] = relationship()


class LocationInvitation(Base):
    __tablename__ = "location_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    investigation_id: Mapped[int | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    phone_e164: Mapped[str] = mapped_column(String(20), default="")
    purpose: Mapped[str] = mapped_column(Text)
    requester_label: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending | opened | shared | declined | revoked  (expired is computed)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime())
    opened_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    @property
    def effective_status(self) -> str:
        if self.status in ("pending", "opened") and self.expires_at <= utcnow():
            return "expired"
        return self.status


class LocationRecord(Base):
    """A single, consented, point-in-time location. Never 'current'."""

    __tablename__ = "location_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invitation_id: Mapped[int | None] = mapped_column(
        ForeignKey("location_invitations.id", ondelete="SET NULL"), nullable=True
    )
    investigation_id: Mapped[int | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    device_timestamp: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    consent_text_version: Mapped[str] = mapped_column(String(16))
    consent_given_at: Mapped[datetime] = mapped_column(TZDateTime())
    source: Mapped[str] = mapped_column(String(32), default="browser_geolocation_consent")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    address_text: Mapped[str] = mapped_column(Text, default="")  # optional reverse geocoding


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), default="")
    entity_id: Mapped[str] = mapped_column(String(32), default="")
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | bool | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)
