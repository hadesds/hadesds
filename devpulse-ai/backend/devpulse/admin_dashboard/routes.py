from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from devpulse import settings_service
from devpulse.admin_dashboard import serializers as ser
from devpulse.admin_dashboard.auth import login, require_auth
from devpulse.config import get_settings
from devpulse.db import get_db
from devpulse.email_delivery.smtp import SmtpTransport
from devpulse.models import (
    EditorialScore,
    LlmUsage,
    NewsCluster,
    NewsItem,
    NotificationDelivery,
    ScheduledRun,
    Script,
    ScriptScene,
    Source,
    SourceRun,
)
from devpulse.news_ingestion.service import collect_source
from devpulse.scheduler.deliveries import manual_resend
from devpulse.scheduler.jobs import request_manual
from devpulse.script_generation.render import to_markdown
from devpulse.script_generation.schema import ScriptPackage
from devpulse.source_connectors.registry import available, get_connector
from devpulse.timeutil import local_dt, local_now, local_today, parse_hhmm, tz
from devpulse.whatsapp_delivery.cloud_api import WhatsAppTransport

public = APIRouter(prefix="/api")
api = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}$")


class LoginIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@public.post("/auth/login")
def do_login(body: LoginIn, request: Request) -> dict:
    return {"token": login(request, body.username, body.password)}


@public.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ok", "time": local_now().isoformat()}


# ---------------------------------------------------------------- dashboard
def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz())
    return start, start + timedelta(days=1)


def next_runs(cfg: settings_service.EditableSettings) -> list[dict]:
    now = local_now()
    out = []
    for slot, hhmm in (("main", cfg.edition_main_time), ("secondary", cfg.edition_secondary_time)):
        at = parse_hhmm(hhmm)
        if at is None:
            continue
        when = local_dt(now.date(), at)
        if when <= now:
            when = local_dt(now.date() + timedelta(days=1), at)
        out.append({"slot": slot, "at": when.isoformat()})
    return sorted(out, key=lambda r: r["at"])


@api.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    today = local_today()
    start, end = _day_bounds(today)
    cfg = settings_service.load(db)
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    last_run = db.scalar(select(ScheduledRun).where(ScheduledRun.kind == "edition").order_by(ScheduledRun.created_at.desc()))
    llm = db.execute(
        select(func.count(LlmUsage.id), func.coalesce(func.sum(LlmUsage.estimated_cost_usd), 0.0)).where(LlmUsage.day == today)
    ).one()
    return {
        "today": today.isoformat(),
        "collected_today": count(select(func.count(NewsItem.id)).where(NewsItem.discovered_at.between(start, end))),
        "analyzed_today": count(select(func.count(func.distinct(EditorialScore.cluster_id))).where(EditorialScore.computed_at.between(start, end))),
        "scripts_today": count(select(func.count(Script.id)).where(Script.edition_date == today, Script.status != "rejected")),
        "daily_limit": cfg.daily_script_limit,
        "notifications_sent_today": count(select(func.count(NotificationDelivery.id)).where(NotificationDelivery.edition_date == today, NotificationDelivery.status == "sent")),
        "errors_today": {
            "sources": count(select(func.count(SourceRun.id)).where(SourceRun.status == "failed", SourceRun.started_at.between(start, end))),
            "deliveries": count(select(func.count(NotificationDelivery.id)).where(NotificationDelivery.edition_date == today, NotificationDelivery.status.in_(["failed", "failed_auth", "needs_review"]))),
            "runs": count(select(func.count(ScheduledRun.id)).where(ScheduledRun.status == "failed", ScheduledRun.created_at.between(start, end))),
        },
        "pending": {
            "runs": count(select(func.count(ScheduledRun.id)).where(ScheduledRun.status.in_(["pending", "running"]))),
            "deliveries": count(select(func.count(NotificationDelivery.id)).where(NotificationDelivery.status.in_(["pending", "retrying", "sending"]))),
        },
        "last_edition_run": ser.run(last_run) if last_run else None,
        "next_runs": next_runs(cfg),
        "llm_today": {"calls": llm[0], "estimated_cost_usd": round(float(llm[1]), 4), "limit_calls": cfg.llm_max_calls_per_day},
        "recent_runs": [ser.run(r) for r in db.scalars(select(ScheduledRun).order_by(ScheduledRun.created_at.desc()).limit(10))],
    }


