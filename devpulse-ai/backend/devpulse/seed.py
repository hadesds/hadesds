"""Carrega fontes de ``config/sources.yaml`` (cria as novas; não sobrescreve edições do painel)."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from devpulse.models import Source

log = logging.getLogger(__name__)
FIELDS = {"name", "connector_type", "url", "config", "category", "priority_tier", "reliability", "enabled",
          "fetch_interval_minutes", "notes"}


def load_sources_file(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        log.warning("Arquivo de fontes não encontrado: %s", p)
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("sources", [])


def seed_sources(session: Session, path: str | Path) -> dict:
    created, kept = 0, 0
    for entry in load_sources_file(path):
        slug = entry["slug"]
        if session.scalar(select(Source).where(Source.slug == slug)):
            kept += 1
            continue
        session.add(Source(slug=slug, **{k: v for k, v in entry.items() if k in FIELDS}))
        created += 1
    session.commit()
    return {"created": created, "existing": kept}
