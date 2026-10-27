"""Seleção da edição: até N notícias, com diversidade de categorias."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from devpulse.editorial_scoring.scorer import ClusterScore, apply_eligibility, recent_script_titles, score_cluster
from devpulse.models import EditorialScore, NewsCluster, NewsItem
from devpulse.settings_service import EditableSettings
from devpulse.timeutil import utcnow


def candidate_clusters(session: Session, cfg: EditableSettings) -> list[NewsCluster]:
    since = utcnow() - timedelta(hours=cfg.freshness_hours)
    ids = session.scalars(
        select(NewsItem.cluster_id)
        .where(NewsItem.cluster_id.is_not(None))
        .where(or_(NewsItem.published_at >= since, NewsItem.published_at.is_(None) & (NewsItem.discovered_at >= since)))
        .distinct()
    ).all()
    if not ids:
        return []
    return list(
        session.scalars(
            select(NewsCluster)
            .where(NewsCluster.id.in_(ids))
            .options(selectinload(NewsCluster.items).selectinload(NewsItem.references))
        )
    )


def score_candidates(session: Session, cfg: EditableSettings, run_id: str | None = None, llm_refiner=None) -> list[ClusterScore]:
    recent = recent_script_titles(session, cfg.topic_retention_days)
    scored = [score_cluster(session, c, cfg, recent) for c in candidate_clusters(session, cfg)]
    scored.sort(key=lambda s: s.total, reverse=True)
    if llm_refiner is not None:
        llm_refiner(scored[:12])
        scored.sort(key=lambda s: s.total, reverse=True)
    for cs in scored:
        apply_eligibility(cs, cfg, recent)
        cs.representative.editorial_score = cs.total
        cs.cluster.category = cs.category
        session.add(
            EditorialScore(
                cluster_id=cs.cluster.id,
                news_item_id=cs.representative.id,
                scheduled_run_id=run_id,
                total=cs.total,
                components=cs.components,
                method=cs.method,
                rationale=cs.rationale or None,
                eligible=cs.eligible,
                ineligibility_reason="; ".join(cs.reasons) or None,
            )
        )
    session.commit()
    return scored


def select_for_edition(scored: list[ClusterScore], quota: int, cfg: EditableSettings,
                       exclude_cluster_ids: set[int] = frozenset(), category_counts: dict[str, int] | None = None) -> list[ClusterScore]:
    """Escolhe por pontuação, limitando notícias da mesma categoria no dia
    (``max_per_category``), exceto acontecimentos excepcionais."""
    eligible = [s for s in scored if s.eligible and s.cluster.id not in exclude_cluster_ids]
    chosen: list[ClusterScore] = []
    per_cat: dict[str, int] = dict(category_counts or {})
    for cs in eligible:
        if len(chosen) >= quota:
            break
        n = per_cat.get(cs.category, 0)
        if n >= cfg.max_per_category and cs.total < cfg.exceptional_score:
            continue
        chosen.append(cs)
        per_cat[cs.category] = n + 1
    return chosen


def selection_reason(cs: ClusterScore) -> str:
    top = sorted(cs.components.items(), key=lambda kv: kv[1], reverse=True)[:3]
    labels = ", ".join(f"{k.replace('_', ' ')} {v:.0f}" for k, v in top)
    ev = cs.evidence
    base = f"Pontuação {cs.total:.0f}/100 (destaques: {labels}). "
    if ev.best_tier <= 2:
        base += "Sustentada por fonte primária/oficial"
    else:
        base += f"Confirmada por {ev.independent_groups} fontes independentes"
    if ev.newsletter_mentions:
        base += f"; citada em {ev.newsletter_mentions} newsletter(s)"
    return base + "."
