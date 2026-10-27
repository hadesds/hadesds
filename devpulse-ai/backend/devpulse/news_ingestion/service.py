"""Coleta incremental: executa conectores, deduplica, classifica e agrupa."""
from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from devpulse import http as http_mod
from devpulse.content_extraction.extractor import extract
from devpulse.content_extraction.text import detect_language, truncate
from devpulse.deduplication.clustering import assign_cluster
from devpulse.deduplication.normalize import content_hash, normalize_url, title_fingerprint
from devpulse.editorial_scoring.categories import classify, content_type
from devpulse.models import NewsItem, Source, SourceReference, SourceRun
from devpulse.source_connectors.base import ConnectorContext, ConnectorError, RawItem
from devpulse.source_connectors.registry import get_connector
from devpulse.timeutil import ensure_aware, utcnow

log = logging.getLogger(__name__)
CONTENT_LIMIT = 20_000  # guardamos apenas o necessário para análise e checagem


def _add_reference(session: Session, item: NewsItem, source: Source, raw: RawItem) -> None:
    exists = session.scalar(
        select(SourceReference).where(
            SourceReference.news_item_id == item.id,
            SourceReference.source_id == source.id,
            SourceReference.url == raw.url,
        )
    )
    if not exists:
        session.add(
            SourceReference(
                news_item_id=item.id, source_id=source.id, url=raw.url, title=raw.title,
                reference_type=raw.reference_type,
            )
        )


def persist_item(session: Session, source: Source, raw: RawItem) -> tuple[str, NewsItem]:
    """Retorna ("new"|"duplicate"|"updated", item)."""
    norm = normalize_url(raw.url)
    by_ext = session.scalar(
        select(NewsItem).where(NewsItem.source_id == source.id, NewsItem.external_id == raw.external_id[:500])
    )
    if by_ext:
        if raw.updated_at and (not by_ext.source_updated_at or raw.updated_at > ensure_aware(by_ext.source_updated_at)):
            by_ext.source_updated_at = raw.updated_at
            return "updated", by_ext
        return "duplicate", by_ext
    by_url = session.scalar(select(NewsItem).where(NewsItem.normalized_url == norm))
    if by_url:
        _add_reference(session, by_url, source, raw)
        return "duplicate", by_url

    text_for_class = f"{raw.summary} {raw.content}"
    category, _ = classify(raw.title, text_for_class, raw.category_hint or source.category)
    item = NewsItem(
        source_id=source.id,
        external_id=raw.external_id[:500],
        url=raw.url,
        normalized_url=norm,
        title=raw.title,
        title_fingerprint=title_fingerprint(raw.title),
        summary=raw.summary or None,
        content=truncate(raw.content, CONTENT_LIMIT) or None,
        content_access=raw.content_access,
        content_hash=content_hash(raw.content) if raw.content else None,
        author=raw.author,
        published_at=raw.published_at,
        published_at_inferred=raw.raw.get("published_at_origin") == "newsletter_date",
        source_updated_at=raw.updated_at,
        discovered_at=utcnow(),
        language=raw.language or detect_language(f"{raw.title} {raw.summary}"),
        category=category,
        content_type=content_type(raw.title, raw.summary),
        verification_status="source_only",
        extraction_status="done" if raw.content_access == "full" else "pending",
        raw=raw.raw,
    )
    session.add(item)
    session.flush()
    _add_reference(session, item, source, raw)
    assign_cluster(session, item)
    return "new", item


def collect_source(session: Session, source: Source, http: httpx.Client | None = None, run_id: str | None = None) -> SourceRun:
    run = SourceRun(source_id=source.id, scheduled_run_id=run_id, status="running")
    session.add(run)
    session.flush()
    own_client = http is None
    http = http or http_mod.client()
    state = dict((source.config or {}).get("state", {}))
    try:
        connector = get_connector(source.connector_type)
        cfg = {k: v for k, v in (source.config or {}).items() if k != "state"}
        result = connector.fetch(
            ConnectorContext(http=http, source_config=cfg, source_url=source.url, state=state, since=source.last_success_at)
        )
        run.items_found = len(result.items)
        for raw in result.items:
            try:
                with session.begin_nested():
                    status, _ = persist_item(session, source, raw)
                if status == "new":
                    run.items_new += 1
                else:
                    run.items_duplicate += 1
            except Exception as e:  # um item ruim não derruba a coleta
                log.warning("Item ignorado de %s: %s", source.slug, e)
                result.warnings.append(f"Item ignorado: {type(e).__name__}")
        run.status = "partial" if result.warnings and run.items_found == 0 else "success"
        run.details = {"warnings": result.warnings[:20]}
        source.config = {**(source.config or {}), "state": result.state or state}
        source.last_success_at = utcnow()
        source.last_error = None
        source.consecutive_failures = 0
    except (ConnectorError, httpx.HTTPError, KeyError, ValueError) as e:
        run.status = "failed"
        run.error = f"{type(e).__name__}: {e}"[:1000]
        source.last_error = run.error
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        log.warning("Coleta falhou para %s: %s", source.slug, run.error)
    finally:
        run.finished_at = utcnow()
        source.last_run_at = run.finished_at
        if own_client:
            http.close()
    session.commit()
    return run


