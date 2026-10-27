"""Processo do agendador. Deve existir apenas um (garantido por advisory lock)."""
from __future__ import annotations

import logging
import signal
import time
from datetime import datetime

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from devpulse.config import get_settings
from devpulse.db import get_engine, session_scope
from devpulse.observability.logging import configure_logging
from devpulse.settings_service import load as load_settings
from devpulse.settings_service import version as settings_version
from devpulse.timeutil import parse_hhmm, tz

log = logging.getLogger("devpulse.worker")
LOCK_ID = 727_001


def _schedule_jobs(sched: BackgroundScheduler, first: bool = False) -> None:
    with session_scope() as session:
        cfg = load_settings(session)
    common = {"replace_existing": True, "coalesce": True, "max_instances": 1, "misfire_grace_time": 600}
    # primeira rodada imediata = recuperação ao iniciar (executa no agendador, não na thread principal)
    # (next_run_time=None pausaria o job; por isso só é passado na primeira vez)
    extra = {"next_run_time": datetime.now(tz())} if first else {}
    sched.add_job("devpulse.scheduler.jobs:tick", IntervalTrigger(seconds=60), id="tick", **common, **extra)
    sched.add_job("devpulse.scheduler.jobs:collect_job", IntervalTrigger(minutes=cfg.collect_interval_minutes),
                  id="collect", **common)
    for slot, hhmm in (("main", cfg.edition_main_time), ("secondary", cfg.edition_secondary_time)):
        at = parse_hhmm(hhmm)
        job_id = f"edition_{slot}"
        if at is None:
            if sched.get_job(job_id):
                sched.remove_job(job_id)
            continue
        sched.add_job("devpulse.scheduler.jobs:edition_job", CronTrigger(hour=at.hour, minute=at.minute, timezone=tz()),
                      id=job_id, args=[slot], **common)
    log.info("Agenda: edição principal %s, secundária %s, coleta a cada %s min (%s)", cfg.edition_main_time,
             cfg.edition_secondary_time or "desativada", cfg.collect_interval_minutes, get_settings().timezone)


def main() -> None:
    configure_logging()
    engine = get_engine()
    lock_conn = engine.connect()
    if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID}).scalar():
        log.error("Outro worker já está em execução; encerrando para evitar duplicidade")
        return
    sched = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")}, timezone=tz()
    )
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    _schedule_jobs(sched, first=True)
    sched.start()
    log.info("Worker iniciado; recuperação inicial agendada para agora")
    with session_scope() as session:
        current = settings_version(session)
    while not stop["flag"]:
        time.sleep(5)
        with session_scope() as session:
            v = settings_version(session)
        if v != current:
            log.info("Configurações alteradas no painel; reprogramando agenda")
            _schedule_jobs(sched)
            current = v
    log.info("Encerrando worker")
    sched.shutdown(wait=True)
    lock_conn.close()


if __name__ == "__main__":
    main()
