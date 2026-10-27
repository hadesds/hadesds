"""Funções executadas pelo APScheduler (referenciadas por caminho, persistíveis)."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from devpulse.db import session_scope
from devpulse.models import ScheduledRun
from devpulse.scheduler import deliveries, recovery
from devpulse.scheduler.pipeline import run_collection, run_edition
from devpulse.scheduler.runs import claim_run, fail_with_retry, finish, get_or_create_run
from devpulse.timeutil import local_today, utcnow

log = logging.getLogger(__name__)


def process_run(session, run: ScheduledRun) -> None:
    if not claim_run(session, run):
        return
    log.info("Iniciando %s", run.run_key, extra={"run_id": run.id})
    try:
        if run.kind == "edition":
            run_edition(session, run)
        else:
            run_collection(session, run, force=run.trigger == "manual")
        finish(session, run, "completed")
        log.info("Concluída %s", run.run_key, extra={"run_id": run.id})
    except Exception as e:
        session.rollback()
        log.exception("Execução %s falhou", run.run_key, extra={"run_id": run.id})
        fail_with_retry(session, run, f"{type(e).__name__}: {e}")


def tick() -> None:
    """A cada minuto: recuperação, execuções pendentes e entregas devidas."""
    with session_scope() as session:
        recovery.reset_stale_running(session)
        recovery.expire_old_pending(session, local_today())
        recovery.ensure_today_editions(session)
        deliveries.recover_stuck(session)
        for run in recovery.due_pending_runs(session):
            process_run(session, run)
        deliveries.dispatch_due(session)


def edition_job(slot: str) -> None:
    # O horário chegou: a criação é idempotente; o tick processa logo em seguida.
    with session_scope() as session:
        recovery.ensure_today_editions(session)
        for run in recovery.due_pending_runs(session):
            if run.kind == "edition":
                process_run(session, run)


def collect_job() -> None:
    with session_scope() as session:
        now = utcnow()
        key = f"collect:{now.strftime('%Y-%m-%dT%H:%M')}"
        run, created = get_or_create_run(session, run_key=key, kind="collect", slot=None, edition_date=local_today(),
                                         trigger="schedule", scheduled_for=now)
        if created:
            process_run(session, run)


def request_manual(session, kind: str) -> ScheduledRun:
    key = f"{kind}:{local_today().isoformat()}:manual:{uuid.uuid4().hex[:8]}"
    run, _ = get_or_create_run(session, run_key=key, kind=kind, slot="manual", edition_date=local_today(),
                               trigger="manual", scheduled_for=utcnow() + timedelta(seconds=1))
    return run