def due_sources(session: Session, force: bool = False) -> list[Source]:
    sources = session.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.priority_tier)).all()
    if force:
        return list(sources)
    now = utcnow()
    out = []
    for s in sources:
        last = ensure_aware(s.last_run_at)
        # recuo progressivo para fontes que falham repetidamente
        backoff = min(2 ** max(0, (s.consecutive_failures or 0) - 1), 24)
        if last is None or now - last >= timedelta(minutes=s.fetch_interval_minutes * backoff) - timedelta(minutes=1):
            out.append(s)
    return out


def collect_all(session: Session, force: bool = False, run_id: str | None = None) -> dict:
    stats = {"sources": 0, "failed": 0, "new": 0, "duplicate": 0}
    with http_mod.client() as http:
        for source in due_sources(session, force=force):
            run = collect_source(session, source, http=http, run_id=run_id)
            stats["sources"] += 1
            stats["failed"] += run.status == "failed"
            stats["new"] += run.items_new
            stats["duplicate"] += run.items_duplicate
    return stats


def enrich_item(session: Session, item: NewsItem, http: httpx.Client) -> None:
    """Busca o conteúdo acessível do link original e completa metadados."""
    page = extract(http, item.url)
    item.raw = {**(item.raw or {}), "extraction": {
        "final_url": page.final_url, "status": page.status_code, "images": page.images,
        "links": page.links[:80], "extracted_published_at": page.published_at.isoformat() if page.published_at else None,
    }}
    if not page.accessible:
        item.extraction_status = "failed"
        item.extraction_error = page.error
        if page.access == "restricted":
            item.content_access = "restricted"
        return
    final_norm = normalize_url(page.final_url)
    if final_norm != item.normalized_url:
        other = session.scalar(select(NewsItem).where(NewsItem.normalized_url == final_norm))
        if other and other.id != item.id:
            # o link (ex.: redirecionamento da newsletter) aponta para matéria já conhecida
            for ref in list(item.references):
                _add_reference(session, other, ref.source, RawItem(external_id="", url=ref.url, title=ref.title or "", reference_type=ref.reference_type))
            item.extraction_status = "skipped"
            item.extraction_error = f"Duplicata de #{other.id} após redirecionamento"
            item.cluster_id = other.cluster_id
            item.raw = {**item.raw, "duplicate_of": other.id}
            return
        item.normalized_url = final_norm
        item.url = page.final_url
    item.extraction_status = "done"
    item.extraction_error = None
    if page.text and len(page.text) > len(item.content or ""):
        item.content = truncate(page.text, CONTENT_LIMIT)
        item.content_hash = content_hash(page.text)
        item.content_access = page.access
    if not item.summary and page.description:
        item.summary = truncate(page.description, 1200)
    if page.published_at and (item.published_at is None or item.published_at_inferred):
        item.published_at = page.published_at
        item.published_at_inferred = False
    if page.modified_at and not item.source_updated_at:
        item.source_updated_at = page.modified_at
    if not item.author and page.author:
        item.author = page.author[:300]
    if page.language and not item.language:
        item.language = page.language
    category, _ = classify(item.title, f"{item.summary or ''} {item.content or ''}", item.category)
    item.category = category


def enrich_pending(session: Session, items: list[NewsItem], limit: int) -> int:
    done = 0
    with http_mod.client() as http:
        for item in items:
            if done >= limit:
                break
            if item.extraction_status not in ("pending",):
                continue
            try:
                with session.begin_nested():
                    enrich_item(session, item, http)
            except Exception as e:
                item.extraction_status = "failed"
                item.extraction_error = f"{type(e).__name__}"
            done += 1
        session.commit()
    return done
