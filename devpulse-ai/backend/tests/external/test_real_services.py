"""Verificações com serviços REAIS. Só rodam com RUN_EXTERNAL_TESTS=1.

Os testes de envio exigem, além disso, ALLOW_REAL_SENDS_IN_TESTS=true e as
credenciais no ambiente — é a autorização explícita para enviar mensagens reais.
"""
from __future__ import annotations

import os

import pytest

from devpulse import http as http_mod
from devpulse.config import get_settings, reset_settings_cache
from devpulse.source_connectors.base import ConnectorContext
from devpulse.source_connectors.registry import get_connector

pytestmark = pytest.mark.external


def test_real_rss_feed_has_urls_and_dates():
    url = os.environ.get("EXTERNAL_FEED_URL", "https://nodejs.org/en/feed/blog.xml")
    with http_mod.client() as c:
        res = get_connector("rss").fetch(ConnectorContext(http=c, source_config={}, source_url=url, state={}, since=None))
    assert res.items, "feed sem itens"
    assert all(i.url.startswith("http") for i in res.items)
    assert any(i.published_at for i in res.items)


def _require_sends():
    reset_settings_cache()
    if os.environ.get("ALLOW_REAL_SENDS_IN_TESTS", "").lower() != "true":
        pytest.skip("defina ALLOW_REAL_SENDS_IN_TESTS=true para autorizar envios reais")
    return get_settings()


def test_real_email_send():
    from devpulse.email_delivery.smtp import SmtpTransport

    s = _require_sends()
    t = SmtpTransport(s)
    if t.configured() or not s.email_recipient:
        pytest.skip(f"SMTP incompleto: {t.configured() or ['EMAIL_RECIPIENT']}")
    out = t.send(to=s.email_recipient, subject="DevPulse AI — teste externo", text="Teste externo.",
                 html="<p>Teste externo.</p>", message_id="<external-test@devpulse.local>")
    assert out.ok, out.error


def test_real_whatsapp_send():
    from devpulse.whatsapp_delivery.cloud_api import WhatsAppTransport

    s = _require_sends()
    t = WhatsAppTransport(s)
    if t.configured() or not s.whatsapp_recipient or not s.whatsapp_recipient_opt_in:
        pytest.skip("WhatsApp Business não configurado ou sem opt-in")
    out = t.send(s.whatsapp_recipient, params=["teste", "0", "Teste externo do DevPulse AI."], text="Teste externo do DevPulse AI.")
    assert out.ok, out.error
