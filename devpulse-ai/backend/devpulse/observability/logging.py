"""Logs estruturados em JSON com remoção de segredos e dados pessoais."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

from devpulse.config import SECRET_FIELD_NAMES, get_settings

_PATTERNS = [
    re.compile(r"(?i)(authorization|bearer|token|password|senha|api[_-]?key|secret)([\"'=:\s]+)([^\s\"',;]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"EAA[A-Za-z0-9]{20,}"),  # tokens da Meta
]
_EMAIL = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+)")
_PHONE = re.compile(r"\+?\d{2}\d{6,}(\d{2})")


def _secret_values() -> list[str]:
    s = get_settings()
    vals = []
    for name in SECRET_FIELD_NAMES:
        v = getattr(s, name).get_secret_value()
        if v and len(v) >= 6:
            vals.append(v)
    return vals


def redact(text: str) -> str:
    for v in _secret_values():
        text = text.replace(v, "***")
    for p in _PATTERNS[1:]:
        text = p.sub("***", text)
    return _PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


def mask_email(value: str) -> str:
    return _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", value or "")


def mask_phone(value: str) -> str:
    return _PHONE.sub(lambda m: f"***{m.group(1)}", value or "")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for key in ("run_id", "source", "channel", "script_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(get_settings().log_level.upper())
    for noisy in ("httpx", "httpcore", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
