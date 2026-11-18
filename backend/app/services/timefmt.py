from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo("Africa/Cairo")  # needs the 'tzdata' package on Windows


def local(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CAIRO).strftime("%Y-%m-%d %H:%M")


def age_ar(dt: datetime | None, now: datetime | None = None) -> str:
    """Human-readable age, e.g. 'منذ 3 ساعات'. Used to label historical data."""
    if dt is None:
        return ""
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = max(0, int((now - dt).total_seconds()))
    if secs < 60:
        return "منذ أقل من دقيقة"
    mins = secs // 60
    if mins < 60:
        return f"منذ {mins} دقيقة"
    hours = mins // 60
    if hours < 48:
        return f"منذ {hours} ساعة"
    return f"منذ {hours // 24} يوم"
