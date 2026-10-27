"""Pontuação editorial 0–100 por agrupamento de notícias."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from devpulse.deduplication.similarity import title_similarity
from devpulse.editorial_scoring.categories import classify
from devpulse.editorial_scoring.evidence import EvidenceProfile, evidence_for_cluster, item_text
from devpulse.editorial_scoring.reliability import RELIABILITY_BY_TIER
from devpulse.models import NewsCluster, NewsItem, Script
from devpulse.settings_service import EditableSettings
from devpulse.timeutil import ensure_aware, local_today, utcnow

WEIGHTS = {
    "atualidade": 0.18,
    "relevancia_dev": 0.18,
    "confiabilidade": 0.16,
    "utilidade_pratica": 0.14,
    "potencial_visual": 0.09,
    "interesse_publico": 0.10,
    "originalidade": 0.08,
    "explicabilidade": 0.07,
}
PRACTICAL = re.compile(
    r"(?i)\b(release[sd]?|lança|launch|available|disponível|now supports|agora suporta|introduc|apresenta|"
    r"deprecat|descontinu|breaking|tutorial|how to|como |guide|guia|cli|api|sdk|update|atualiza|patch|"
    r"fix|correç|v?\d+\.\d+(\.\d+)?|beta|preview|open[- ]source|free tier|gratuit)"
)
VISUAL = re.compile(r"(?i)\b(demo|playground|ui|interface|dashboard|cli|terminal|editor|vscode|ide|screenshot|agent|code|código|extension|extensão|app)\b")
BRANDS = re.compile(
    r"(?i)\b(openai|chatgpt|anthropic|claude|google|gemini|github|copilot|microsoft|apple|meta|llama|nvidia|"
    r"aws|amazon|python|javascript|typescript|react|next\.js|node\.js|rust|docker|kubernetes|linux|vs ?code)\b"
)
HIGH_IMPACT = re.compile(r"(?i)(acquisition|acquires|aquisição|adquire|layoff|demiss|breach|vazamento|zero-day|0-day|ransomware|lawsuit|processo judicial)")


@dataclass
class ClusterScore:
    cluster: NewsCluster
    representative: NewsItem
    total: float
    components: dict[str, float]
    evidence: EvidenceProfile
    category: str
    eligible: bool = True
    reasons: list[str] = field(default_factory=list)
    rationale: str = ""
    method: str = "heuristic"


def representative_item(session: Session, cluster: NewsCluster, evidence: EvidenceProfile) -> NewsItem:
    pool = evidence.accessible_items or [i for i in cluster.items if not (i.raw or {}).get("duplicate_of")] or cluster.items
    from devpulse.editorial_scoring.evidence import item_tier

    return sorted(pool, key=lambda i: (item_tier(session, i), -len(item_text(i))))[0]


def _recency(cluster: NewsCluster, rep: NewsItem, freshness_hours: int) -> tuple[float, str | None]:
    published = ensure_aware(cluster.first_published_at or rep.published_at)
    if published is None:
        return 0.0, "Data de publicação original desconhecida"
    age_h = max(0.0, (utcnow() - published).total_seconds() / 3600)
    if age_h > freshness_hours:
        return 0.0, f"Publicada há {age_h:.0f}h (limite {freshness_hours}h)"
    score = 100 * math.exp(-age_h / max(12, freshness_hours / 2))
    if rep.published_at_inferred:
        score = min(score, 80)
    return round(score, 1), None


def recent_script_titles(session: Session, days: int) -> list[tuple[int, str]]:
    since = local_today() - timedelta(days=days)
    rows = session.execute(
        select(Script.cluster_id, Script.news_title).where(Script.edition_date >= since, Script.status != "rejected")
    ).all()
    return [(r[0], r[1]) for r in rows]


def score_cluster(session: Session, cluster: NewsCluster, cfg: EditableSettings, recent: list[tuple[int, str]]) -> ClusterScore:
    evidence = evidence_for_cluster(session, cluster)
    rep = representative_item(session, cluster, evidence)
    text = f"{rep.title} {rep.summary or ''} {(rep.content or '')[:3000]}"
    category, cat_scores = classify(rep.title, text, rep.category)
    reasons: list[str] = []

    recency, why = _recency(cluster, rep, cfg.freshness_hours)
    if why:
        reasons.append(why)

    relevance = min(100.0, max(cat_scores.values()) * 7)
    if category in cfg.priority_categories:
        relevance = min(100.0, relevance + 10)

    reliability = RELIABILITY_BY_TIER.get(evidence.best_tier, 0.5) * 85
    reliability += min(15, 7.5 * max(0, evidence.independent_groups - 1))
    if not evidence.accessible_items:
        reliability = min(reliability, 30)

    practical = min(100.0, 30 + 14 * len(set(m.group(0).lower() for m in PRACTICAL.finditer(text[:2500]))))
    has_image = any((i.raw or {}).get("extraction", {}).get("images") for i in cluster.items)
    has_repo = "github.com/" in " ".join(" ".join((i.raw or {}).get("extraction", {}).get("links", [])) for i in cluster.items)
    visual = min(100.0, 25 + 12 * len(set(m.group(0).lower() for m in VISUAL.finditer(text[:2500]))) + 15 * has_image + 15 * has_repo)

    points = max([int((i.raw or {}).get("points") or 0) for i in cluster.items] + [0])
    interest = 30 + min(30, 10 * len(set(m.group(0).lower() for m in BRANDS.finditer(rep.title))))
    interest += min(20, points / 25) + min(10, 5 * evidence.newsletter_mentions) + min(10, 3 * (len(evidence.domains) - 1))
    interest = min(100.0, interest)

    max_sim = max((title_similarity(rep.title, t) for cid, t in recent if cid != cluster.id), default=0.0)
    originality = round(100 * (1 - max_sim), 1)

    explain = 40.0 + (25 if len(item_text(rep)) > 600 else 10 if len(item_text(rep)) > 150 else 0)
    explain += 15 if 20 <= len(rep.title) <= 140 else 0
    explain -= 30 if rep.content_type in ("opinion", "rumor") else 0
    explain = max(0.0, min(100.0, explain + 10 * (rep.language in ("pt", "en"))))

    components = {
        "atualidade": recency,
        "relevancia_dev": round(relevance, 1),
        "confiabilidade": round(min(100.0, reliability), 1),
        "utilidade_pratica": round(practical, 1),
        "potencial_visual": round(visual, 1),
        "interesse_publico": round(interest, 1),
        "originalidade": originality,
        "explicabilidade": round(explain, 1),
    }
    total = round(sum(components[k] * w for k, w in WEIGHTS.items()), 1)
    return ClusterScore(cluster, rep, total, components, evidence, category, reasons=reasons)


def apply_eligibility(cs: ClusterScore, cfg: EditableSettings, recent: list[tuple[int, str]]) -> ClusterScore:
    ev, rep = cs.evidence, cs.representative
    reasons = list(cs.reasons)
    if not ev.accessible_items:
        reasons.append("Nenhum conteúdo da fonte acessível para sustentar o roteiro")
    if rep.content_type == "rumor":
        reasons.append("Classificada como rumor")
    high_impact = bool(HIGH_IMPACT.search(rep.title)) or (cs.category == "seguranca" and ev.best_tier > 2)
    if ev.best_tier > 2 and ev.independent_groups < 2:
        reasons.append("Sem fonte primária e sem confirmação independente")
    elif high_impact and ev.best_tier > 1 and ev.independent_groups < 2:
        reasons.append("Notícia de alto impacto sem segunda fonte independente")
    if cs.total < cfg.min_editorial_score:
        reasons.append(f"Pontuação {cs.total} abaixo do mínimo {cfg.min_editorial_score}")
    if cs.cluster.last_selected_on and (local_today() - cs.cluster.last_selected_on).days < cfg.topic_retention_days:
        reasons.append("Tema já usado dentro do período de retenção")
    elif cs.components["originalidade"] < 45:
        reasons.append("Muito semelhante a um roteiro recente")
    cs.reasons = reasons
    cs.eligible = not reasons
    return cs
