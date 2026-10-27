"""Documentos-fonte entregues ao gerador (sempre a partir do que foi coletado)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from devpulse.content_extraction.text import sentences

from devpulse.editorial_scoring.evidence import EvidenceProfile, item_text, item_tier
from devpulse.editorial_scoring.reliability import EVIDENCE_BY_TIER, domain
from devpulse.models import NewsItem

DOC_CHARS = 12_000


@dataclass
class SourceDoc:
    ref: str
    item: NewsItem
    url: str
    title: str
    publisher: str
    tier: int
    evidence_type: str
    published_at: str | None
    text: str


def boilerplate(session: Session, item: NewsItem, sample: int = 12) -> set[str]:
    """Frases repetidas em várias páginas da mesma fonte (rodapés, "sobre a empresa")."""
    others = session.scalars(
        select(NewsItem.content).where(NewsItem.source_id == item.source_id, NewsItem.id != item.id, NewsItem.content.is_not(None))
        .order_by(NewsItem.discovered_at.desc()).limit(sample)
    ).all()
    counts = Counter(s for text in others for s in set(sentences(text or "")))
    return {s for s, n in counts.items() if n >= 2}


def clean_text(session: Session, item: NewsItem) -> str:
    text = item_text(item)
    common = boilerplate(session, item)
    if not common:
        return text
    return "\n".join(line for line in text.splitlines() if not any(c in line for c in common) or len(line) > 400)


def build_docs(session: Session, rep: NewsItem, evidence: EvidenceProfile, max_docs: int = 4) -> list[SourceDoc]:
    pool = [rep] + [i for i in evidence.accessible_items if i.id != rep.id]
    docs = []
    for n, it in enumerate(pool[:max_docs], start=1):
        tier = item_tier(session, it)
        docs.append(
            SourceDoc(
                ref=f"S{n}",
                item=it,
                url=it.url,
                title=it.title,
                publisher=domain(it.url),
                tier=tier,
                evidence_type=EVIDENCE_BY_TIER.get(tier, "independent"),
                published_at=it.published_at.isoformat() if it.published_at else None,
                text=clean_text(session, it)[:DOC_CHARS],
            )
        )
    return docs