# ---------------------------------------------------------------- fontes
class SourceIn(BaseModel):
    slug: str
    name: str = Field(min_length=2, max_length=200)
    connector_type: str
    url: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    category: str | None = None
    priority_tier: int = Field(4, ge=1, le=5)
    reliability: float = Field(0.7, ge=0, le=1)
    enabled: bool = True
    fetch_interval_minutes: int = Field(60, ge=15, le=1440)
    notes: str | None = None


def _validate_source(body: SourceIn) -> None:
    if not SLUG.match(body.slug):
        raise HTTPException(422, "slug deve conter apenas letras minúsculas, números e hífens")
    if body.url and not body.url.startswith(("http://", "https://")):
        raise HTTPException(422, "URL deve começar com http:// ou https://")
    if body.category and body.category not in settings_service.CATEGORIES:
        raise HTTPException(422, f"Categoria inválida; use {settings_service.CATEGORIES}")
    try:
        errors = get_connector(body.connector_type).validate_config(body.url, body.config)
    except KeyError:
        raise HTTPException(422, f"Tipo de conector desconhecido: {body.connector_type}") from None
    if errors:
        raise HTTPException(422, "; ".join(errors))


@api.get("/connectors")
def connectors() -> list[dict]:
    return [{"type": k, "description": v.description, "config_fields": v.config_fields} for k, v in sorted(available().items())]


@api.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for s in db.scalars(select(Source).order_by(Source.priority_tier, Source.name)):
        last = db.scalar(select(SourceRun).where(SourceRun.source_id == s.id).order_by(SourceRun.started_at.desc()))
        out.append(ser.source(s, last))
    return out


@api.post("/sources", status_code=201)
def create_source(body: SourceIn, db: Session = Depends(get_db)) -> dict:
    _validate_source(body)
    if db.scalar(select(Source).where(Source.slug == body.slug)):
        raise HTTPException(409, "Já existe uma fonte com esse slug")
    s = Source(**body.model_dump())
    db.add(s)
    db.commit()
    return ser.source(s)


@api.put("/sources/{source_id}")
def update_source(source_id: int, body: SourceIn, db: Session = Depends(get_db)) -> dict:
    s = db.get(Source, source_id) or _404()
    _validate_source(body)
    state = (s.config or {}).get("state")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    if state:
        s.config = {**s.config, "state": state}
    db.commit()
    return ser.source(s)


@api.post("/sources/{source_id}/toggle")
def toggle_source(source_id: int, db: Session = Depends(get_db)) -> dict:
    s = db.get(Source, source_id) or _404()
    s.enabled = not s.enabled
    db.commit()
    return ser.source(s)


@api.post("/sources/{source_id}/collect")
def collect_now(source_id: int, db: Session = Depends(get_db)) -> dict:
    s = db.get(Source, source_id) or _404()
    return ser.source_run(collect_source(db, s))


@api.get("/sources/{source_id}/runs")
def source_runs(source_id: int, db: Session = Depends(get_db)) -> list[dict]:
    return [ser.source_run(r) for r in db.scalars(
        select(SourceRun).where(SourceRun.source_id == source_id).order_by(SourceRun.started_at.desc()).limit(30))]


