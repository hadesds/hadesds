"""Avalia a base de evidências de um agrupamento de notícias."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from devpulse.deduplication.similarity import SAME_TEXT_THRESHOLD, content_similarity
from devpulse.editorial_scoring.reliability import domain, tier_for_url
from devpulse.models import NewsCluster, NewsItem


@dataclass
class EvidenceProfile:
    best_tier: int
    primary_urls: list[str] = field(default_factory=list)
    independent_groups: int = 0
    domains: list[str] = field(default_factory=list)
    accessible_items: list[NewsItem] = field(default_factory=list)
    newsletter_mentions: int = 0
    notes: list[str] = field(default_factory=list)


def item_text(item: NewsItem) -> str:
    return f"{item.summary or ''}\n{item.content or ''}".strip()


def item_tier(session: Session, item: NewsItem) -> int:
    if item.source and item.source.connector_type not in ("json_api", "email_newsletter", "webpage"):
        return item.source.priority_tier
    return tier_for_url(session, item.url, default=item.source.priority_tier if item.source else 4)


def evidence_for_cluster(session: Session, cluster: NewsCluster) -> EvidenceProfile:
    items = [i for i in cluster.items if not (i.raw or {}).get("duplicate_of")]
    prof = EvidenceProfile(best_tier=5)
    groups: list[tuple[str, str]] = []  # (domínio, texto)
    for it in items:
        refs = it.references
        prof.newsletter_mentions += sum(r.reference_type == "newsletter_mention" for r in refs)
        text = item_text(it)
        accessible = len(text) >= 120 and it.content_access != "restricted"
        tier = item_tier(session, it)
        if accessible:
            prof.accessible_items.append(it)
            prof.best_tier = min(prof.best_tier, tier)
            if tier <= 2:
                prof.primary_urls.append(it.url)
        elif it.content_access == "restricted":
            prof.notes.append(f"Conteúdo restrito em {domain(it.url)} — usado apenas o que é público")
        dom = domain(it.url)
        if dom not in prof.domains:
            prof.domains.append(dom)
        if not accessible or tier == 5:
            continue  # agregadores e páginas sem conteúdo não confirmam nada sozinhos
        # mesma redação em domínios diferentes = mesmo comunicado, não confirmação independente
        if any(d == dom or content_similarity(text, t) >= SAME_TEXT_THRESHOLD for d, t in groups):
            continue
        groups.append((dom, text))
    prof.independent_groups = len(groups)
    if prof.newsletter_mentions and not prof.accessible_items:
        prof.notes.append("Somente menção em newsletter; matéria original não acessível")
    return prof
