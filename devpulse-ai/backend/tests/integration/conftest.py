from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from devpulse.config import get_settings, reset_settings_cache
from devpulse.delivery_common import SendOutcome
from devpulse.models import Source
from devpulse.news_ingestion.service import persist_item
from devpulse.source_connectors.base import RawItem
from devpulse.timeutil import utcnow

BACKEND = Path(__file__).resolve().parents[2]
TABLES = ("llm_usage", "application_settings", "notification_deliveries", "media_assets", "fact_checks", "script_scenes",
          "scripts", "editorial_scores", "source_references", "news_items", "news_clusters", "source_runs", "scheduled_runs", "sources")


@pytest.fixture(scope="session")
def migrated():
    url = os.environ["TEST_DATABASE_URL"]
    try:
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    except Exception as e:  # pragma: no cover
        pytest.skip(f"PostgreSQL de teste indisponível: {e}")
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(migrated, monkeypatch):
    from devpulse import db as dbmod

    reset_settings_cache()
    dbmod.reset_engine()
    with migrated.begin() as c:
        c.execute(text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
    session = dbmod.session_factory()()
    yield session
    session.close()
    dbmod.reset_engine()


@pytest.fixture
def enable_channels(monkeypatch):
    """Habilita os dois canais com credenciais FICTÍCIAS; os envios usam transportes simulados."""
    env = {
        "EMAIL_ENABLED": "true", "EMAIL_RECIPIENT": "dono@example.com", "EMAIL_FROM": "bot@example.com",
        "SMTP_HOST": "smtp.example.com", "SMTP_USERNAME": "bot", "SMTP_PASSWORD": "x" * 12,
        "WHATSAPP_ENABLED": "true", "WHATSAPP_ACCESS_TOKEN": "EAA" + "x" * 30, "WHATSAPP_PHONE_NUMBER_ID": "123",
        "WHATSAPP_TEMPLATE_NAME": "devpulse_edicao", "WHATSAPP_RECIPIENT": "+5598999990000", "WHATSAPP_RECIPIENT_OPT_IN": "true",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    reset_settings_cache()
    yield get_settings()
    reset_settings_cache()


class FakeEmail:
    def __init__(self, outcome: SendOutcome | None = None):
        self.calls: list[dict] = []
        self.outcome = outcome or SendOutcome(ok=True, provider_message_id="<fake@x>", provider_status="accepted_by_smtp_server")

    def send(self, **kw):
        self.calls.append(kw)
        return self.outcome


class FakeWhatsApp:
    def __init__(self, outcome: SendOutcome | None = None):
        self.calls: list[tuple] = []
        self.outcome = outcome or SendOutcome(ok=True, provider_message_id="wamid.fake", provider_status="accepted")

    def send(self, to, *, params, text):
        self.calls.append((to, params, text))
        return self.outcome


@pytest.fixture
def transports():
    return {"email": FakeEmail(), "whatsapp": FakeWhatsApp()}


ARTICLE = (
    "Today we are announcing {name} {ver}. This release introduces a new command line interface for developers "
    "and improves performance of the API by 25% in our benchmarks. The update is available now for all users. "
    "Developers can install it with the package manager and read the documentation to migrate existing projects. "
    "The team also published a migration guide and deprecated two legacy endpoints that will be removed next year. "
) * 3


def make_source(session, slug, tier=1, category=None, ctype="rss", url=None):
    s = Source(slug=slug, name=slug, connector_type=ctype, url=url or f"https://{slug}.example.com/feed",
               priority_tier=tier, category=category, config={})
    session.add(s)
    session.commit()
    return s


def add_story(session, source, title, url, hours_ago=2, content=None, **kw):
    raw = RawItem(external_id=url, url=url, title=title, summary=title + ". " + (content or "")[:200],
                  content=content if content is not None else ARTICLE.format(name=title.split()[0], ver="2.0"),
                  content_access="full", published_at=utcnow() - timedelta(hours=hours_ago), language="en", **kw)
    status, item = persist_item(session, source, raw)
    session.commit()
    return status, item
