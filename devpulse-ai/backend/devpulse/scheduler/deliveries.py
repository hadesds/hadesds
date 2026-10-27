"""Entregas por canal, com idempotência, retentativas e estados independentes."""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from devpulse.config import get_settings
from devpulse.content_extraction.text import truncate
from devpulse.delivery_common import SendOutcome
from devpulse.email_delivery.render import render_edition
from devpulse.email_delivery.smtp import SmtpTransport
from devpulse.models import NotificationDelivery, ScheduledRun, Script
from devpulse.observability.logging import mask_email, mask_phone
from devpulse.script_generation.schema import ScriptPackage
from devpulse.settings_service import load as load_settings
from devpulse.timeutil import local_today, utcnow
from devpulse.whatsapp_delivery.cloud_api import WhatsAppTransport

log = logging.getLogger(__name__)
BACKOFF_MINUTES = [2, 10, 30, 90, 240]
STUCK_AFTER = timedelta(minutes=10)


def _key(run: ScheduledRun, channel: str, recipient: str) -> str:
    h = hashlib.sha256(recipient.lower().encode()).hexdigest()[:12]
    return f"{run.run_key}:{channel}:{h}"


def edition_scripts(session: Session, run: ScheduledRun) -> list[Script]:
    return list(session.scalars(
        select(Script).where(Script.scheduled_run_id == run.id, Script.status != "rejected").order_by(Script.position)
    ))


def ensure_deliveries(session: Session, run: ScheduledRun) -> list[NotificationDelivery]:
    s = get_settings()
    cfg = load_settings(session)
    out = []
    plans = [
        ("email", cfg.email_recipient, s.email_enabled, SmtpTransport(s).configured(), None),
        ("whatsapp", cfg.whatsapp_recipient, s.whatsapp_enabled, WhatsAppTransport(s).configured(),
         WhatsAppTransport.validate_recipient(cfg.whatsapp_recipient) if cfg.whatsapp_recipient else None),
    ]
    for channel, recipient, enabled, missing, invalid in plans:
        status, error = "pending", None
        if not enabled:
            status, error = "disabled", f"Canal {channel} desativado na configuração"
        elif not recipient:
            status, error = "blocked", "Destinatário não configurado"
        elif missing:
            status, error = "blocked", "Credenciais ausentes: " + ", ".join(missing)
        elif invalid:
            status, error = "blocked", invalid
        elif channel == "whatsapp" and not cfg.whatsapp_recipient_opt_in:
            status, error = "blocked", "Opt-in do destinatário não confirmado (WHATSAPP_RECIPIENT_OPT_IN)"
        key = _key(run, channel, recipient or "-")
        existing = session.scalar(select(NotificationDelivery).where(NotificationDelivery.idempotency_key == key))
        if existing:
            out.append(existing)
            continue
        d = NotificationDelivery(
            scheduled_run_id=run.id, edition_date=run.edition_date, channel=channel, recipient=recipient or "-",
            idempotency_key=key, status=status, last_error=error, next_attempt_at=utcnow() if status == "pending" else None,
            provider="smtp" if channel == "email" else "whatsapp_cloud_api",
        )
        session.add(d)
        out.append(d)
    session.commit()
    return out


def _summary(packages: list[ScriptPackage]) -> str:
    if not packages:
        return "Nenhuma notícia foi aprovada nos critérios de atualidade, relevância e verificação."
    cats = sorted({p.identification.category for p in packages})
    return f"{len(packages)} roteiro(s) prontos para gravar, cobrindo: {', '.join(cats)}."


def _empty_reasons(run: ScheduledRun) -> list[str]:
    return list((run.stats or {}).get("top_rejections", []))


def build_whatsapp(run: ScheduledRun, packages: list[ScriptPackage], label: str, dashboard: str) -> tuple[list[str], str]:
    items = []
    lines = [f"*DevPulse AI — {label}*", f"{len(packages)} roteiro(s) disponível(is).", ""]
    for i, p in enumerate(packages, start=1):
        src = p.identification.primary_sources[0].url if p.identification.primary_sources else ""
        items.append(f"{i}) {p.identification.video_title} ({p.planning.duration_seconds}s) fonte: {src}")
        lines += [f"*{i}. {p.identification.video_title}*", truncate(p.planning.key_message, 180),
                  f"⏱ {p.planning.duration_seconds}s · {p.identification.category}", f"Fonte: {src}", ""]
    if not packages:
        items.append("Nenhuma notícia suficientemente verificada hoje.")
        lines.append("Nenhuma notícia suficientemente verificada hoje.")
    lines.append("Roteiros completos enviados por e-mail e no painel local.")
    params = [label, str(len(packages)), " ".join(items)]
    return params, "\n".join(lines)


