from datetime import timedelta

import pytest
from sqlalchemy import func, select

from devpulse.delivery_common import SendOutcome
from devpulse.models import FactCheck, NotificationDelivery, ScheduledRun, Script
from devpulse.scheduler import deliveries, recovery
from devpulse.scheduler.jobs import process_run, request_manual
from devpulse.scheduler.pipeline import run_edition
from devpulse.scheduler.runs import claim_run, edition_key, get_or_create_run
from devpulse.settings_service import save
from devpulse.timeutil import local_now, local_today, utcnow

from .conftest import FakeEmail, FakeWhatsApp, add_story, make_source

pytestmark = pytest.mark.integration

TOPICS = [
    ("desenvolvimento", "TypeScript 7.0 released with native compiler"),
    ("ia", "Anthropic launches Claude agents SDK for developers"),
    ("infraestrutura", "Kubernetes 1.36 released with cloud autoscaling"),
    ("seguranca", "Patch for critical CVE-2026-5555 vulnerability exploited"),
    ("mercado", "Developer hiring survey shows new skills in demand"),
    ("desenvolvimento", "Python 3.15 beta adds free-threading by default"),
]


def seed_news(db):
    for i, (cat, title) in enumerate(TOPICS):
        src = make_source(db, f"oficial-{i}", tier=1, category=cat)
        add_story(db, src, title, f"https://oficial-{i}.example.com/news/{i}")


def new_run(db, slot="main"):
    run, _ = get_or_create_run(db, run_key=edition_key(local_today(), slot), kind="edition", slot=slot,
                               edition_date=local_today(), trigger="schedule", scheduled_for=utcnow())
    assert claim_run(db, run)
    return run


def test_edition_respects_limit_and_produces_complete_scripts(db, enable_channels, transports):
    seed_news(db)
    run = new_run(db)
    stats = run_edition(db, run, collect=False, transports=transports, verify_links=False)
    scripts = db.scalars(select(Script).where(Script.status != "rejected")).all()
    assert 1 <= len(scripts) <= 3 and stats["produced"] == len(scripts)
    assert len({s.category for s in scripts}) == len(scripts)  # diversidade de categorias
    for s in scripts:
        assert s.scenes and all(sc.speech for sc in s.scenes)
        assert s.media_assets and any(m.kind == "page_screenshot" for m in s.media_assets)
        central = db.scalars(select(FactCheck).where(FactCheck.script_id == s.id, FactCheck.is_central.is_(True))).all()
        assert central and all(fc.result == "supported" and fc.source_url for fc in central)
        assert s.package["identification"]["primary_sources"][0]["url"].startswith("https://")
    # mesmo roteiro enviado por e-mail e WhatsApp conta uma vez só no limite
    assert len(transports["email"].calls) == 1 and len(transports["whatsapp"].calls) == 1
    assert transports["email"].calls[0]["subject"].startswith("DevPulse AI")


def test_daily_limit_is_shared_across_runs(db, enable_channels, transports):
    seed_news(db)
    run_edition(db, new_run(db, "main"), collect=False, transports=transports, verify_links=False)
    first = db.scalar(select(func.count(Script.id)).where(Script.status != "rejected"))
    manual = request_manual(db, "edition")
    claim_run(db, manual)
    run_edition(db, manual, collect=False, transports=transports, verify_links=False)
    total = db.scalar(select(func.count(Script.id)).where(Script.status != "rejected"))
    assert total <= 3 and total >= first


def test_no_adequate_sources_means_no_fabricated_scripts(db, enable_channels, transports):
    src = make_source(db, "portal", tier=4)
    add_story(db, src, "Rumor: company reportedly planning new phone", "https://portal.example.com/rumor")
    add_story(db, src, "Old news from last month", "https://portal.example.com/old", hours_ago=24 * 30)
    run = new_run(db)
    run_edition(db, run, collect=False, transports=transports, verify_links=False)
    assert db.scalar(select(func.count(Script.id))) == 0
    email = transports["email"].calls[0]
    assert "nenhuma notícia suficientemente verificada" in email["subject"]
    assert transports["whatsapp"].calls[0][1][1] == "0"


def test_channel_failure_is_isolated(db, enable_channels):
    seed_news(db)
    t = {"email": FakeEmail(SendOutcome(ok=False, auth_error=True, error="auth")), "whatsapp": FakeWhatsApp()}
    run_edition(db, new_run(db), collect=False, transports=t, verify_links=False)
    by_channel = {d.channel: d for d in db.scalars(select(NotificationDelivery))}
    assert by_channel["email"].status == "failed_auth"
    assert by_channel["whatsapp"].status == "sent" and by_channel["whatsapp"].provider_message_id == "wamid.fake"


def test_retryable_failure_schedules_backoff(db, enable_channels):
    seed_news(db)
    t = {"email": FakeEmail(SendOutcome(ok=False, retryable=True, error="timeout")), "whatsapp": FakeWhatsApp()}
    run_edition(db, new_run(db), collect=False, transports=t, verify_links=False)
    d = db.scalar(select(NotificationDelivery).where(NotificationDelivery.channel == "email"))
    assert d.status == "retrying" and d.next_attempt_at > utcnow() and d.attempts == 1
    deliveries.dispatch_due(db, t)  # ainda não venceu: não reenvia
    assert len(t["email"].calls) == 1


