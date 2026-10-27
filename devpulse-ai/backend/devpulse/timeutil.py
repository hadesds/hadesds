from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from devpulse.config import get_settings


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def local_now() -> datetime:
    return utcnow().astimezone(tz())


def local_today() -> date:
    return local_now().date()


def parse_hhmm(value: str) -> time | None:
    value = (value or "").strip()
    if not value:
        return None
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def local_dt(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=tz())


def ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
