"""Criação idempotente de execuções (ScheduledRun)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from devpulse.models import ScheduledRun
from devpulse.timeutil import utcnow

RUN_BACKOFF_MINUTES = [5, 15, 45]


def edition_key(day: date, slot: str) -> str:
    return f"edition:{day.isoformat()}:{slot}"


def get_or_create_run(session: Session, *, run_key: str, kind: str, slot: str | None, edition_date: date | None,
                      trigger: str, scheduled_for: datetime | None, status: str = "pending", error: str | None = None) -> tuple[ScheduledRun, bool]:
    stmt = (
        insert(ScheduledRun)
        .values(run_key=run_key, kind=kind, slot=slot, edition_date=edition_date, trigger=trigger,
                scheduled_for=scheduled_for, status=status, error=error, stats={}, attempts=0,
                id=str(uuid.uuid4()))
        .on_conflict_do_nothing(index_elements=["run_key"])
        .returning(ScheduledRun.id)
    )
    created_id = session.execute(stmt).scalar()
    session.commit()
    run = session.scalar(select(ScheduledRun).where(ScheduledRun.run_key == run_key))
    assert run is not None
    return run, created_id is not None


def claim_run(session: Session, run: ScheduledRun) -> bool:
    """Marca como 'running' apenas se ainda estiver pendente (evita execução dupla)."""
    now = utcnow()
    res = session.execute(
        ScheduledRun.__table__.update()
        .where(ScheduledRun.id == run.id, ScheduledRun.status == "pending")
        .values(status="running", started_at=now, heartbeat_at=now, attempts=ScheduledRun.attempts + 1)
    )
    session.commit()
    session.refresh(run)
    return res.rowcount == 1


def heartbeat(session: Session, run: ScheduledRun, step: str) -> None:
    run.step = step
    run.heartbeat_at = utcnow()
    session.commit()


def finish(session: Session, run: ScheduledRun, status: str, error: str | None = None) -> None:
    run.status = status
    run.error = error
    if status == "completed":
        run.step = "done"
    run.finished_at = utcnow()
    session.commit()


def fail_with_retry(session: Session, run: ScheduledRun, error: str) -> None:
    if run.attempts <= len(RUN_BACKOFF_MINUTES):
        run.status = "pending"
        run.next_attempt_at = utcnow() + timedelta(minutes=RUN_BACKOFF_MINUTES[min(run.attempts, len(RUN_BACKOFF_MINUTES)) - 1])
        run.error = f"Tentativa {run.attempts} falhou: {error}"[:2000]
    else:
        run.status = "failed"
        run.error = error[:2000]
        run.finished_at = utcnow()
    session.commit()
