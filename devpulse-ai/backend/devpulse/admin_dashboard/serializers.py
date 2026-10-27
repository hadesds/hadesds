from __future__ import annotations

from devpulse.models import NewsItem, NotificationDelivery, ScheduledRun, Script, Source, SourceRun
from devpulse.observability.logging import mask_email, mask_phone


def iso(dt):
    return dt.isoformat() if dt else None


def source(s: Source, last_run: SourceRun | None = None) -> dict:
    return {
        "id": s.id, "slug": s.slug, "name": s.name, "connector_type": s.connector_type, "url": s.url,
        "config": {k: v for k, v in (s.config or {}).items() if k != "state"}, "category": s.category,
        "priority_tier": s.priority_tier, "reliability": s.reliability, "enabled": s.enabled,
        "fetch_interval_minutes": s.fetch_interval_minutes, "notes": s.notes, "last_run_at": iso(s.last_run_at),
        "last_success_at": iso(s.last_success_at), "last_error": s.last_error,
        "consecutive_failures": s.consecutive_failures, "last_run": source_run(last_run) if last_run else None,
    }


def source_run(r: SourceRun) -> dict:
    return {"id": r.id, "source_id": r.source_id, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
            "status": r.status, "items_found": r.items_found, "items_new": r.items_new,
            "items_duplicate": r.items_duplicate, "error": r.error, "details": r.details}


def news(i: NewsItem, full: bool = False) -> dict:
    d = {
        "id": i.id, "title": i.title, "url": i.url, "source": {"id": i.source.id, "name": i.source.name} if i.source else None,
        "summary": i.summary, "author": i.author, "published_at": iso(i.published_at),
        "published_at_inferred": i.published_at_inferred, "source_updated_at": iso(i.source_updated_at),
        "discovered_at": iso(i.discovered_at), "language": i.language, "category": i.category,
        "content_type": i.content_type, "verification_status": i.verification_status,
        "content_access": i.content_access, "extraction_status": i.extraction_status,
        "editorial_score": i.editorial_score, "cluster_id": i.cluster_id,
    }
    if full:
        d["content_excerpt"] = (i.content or "")[:3000]
        d["extraction_error"] = i.extraction_error
        d["references"] = [
            {"source": r.source.name if r.source else None, "url": r.url, "type": r.reference_type, "seen_at": iso(r.seen_at)}
            for r in i.references
        ]
    return d


def script(s: Script, full: bool = False) -> dict:
    d = {
        "id": s.id, "edition_date": s.edition_date.isoformat(), "position": s.position, "status": s.status,
        "news_title": s.news_title, "video_title": s.video_title, "category": s.category,
        "editorial_score": s.editorial_score, "estimated_duration_seconds": s.estimated_duration_seconds,
        "generator": s.generator, "edited_manually": s.edited_manually, "selection_reason": s.selection_reason,
        "verification": s.verification_summary, "rejection_reason": s.rejection_reason,
        "created_at": iso(s.created_at), "updated_at": iso(s.updated_at),
    }
    if full:
        d["package"] = s.package
        d["markdown"] = s.markdown
        d["scenes"] = [{"order": c.order, "section": c.section, "start_second": c.start_second, "end_second": c.end_second,
                        "speech": c.speech, "action": c.action, "on_screen": c.on_screen, "overlay_text": c.overlay_text,
                        "editing_notes": c.editing_notes, "visual_resource": c.visual_resource} for c in s.scenes]
        d["fact_checks"] = [{"claim": f.claim, "claim_type": f.claim_type, "is_central": f.is_central, "source_url": f.source_url,
                             "evidence_type": f.evidence_type, "result": f.result, "notes": f.notes, "quote": f.evidence_quote}
                            for f in s.fact_checks]
        d["media_assets"] = [{"scene": m.scene_order, "kind": m.kind, "url": m.url, "source_page_url": m.source_page_url,
                              "description": m.description, "license_info": m.license_info, "accessible": m.accessible}
                             for m in s.media_assets]
    return d


def delivery(d: NotificationDelivery) -> dict:
    rec = mask_email(d.recipient) if d.channel == "email" else mask_phone(d.recipient)
    return {"id": d.id, "run_id": d.scheduled_run_id, "edition_date": d.edition_date.isoformat(), "channel": d.channel,
            "recipient": rec, "status": d.status, "attempts": d.attempts, "next_attempt_at": iso(d.next_attempt_at),
            "last_error": d.last_error, "provider": d.provider, "provider_message_id": d.provider_message_id,
            "provider_status": d.provider_status, "attempt_log": d.attempt_log, "payload_summary": d.payload_summary,
            "sent_at": iso(d.sent_at), "created_at": iso(d.created_at)}


def run(r: ScheduledRun) -> dict:
    return {"id": r.id, "run_key": r.run_key, "kind": r.kind, "slot": r.slot,
            "edition_date": r.edition_date.isoformat() if r.edition_date else None, "trigger": r.trigger,
            "scheduled_for": iso(r.scheduled_for), "status": r.status, "step": r.step, "attempts": r.attempts,
            "started_at": iso(r.started_at), "finished_at": iso(r.finished_at), "error": r.error, "stats": r.stats,
            "created_at": iso(r.created_at)}