def _send(session: Session, d: NotificationDelivery, run: ScheduledRun, transports: dict) -> SendOutcome:
    packages = [ScriptPackage.model_validate(s.package) for s in edition_scripts(session, run)]
    label = run.edition_date.strftime("%d/%m/%Y") + ("" if run.slot == "main" else f" ({run.slot})")
    dashboard = get_settings().dashboard_public_url
    if d.channel == "email":
        subject, html, text = render_edition(edition_label=label, packages=packages, summary=_summary(packages),
                                             dashboard_url=dashboard, empty_reasons=_empty_reasons(run))
        d.payload_summary = {"subject": subject, "scripts": len(packages), "html_bytes": len(html)}
        domain = (get_settings().email_from.split("@")[-1] or "devpulse.local").strip(">")
        message_id = f"<{hashlib.sha256(d.idempotency_key.encode()).hexdigest()[:32]}@{domain}>"
        return transports["email"].send(to=d.recipient, subject=subject, html=html, text=text, message_id=message_id)
    params, text = build_whatsapp(run, packages, label, dashboard)
    d.payload_summary = {"scripts": len(packages), "mode": get_settings().whatsapp_mode}
    return transports["whatsapp"].send(d.recipient, params=params, text=text)


def default_transports() -> dict:
    s = get_settings()
    return {"email": SmtpTransport(s), "whatsapp": WhatsAppTransport(s)}


def dispatch_due(session: Session, transports: dict | None = None) -> dict:
    transports = transports or default_transports()
    stats = {"sent": 0, "failed": 0, "retrying": 0}
    now = utcnow()
    due = session.scalars(
        select(NotificationDelivery).where(
            NotificationDelivery.status.in_(["pending", "retrying"]),
            (NotificationDelivery.next_attempt_at.is_(None)) | (NotificationDelivery.next_attempt_at <= now),
        )
    ).all()
    for d in due:
        if d.edition_date < local_today():
            d.status, d.last_error = "failed", "Edição expirada: não reenviada em dia posterior"
            session.commit()
            continue
        claimed = session.execute(
            update(NotificationDelivery)
            .where(NotificationDelivery.id == d.id, NotificationDelivery.status.in_(["pending", "retrying"]))
            .values(status="sending", attempts=NotificationDelivery.attempts + 1, updated_at=utcnow())
        ).rowcount
        session.commit()
        if not claimed:
            continue
        session.refresh(d)
        run = session.get(ScheduledRun, d.scheduled_run_id)
        try:
            outcome = _send(session, d, run, transports)
        except Exception as e:  # erro inesperado: não sabemos se saiu; não reenviar automaticamente
            log.exception("Erro inesperado no envio %s", d.channel)
            outcome = SendOutcome(ok=False, error=f"Erro inesperado: {type(e).__name__}")
            d.status = "needs_review"
        masked = mask_email(d.recipient) if d.channel == "email" else mask_phone(d.recipient)
        entry = {"at": utcnow().isoformat(), "attempt": d.attempts, "ok": outcome.ok, "error": outcome.error,
                 "provider_message_id": outcome.provider_message_id, "details": outcome.details}
        d.attempt_log = [*(d.attempt_log or []), entry][-20:]
        if outcome.ok:
            d.status, d.sent_at, d.last_error = "sent", utcnow(), None
            d.provider_message_id, d.provider_status = outcome.provider_message_id, outcome.provider_status
            stats["sent"] += 1
            log.info("Entrega %s aceita pelo provedor para %s", d.channel, masked, extra={"channel": d.channel})
        elif d.status == "needs_review":
            d.last_error = outcome.error
        elif outcome.auth_error:
            d.status, d.last_error = "failed_auth", outcome.error
            stats["failed"] += 1
        elif outcome.retryable and d.attempts < d.max_attempts:
            d.status, d.last_error = "retrying", outcome.error
            d.next_attempt_at = utcnow() + timedelta(minutes=BACKOFF_MINUTES[min(d.attempts, len(BACKOFF_MINUTES)) - 1])
            stats["retrying"] += 1
        else:
            d.status, d.last_error = "failed", outcome.error
            stats["failed"] += 1
        if not outcome.ok:
            log.warning("Entrega %s falhou (%s): %s", d.channel, d.status, outcome.error, extra={"channel": d.channel})
        session.commit()
    return stats


def recover_stuck(session: Session) -> int:
    """Envios interrompidos no meio (queda/reinício) vão para revisão manual, nunca reenvio cego."""
    limit = utcnow() - STUCK_AFTER
    stuck = session.scalars(
        select(NotificationDelivery).where(NotificationDelivery.status == "sending", NotificationDelivery.updated_at < limit)
    ).all()
    for d in stuck:
        d.status = "needs_review"
        d.last_error = "Envio interrompido; o provedor pode ou não ter recebido. Confirme antes de reenviar pelo painel."
    session.commit()
    return len(stuck)


def manual_resend(session: Session, d: NotificationDelivery) -> None:
    if d.status not in ("failed", "failed_auth", "needs_review", "blocked"):
        raise ValueError("Somente entregas com falha, bloqueadas ou em revisão podem ser reenviadas")
    d.status, d.next_attempt_at, d.max_attempts = "pending", utcnow(), d.attempts + 3
    session.commit()
