"""Pipeline da edição diária. Cada etapa é idempotente e pode ser retomada."""
from __future__ import annotations

import logging
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from devpulse import http as http_mod
from devpulse.editorial_scoring.llm_refine import make_refiner
from devpulse.editorial_scoring.selection import candidate_clusters, score_candidates, select_for_edition
from devpulse.models import NewsItem, ScheduledRun, Script
from devpulse.news_ingestion.service import collect_all, enrich_pending
from devpulse.scheduler import deliveries
from devpulse.scheduler.runs import heartbeat
from devpulse.script_generation.generator import persist_script, produce_package
from devpulse.script_generation.llm import get_llm
from devpulse.settings_service import load as load_settings

log = logging.getLogger(__name__)


def scripts_today(session: Session, run: ScheduledRun) -> int:
    return session.scalar(
        select(func.count(Script.id)).where(Script.edition_date == run.edition_date, Script.status != "rejected")
    ) or 0


def _save_stats(session: Session, run: ScheduledRun, stats: dict) -> None:
    # sempre um dict novo: reatribuir o mesmo objeto mutado não é detectado pelo ORM
    run.stats = dict(stats)
    session.commit()


def run_edition(session: Session, run: ScheduledRun, *, collect: bool = True, deliver: bool = True,
                transports: dict | None = None, verify_links: bool = True) -> dict:
    cfg = load_settings(session)
    stats = dict(run.stats or {})

    if collect and not stats.get("collected"):
        heartbeat(session, run, "collect")
        stats["collect"] = collect_all(session, force=False, run_id=run.id)
        stats["collected"] = True
        _save_stats(session, run, stats)

    if not stats.get("generated"):
        heartbeat(session, run, "enrich")
        clusters = candidate_clusters(session, cfg)
        pending = [i for c in clusters for i in c.items if i.extraction_status == "pending"]
        pending.sort(key=lambda i: (i.source.priority_tier, -(i.published_at.timestamp() if i.published_at else 0)))
        stats["enriched"] = enrich_pending(session, pending, cfg.max_extractions_per_run)

        heartbeat(session, run, "score")
        llm = get_llm(session, cfg)
        refiner = make_refiner(llm, cfg) if llm else None
        scored = score_candidates(session, cfg, run_id=run.id, llm_refiner=refiner)
        quota = max(0, cfg.daily_script_limit - scripts_today(session, run))
        used = set(session.scalars(select(Script.cluster_id).where(Script.edition_date == run.edition_date)))
        cat_counts = Counter(session.scalars(
            select(Script.category).where(Script.edition_date == run.edition_date, Script.status != "rejected")
        ))
        stats.update(candidates=len(scored), eligible=sum(s.eligible for s in scored), quota=quota)

        heartbeat(session, run, "generate")
        produced, attempts = 0, 0
        position = (session.scalar(select(func.max(Script.position)).where(Script.edition_date == run.edition_date)) or 0) + 1
        http = http_mod.client() if verify_links else None
        try:
            while produced < quota and attempts < quota * 2 + 1:
                picks = select_for_edition(scored, quota - produced, cfg, exclude_cluster_ids=used, category_counts=cat_counts)
                if not picks:
                    break
                cs = picks[0]
                used.add(cs.cluster.id)
                attempts += 1
                try:
                    pkg, report = produce_package(session, cs, cfg, llm, http)
                    script = persist_script(session, pkg, report, cs, run.id, run.edition_date, position)
                    session.commit()
                except Exception:
                    session.rollback()
                    log.exception("Falha ao gerar roteiro para cluster %s", cs.cluster.id)
                    continue
                if script.status != "rejected":
                    produced += 1
                    cat_counts[script.category] += 1
                    position += 1
                heartbeat(session, run, "generate")
        finally:
            if http:
                http.close()
        reasons = Counter(r for s in scored if not s.eligible for r in s.reasons)
        stats["top_rejections"] = [f"{r} ({n} notícia(s))" for r, n in reasons.most_common(6)]
        stats["produced"] = produced
        stats["generated"] = True
        _save_stats(session, run, stats)

    if not deliver:
        stats["delivery"] = "Entregas não solicitadas nesta execução"
        _save_stats(session, run, stats)
        return stats
    heartbeat(session, run, "deliver")
    produced_now = len(deliveries.edition_scripts(session, run))
    if produced_now == 0 and run.slot != "main":
        stats["delivery"] = "Sem roteiros novos nesta execução complementar; nada enviado"
    else:
        deliveries.ensure_deliveries(session, run)
        stats["delivery"] = deliveries.dispatch_due(session, transports)
    _save_stats(session, run, stats)
    return stats


def run_collection(session: Session, run: ScheduledRun, force: bool = False) -> dict:
    heartbeat(session, run, "collect")
    stats = collect_all(session, force=force, run_id=run.id)
    stats["items_total"] = session.scalar(select(func.count(NewsItem.id)))
    _save_stats(session, run, stats)
    return stats
