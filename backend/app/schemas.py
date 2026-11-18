from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth/users
class SetupIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str = Field(default="", max_length=128)
    password: str = Field(min_length=1, max_length=256)


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserCreate(SetupIn):
    role: Literal["admin", "operator"] = "operator"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=128)
    role: Literal["admin", "operator"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


# ------------------------------------------------------------------ numbers
class ValidateIn(BaseModel):
    number: str = Field(min_length=1, max_length=40)
    region: str = Field(default="EG", min_length=2, max_length=2)
    investigation_id: int | None = None


class NumberCheckOut(ORM):
    id: int
    raw_input: str
    e164: str
    is_valid: bool
    investigation_id: int | None
    checked_at: datetime
    checked_by_username: str = ""
    result: dict


# ------------------------------------------------------------------ customers
class CustomerIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=160)
    address: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=5000)


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)


class CustomerOut(ORM):
    id: int
    full_name: str
    phone_e164: str
    email: str
    address: str
    notes: str
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ investigations
class InvestigationIn(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=5, max_length=2000, description="الغرض المشروع – إلزامي")
    customer_id: int | None = None
    notes: str = Field(default="", max_length=10000)


class InvestigationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    purpose: str | None = Field(default=None, min_length=5, max_length=2000)
    status: Literal["open", "closed"] | None = None
    customer_id: int | None = None
    notes: str | None = Field(default=None, max_length=10000)


class InvestigationOut(ORM):
    id: int
    ref_code: str
    phone_raw: str
    phone_e164: str
    title: str
    purpose: str
    status: str
    customer_id: int | None
    customer_name: str = ""
    notes: str
    validation: dict | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    created_by_username: str = ""


# ------------------------------------------------------------------ sources
class DataSourceOut(ORM):
    id: int
    key: str
    name: str
    url: str
    information: str
    limitations: str
    update_frequency: str
    license: str
    access_method: str
    is_builtin: bool
    enabled: bool


class DataSourceIn(BaseModel):
    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=160)
    url: str = Field(default="", max_length=300)
    information: str = Field(default="", max_length=4000)
    limitations: str = Field(default="", max_length=4000)
    update_frequency: str = Field(default="", max_length=160)
    license: str = Field(default="", max_length=4000)
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("يجب أن يبدأ الرابط بـ http:// أو https://")
        return v


class SourceRecordIn(BaseModel):
    data_source_id: int | None = None
    source_name: str = Field(min_length=1, max_length=160)
    source_url: str = Field(default="", max_length=500)
    source_type: Literal["official_registry", "website", "social_media", "document", "other"] = "website"
    observed_at: datetime
    summary: str = Field(min_length=1, max_length=10000)
    reliability: Literal["confirmed", "likely", "unverified"] = "unverified"

    @field_validator("source_url")
    @classmethod
    def _url(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("يجب أن يبدأ الرابط بـ http:// أو https://")
        return v


class SourceRecordOut(ORM):
    id: int
    investigation_id: int
    data_source_id: int | None
    source_name: str
    source_url: str
    source_type: str
    observed_at: datetime
    summary: str
    reliability: str
    created_at: datetime
    created_by_username: str = ""


# ------------------------------------------------------------------ locations
class InvitationIn(BaseModel):
    investigation_id: int | None = None
    customer_id: int | None = None
    phone: str = Field(default="", max_length=40)
    purpose: str = Field(min_length=5, max_length=1000)
    hours: int = Field(default=24, ge=1, le=168)


class InvitationOut(ORM):
    id: int
    investigation_id: int | None
    customer_id: int | None
    phone_e164: str
    purpose: str
    status: str
    effective_status: str
    created_at: datetime
    expires_at: datetime
    opened_at: datetime | None
    responded_at: datetime | None


class InvitationCreated(InvitationOut):
    link: str
    message_text: str
    whatsapp_url: str
    sms_uri: str


class ConsentIn(BaseModel):
    decision: Literal["accept", "decline"]
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=1_000_000)
    device_timestamp_ms: int | None = Field(default=None, ge=0)
    consent_text_version: str = Field(max_length=16)


class LocationOut(ORM):
    id: int
    invitation_id: int | None
    investigation_id: int | None
    customer_id: int | None
    latitude: float
    longitude: float
    accuracy_m: float | None
    device_timestamp: datetime | None
    collected_at: datetime
    consent_given_at: datetime
    consent_text_version: str
    source: str
    address_text: str
    is_current: bool = False
    label: str = ""


class AuditOut(ORM):
    id: int
    at: datetime
    username: str
    action: str
    entity_type: str
    entity_id: str
    details: dict | None
    ip: str