def test_whatsapp_blocked_without_opt_in(db, enable_channels, monkeypatch, transports):
    save(db, {"whatsapp_recipient_opt_in": False})
    seed_news(db)
    run_edition(db, new_run(db), collect=False, transports=transports, verify_links=False)
    wa = db.scalar(select(NotificationDelivery).where(NotificationDelivery.channel == "whatsapp"))
    assert wa.status == "blocked" and "Opt-in" in wa.last_error
    assert transports["whatsapp"].calls == []


def test_disabled_channels_are_recorded_not_sent(db, transports):
    seed_news(db)
    run_edition(db, new_run(db), collect=False, transports=transports, verify_links=False)
    statuses = {d.channel: d.status for d in db.scalars(select(NotificationDelivery))}
    assert statuses == {"email": "disabled", "whatsapp": "disabled"}
    assert transports["email"].calls == []


def test_rerun_after_restart_does_not_duplicate(db, enable_channels, transports):
    seed_news(db)
    run = new_run(db)
    run_edition(db, run, collect=False, transports=transports, verify_links=False)
    n_scripts = db.scalar(select(func.count(Script.id)))
    # simula reinício: a mesma execução volta a ser processada
    run.status = "pending"
    db.commit()
    assert claim_run(db, run)
    run_edition(db, run, collect=False, transports=transports, verify_links=False)
    assert db.scalar(select(func.count(Script.id))) == n_scripts
    assert len(transports["email"].calls) == 1 and len(transports["whatsapp"].calls) == 1
    # e criar de novo a execução do dia não cria outra
    _, created = get_or_create_run(db, run_key=edition_key(local_today(), "main"), kind="edition", slot="main",
                                   edition_date=local_today(), trigger="recovery", scheduled_for=utcnow())
    assert created is False


def test_stale_running_run_is_resumed(db, enable_channels, transports, monkeypatch):
    seed_news(db)
    run = new_run(db)
    run.heartbeat_at = utcnow() - timedelta(hours=1)
    db.commit()
    assert recovery.reset_stale_running(db) == 1
    db.refresh(run)
    assert run.status == "pending"
    monkeypatch.setattr("devpulse.scheduler.jobs.run_edition",
                        lambda s, r: run_edition(s, r, collect=False, transports=transports, verify_links=False))
    process_run(db, run)
    db.refresh(run)
    assert run.status == "completed" and run.attempts == 2


def test_interrupted_send_goes_to_review_not_resent(db, enable_channels, transports):
    seed_news(db)
    run = new_run(db)
    run_edition(db, run, collect=False, deliver=False, verify_links=False)
    deliveries.ensure_deliveries(db, run)
    d = db.scalar(select(NotificationDelivery).where(NotificationDelivery.channel == "whatsapp"))
    d.status = "sending"
    d.updated_at = utcnow() - timedelta(hours=1)
    db.commit()
    db.execute(NotificationDelivery.__table__.update().where(NotificationDelivery.id == d.id).values(updated_at=utcnow() - timedelta(hours=1)))
    db.commit()
    assert deliveries.recover_stuck(db) == 1
    deliveries.dispatch_due(db, transports)
    db.refresh(d)
    assert d.status == "needs_review" and transports["whatsapp"].calls == []


def test_recovery_window(db):
    save(db, {"edition_main_time": "08:00", "edition_catchup_until": "14:00", "edition_secondary_time": ""})
    day = local_now().replace(hour=9, minute=0, second=0, microsecond=0)
    created = recovery.ensure_today_editions(db, now=day)
    assert [r.status for r in created] == ["pending"] and created[0].trigger == "recovery"
    assert recovery.ensure_today_editions(db, now=day) == []  # idempotente

    db.execute(ScheduledRun.__table__.delete())
    db.commit()
    late = local_now().replace(hour=18, minute=0, second=0, microsecond=0)
    created = recovery.ensure_today_editions(db, now=late)
    assert created[0].status == "skipped"  # não envia edição atrasada

    db.execute(ScheduledRun.__table__.delete())
    db.commit()
    early = local_now().replace(hour=7, minute=0, second=0, microsecond=0)
    assert recovery.ensure_today_editions(db, now=early) == []


def test_old_pending_editions_expire(db):
    yesterday = local_today() - timedelta(days=1)
    run, _ = get_or_create_run(db, run_key=edition_key(yesterday, "main"), kind="edition", slot="main",
                               edition_date=yesterday, trigger="schedule", scheduled_for=utcnow())
    assert recovery.expire_old_pending(db, local_today()) == 1
    db.refresh(run)
    assert run.status == "skipped"


def test_run_checkpoints_are_persisted(db, transports):
    """Regressão: as etapas concluídas precisam estar no banco para a retomada após reinício."""
    from devpulse.db import session_factory

    seed_news(db)
    run = new_run(db)
    run_edition(db, run, collect=False, transports=transports, verify_links=False)
    fresh = session_factory()()
    try:
        stats = fresh.get(ScheduledRun, run.id).stats
        assert stats["generated"] is True and stats["produced"] >= 1 and "delivery" in stats
    finally:
        fresh.close()