# ---------------------------------------------------------------- notícias
@api.get("/news")
def list_news(
    db: Session = Depends(get_db), q: str | None = None, category: str | None = None,
    date_from: date | None = None, date_to: date | None = None, min_score: float | None = None,
    source_id: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
) -> dict:
    stmt = select(NewsItem).options(selectinload(NewsItem.source))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(NewsItem.title.ilike(like), NewsItem.summary.ilike(like)))
    if category:
        stmt = stmt.where(NewsItem.category == category)
    if date_from:
        stmt = stmt.where(func.coalesce(NewsItem.published_at, NewsItem.discovered_at) >= _day_bounds(date_from)[0])
    if date_to:
        stmt = stmt.where(func.coalesce(NewsItem.published_at, NewsItem.discovered_at) < _day_bounds(date_to)[1])
    if min_score is not None:
        stmt = stmt.where(NewsItem.editorial_score >= min_score)
    if source_id:
        stmt = stmt.where(NewsItem.source_id == source_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(func.coalesce(NewsItem.published_at, NewsItem.discovered_at).desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return {"total": total, "page": page, "items": [ser.news(i) for i in rows]}


@api.get("/news/{item_id}")
def get_news(item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.get(NewsItem, item_id) or _404()
    d = ser.news(item, full=True)
    related = []
    if item.cluster_id:
        cluster = db.get(NewsCluster, item.cluster_id)
        related = [ser.news(i) for i in cluster.items if i.id != item.id]
    d["related"] = related
    d["scores"] = [{"total": s.total, "components": s.components, "method": s.method, "eligible": s.eligible,
                    "reason": s.ineligibility_reason, "rationale": s.rationale, "computed_at": ser.iso(s.computed_at)}
                   for s in db.scalars(select(EditorialScore).where(EditorialScore.cluster_id == item.cluster_id)
                                       .order_by(EditorialScore.computed_at.desc()).limit(5))]
    return d


# ---------------------------------------------------------------- roteiros
@api.get("/scripts")
def list_scripts(db: Session = Depends(get_db), status: str | None = None, date_from: date | None = None,
                 q: str | None = None, include_rejected: bool = False) -> list[dict]:
    stmt = select(Script)
    if status:
        stmt = stmt.where(Script.status == status)
    elif not include_rejected:
        stmt = stmt.where(Script.status != "rejected")
    if date_from:
        stmt = stmt.where(Script.edition_date >= date_from)
    if q:
        stmt = stmt.where(or_(Script.video_title.ilike(f"%{q}%"), Script.news_title.ilike(f"%{q}%")))
    return [ser.script(s) for s in db.scalars(stmt.order_by(Script.edition_date.desc(), Script.position).limit(200))]


@api.get("/scripts/{script_id}")
def get_script(script_id: int, db: Session = Depends(get_db)) -> dict:
    return ser.script(db.get(Script, script_id) or _404(), full=True)


class ScriptEdit(BaseModel):
    package: dict[str, Any]


@api.put("/scripts/{script_id}")
def edit_script(script_id: int, body: ScriptEdit, db: Session = Depends(get_db)) -> dict:
    s = db.get(Script, script_id) or _404()
    try:
        pkg = ScriptPackage.model_validate(body.package)
    except ValidationError as e:
        raise HTTPException(422, e.errors()[:5]) from None
    # o registro de checagem e a origem do conteúdo não podem ser alterados pelo editor
    original = ScriptPackage.model_validate(s.package)
    pkg.fact_check_log, pkg.generator = original.fact_check_log, original.generator
    pkg.generator_notes = list(dict.fromkeys([*original.generator_notes, "Editado manualmente no painel"]))
    s.package = pkg.model_dump(mode="json")
    s.markdown = to_markdown(pkg)
    s.video_title = pkg.identification.video_title
    s.estimated_duration_seconds = pkg.planning.duration_seconds
    s.edited_manually = True
    s.scenes.clear()
    db.flush()
    for n, sc in enumerate(pkg.scenes, start=1):
        s.scenes.append(ScriptScene(order=n, section=sc.section, start_second=sc.start_second, end_second=sc.end_second,
                                    speech=sc.speech, action=sc.action, on_screen=sc.on_screen, overlay_text=sc.overlay_text,
                                    editing_notes=sc.editing_notes, visual_resource=sc.visual_resource))
    db.commit()
    return ser.script(s, full=True)


class StatusIn(BaseModel):
    status: Literal["verified", "recorded", "published"]


@api.post("/scripts/{script_id}/status")
def set_script_status(script_id: int, body: StatusIn, db: Session = Depends(get_db)) -> dict:
    s = db.get(Script, script_id) or _404()
    if s.status == "rejected":
        raise HTTPException(409, "Roteiro reprovado na checagem não pode ser marcado como gravado/publicado")
    s.status = body.status
    db.commit()
    return ser.script(s)


@api.get("/scripts/{script_id}/markdown", response_class=PlainTextResponse)
def script_markdown(script_id: int, db: Session = Depends(get_db)) -> PlainTextResponse:
    s = db.get(Script, script_id) or _404()
    name = f"roteiro-{s.edition_date.isoformat()}-{s.position}.md"
    return PlainTextResponse(s.markdown, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- entregas e execuções
@api.get("/deliveries")
def list_deliveries(db: Session = Depends(get_db), channel: str | None = None) -> list[dict]:
    stmt = select(NotificationDelivery)
    if channel:
        stmt = stmt.where(NotificationDelivery.channel == channel)
    return [ser.delivery(d) for d in db.scalars(stmt.order_by(NotificationDelivery.created_at.desc()).limit(100))]


@api.post("/deliveries/{delivery_id}/resend")
def resend(delivery_id: int, db: Session = Depends(get_db)) -> dict:
    d = db.get(NotificationDelivery, delivery_id) or _404()
    try:
        manual_resend(db, d)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    return ser.delivery(d)


@api.get("/runs")
def list_runs(db: Session = Depends(get_db), kind: str | None = None) -> list[dict]:
    stmt = select(ScheduledRun)
    if kind:
        stmt = stmt.where(ScheduledRun.kind == kind)
    return [ser.run(r) for r in db.scalars(stmt.order_by(ScheduledRun.created_at.desc()).limit(100))]


@api.post("/runs/{kind}", status_code=202)
def request_run(kind: Literal["collect", "edition"], db: Session = Depends(get_db)) -> dict:
    run = request_manual(db, kind)
    return {**ser.run(run), "message": "Execução registrada; o worker a processa em até 1 minuto."}


# ---------------------------------------------------------------- configurações
def integrations_status() -> dict:
    s = get_settings()
    smtp_missing = SmtpTransport(s).configured()
    wa_missing = WhatsAppTransport(s).configured()
    mailbox = s.newsletter_mailbox_provider
    return {
        "email": {"enabled": s.email_enabled, "missing": smtp_missing, "host": s.smtp_host or None},
        "whatsapp": {"enabled": s.whatsapp_enabled, "missing": wa_missing, "mode": s.whatsapp_mode,
                     "template": s.whatsapp_template_name or None},
        "llm": {"provider": s.llm_provider, "api_key_configured": bool(s.llm_api_key.get_secret_value()),
                "base_url": s.llm_base_url or None},
        "newsletter_mailbox": {"provider": mailbox, "address": s.newsletter_mailbox_address or None},
        "timezone": s.timezone,
    }


@api.get("/settings")
def get_settings_view(db: Session = Depends(get_db)) -> dict:
    return {"editable": settings_service.load(db).model_dump(), "categories": settings_service.CATEGORIES,
            "integrations": integrations_status()}


@api.put("/settings")
def put_settings(changes: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    try:
        cfg = settings_service.save(db, changes)
    except ValidationError as e:
        raise HTTPException(422, [{"campo": ".".join(map(str, err["loc"])), "erro": err["msg"]} for err in e.errors()]) from None
    return {"editable": cfg.model_dump(), "integrations": integrations_status()}


@api.post("/integrations/{channel}/test")
def test_channel(channel: Literal["email", "whatsapp"], db: Session = Depends(get_db)) -> dict:
    """Envio de teste REAL, disparado explicitamente pelo administrador no painel."""
    s = get_settings()
    cfg = settings_service.load(db)
    if channel == "email":
        t = SmtpTransport(s)
        if t.configured() or not cfg.email_recipient:
            raise HTTPException(409, f"E-mail não configurado: {t.configured() or ['EMAIL_RECIPIENT']}")
        out = t.send(to=cfg.email_recipient, subject="DevPulse AI — teste de envio",
                     text="Mensagem de teste do DevPulse AI.", html="<p>Mensagem de teste do DevPulse AI.</p>",
                     message_id=f"<test-{local_now().strftime('%Y%m%d%H%M%S')}@devpulse.local>")
    else:
        t = WhatsAppTransport(s)
        problem = t.configured() or ([] if cfg.whatsapp_recipient_opt_in else ["opt-in"]) or (
            [WhatsAppTransport.validate_recipient(cfg.whatsapp_recipient)] if WhatsAppTransport.validate_recipient(cfg.whatsapp_recipient) else [])
        if problem:
            raise HTTPException(409, f"WhatsApp não configurado: {problem}")
        out = t.send(cfg.whatsapp_recipient, params=[local_today().strftime("%d/%m/%Y"), "0", "Mensagem de teste do DevPulse AI."],
                     text="Mensagem de teste do DevPulse AI.")
    return {"ok": out.ok, "error": out.error, "provider_message_id": out.provider_message_id, "provider_status": out.provider_status}


def _404():
    raise HTTPException(404, "Não encontrado")
