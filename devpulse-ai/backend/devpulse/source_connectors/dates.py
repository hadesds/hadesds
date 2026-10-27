from __future__ import annotations

import calendar
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def from_struct(st: time.struct_time | None) -> datetime | None:
    if not st:
        return None
    return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)


def parse_any(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    s = str(value).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        # só a data (sem horário): meia-noite no fuso configurado, não em UTC
        from devpulse.timeutil import tz

        try:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=tz())
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
