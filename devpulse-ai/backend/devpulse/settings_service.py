"""Configurações editáveis pelo painel (persistidas em ``application_settings``).

Somente parâmetros não sensíveis ficam aqui. Credenciais permanecem no ``.env``.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from devpulse.config import get_settings
from devpulse.models import ApplicationSetting

CATEGORIES = ["desenvolvimento", "ia", "infraestrutura", "seguranca", "mercado"]
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EditableSettings(BaseModel):
    edition_main_time: str
    edition_secondary_time: str = ""
    edition_catchup_until: str
    collect_interval_minutes: int = Field(ge=15, le=1440)
    daily_script_limit: int = Field(ge=0, le=3)
    min_editorial_score: float = Field(ge=0, le=100)
    exceptional_score: float = Field(ge=0, le=100)
    freshness_hours: int = Field(ge=6, le=24 * 14)
    topic_retention_days: int = Field(ge=0, le=60)
    priority_categories: list[str]
    max_per_category: int = Field(ge=1, le=3)
    email_recipient: str = ""
    whatsapp_recipient: str = ""
    whatsapp_recipient_opt_in: bool = False
    llm_provider: str
    llm_model_script: str
    llm_model_fast: str
    llm_max_calls_per_day: int = Field(ge=0, le=1000)
    max_extractions_per_run: int = Field(ge=0, le=200)

    @field_validator("edition_main_time", "edition_catchup_until")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("Use o formato HH:MM")
        return v

    @field_validator("edition_secondary_time")
    @classmethod
    def _opt_hhmm(cls, v: str) -> str:
        if v and not HHMM.match(v):
            raise ValueError("Use o formato HH:MM ou deixe vazio")
        return v

    @field_validator("priority_categories")
    @classmethod
    def _cats(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if c not in CATEGORIES]
        if bad:
            raise ValueError(f"Categorias inválidas: {bad}")
        return v

    @field_validator("email_recipient")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if v and not EMAIL.match(v):
            raise ValueError("E-mail inválido")
        return v

    @field_validator("whatsapp_recipient")
    @classmethod
    def _phone(cls, v: str) -> str:
        v = re.sub(r"[\s\-()]", "", v)
        if v and not E164.match(v):
            raise ValueError("Use o formato internacional E.164, ex.: +5598999999999")
        return v

    @field_validator("llm_provider")
    @classmethod
    def _provider(cls, v: str) -> str:
        if v not in {"anthropic", "openai_compatible", "none"}:
            raise ValueError("Provedor inválido")
        return v


def defaults() -> dict[str, Any]:
    s = get_settings()
    return {
        "edition_main_time": s.edition_main_time,
        "edition_secondary_time": s.edition_secondary_time,
        "edition_catchup_until": s.edition_catchup_until,
        "collect_interval_minutes": s.collect_interval_minutes,
        "daily_script_limit": s.daily_script_limit,
        "min_editorial_score": 55.0,
        "exceptional_score": 90.0,
        "freshness_hours": 72,
        "topic_retention_days": 10,
        "priority_categories": ["desenvolvimento", "ia"],
        "max_per_category": 1,
        "email_recipient": s.email_recipient,
        "whatsapp_recipient": s.whatsapp_recipient,
        "whatsapp_recipient_opt_in": s.whatsapp_recipient_opt_in,
        "llm_provider": s.llm_provider,
        "llm_model_script": s.llm_model_script,
        "llm_model_fast": s.llm_model_fast,
        "llm_max_calls_per_day": s.llm_max_calls_per_day,
        "max_extractions_per_run": 25,
    }


def load(session: Session) -> EditableSettings:
    values = defaults()
    for row in session.scalars(select(ApplicationSetting)):
        if row.key in values:
            values[row.key] = row.value
    return EditableSettings.model_validate(values)


def save(session: Session, changes: dict[str, Any]) -> EditableSettings:
    merged = load(session).model_dump() | changes
    validated = EditableSettings.model_validate(merged)
    for key in changes:
        if key not in EditableSettings.model_fields:
            continue
        row = session.get(ApplicationSetting, key)
        value = getattr(validated, key)
        if row is None:
            session.add(ApplicationSetting(key=key, value=value))
        else:
            row.value = value
    # versão usada pelo worker para reprogramar a agenda
    version = session.get(ApplicationSetting, "_version")
    if version is None:
        session.add(ApplicationSetting(key="_version", value=1))
    else:
        version.value = int(version.value or 0) + 1
    session.commit()
    return validated


def version(session: Session) -> int:
    row = session.get(ApplicationSetting, "_version")
    return int(row.value) if row else 0
