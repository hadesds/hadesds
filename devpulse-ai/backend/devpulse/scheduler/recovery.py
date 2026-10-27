"""Recuperação controlada após reinício ou computador desligado no horário.

* Execuções 'running' sem sinal de vida voltam para 'pending' e são retomadas
  (as etapas já concluídas não se repetem).
* A edição do dia que não rodou é executada se ainda estiver dentro da janela
  de recuperação (EDITION_CATCHUP_UNTIL); fora dela, é registrada como
  'skipped' e nunca enviada atrasada.
* Edições de dias anteriores nunca são disparadas.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from devpulse.models import ScheduledRun
from devpulse.scheduler.runs import edition_key, get_or_create_run
from devpulse.settings_service import load as load_settings
from devpulse.timeutil import local_dt, local_now, parse_hhmm, utcnow

log = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=15)


def reset_stale_running(session: Session) -> int:
    limit = utcnow() - STALE_AFTER
    stale = session.scalars(
        select(ScheduledRun).where(ScheduledRun.status == "running", ScheduledRun.heartbeat_at < limit)
    ).all()
    for run in stale:
        log.warning("Retomando execução interrompida %s (etapa %s)", run.run_key, run.step)
        run.status = "pending"
        run.next_attempt_at = None
    session.commit()
    return len(stale)


def expire_old_pending(session: Session, today: date) -> int:
    old = session.scalars(
        select(ScheduledRun).where(ScheduledRun.status == "pending", ScheduledRun.kind == "edition", ScheduledRun.edition_date < today)
    ).all()
    for run in old:
        run.status = "skipped"
        run.error = "Edição de dia anterior não executada; não é enviada com atraso"
        run.finished_at = utcnow()
    session.commit()
    return len(old)


def ensure_today_editions(session: Session, now: datetime | None = None) -> list[ScheduledRun]:
    """Cria (idempotente) as execuções do dia cujo horário já passou."""
    cfg = load_settings(session)
    now = now or local_now()
    today = now.date()
    catchup = parse_hhmm(cfg.edition_catchup_until)
    created = []
    for slot, hhmm in (("main", cfg.edition_main_time), ("secondary", cfg.edition_secondary_time)):
        at = parse_hhmm(hhmm)
        if at is None:
            continue
        scheduled = local_dt(today, at)
        if now < scheduled:
            continue
        deadline = local_dt(today, catchup) if slot == "main" and catchup else scheduled + timedelta(hours=2)
        deadline = max(deadline, scheduled + timedelta(minutes=30))
        late = now - scheduled > timedelta(minutes=10)
        if now <= deadline:
            run, is_new = get_or_create_run(
                session, run_key=edition_key(today, slot), kind="edition", slot=slot, edition_date=today,
                trigger="recovery" if late else "schedule", scheduled_for=scheduled,
            )
        else:
            run, is_new = get_or_create_run(
                session, run_key=edition_key(today, slot), kind="edition", slot=slot, edition_date=today,
                trigger="recovery", scheduled_for=scheduled, status="skipped",
                error=f"Sistema indisponível no horário; janela de recuperação encerrada às {deadline.strftime('%H:%M')}",
            )
        if is_new:
            log.info("Execução %s criada (%s)", run.run_key, run.status)
            created.append(run)
    return created


def due_pending_runs(session: Session) -> list[ScheduledRun]:
    now = utcnow()
    return list(session.scalars(
        select(ScheduledRun)
        .where(ScheduledRun.status == "pending")
        .where((ScheduledRun.next_attempt_at.is_(None)) | (ScheduledRun.next_attempt_at <= now))
        .order_by(ScheduledRun.created_at)
    ))
