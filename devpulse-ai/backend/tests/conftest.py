"""Configuração dos testes.

* Rede real bloqueada por padrão (transportes simulados continuam funcionando).
* Envios reais de e-mail/WhatsApp bloqueados (APP_ENV=test).
* Testes de integração usam TEST_DATABASE_URL (PostgreSQL) e são pulados se o banco não responder.
"""
from __future__ import annotations

import os
import smtplib

import httpx
import pytest

os.environ["APP_ENV"] = "test"
os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://devpulse:devpulse@localhost:5432/devpulse_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["SECRET_KEY"] = "test-secret-key-with-more-than-32-characters!!"
os.environ["ADMIN_PASSWORD"] = "senha-de-teste-123"
os.environ["LLM_PROVIDER"] = "none"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["WHATSAPP_ENABLED"] = "false"
os.environ["FRONTEND_DIST"] = "/nonexistent"
os.environ["LOG_LEVEL"] = "WARNING"
for k in list(os.environ):
    if k.startswith(("SMTP_", "WHATSAPP_ACCESS", "IMAP_", "GMAIL_", "GRAPH_")):
        os.environ.pop(k)

from devpulse.config import reset_settings_cache  # noqa: E402

reset_settings_cache()
EXTERNAL = os.environ.get("RUN_EXTERNAL_TESTS") == "1"


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    if request.node.get_closest_marker("external"):
        return

    def no_network(*args, **kwargs):
        raise RuntimeError("Acesso à rede bloqueado nos testes (use httpx.MockTransport)")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(smtplib.SMTP, "connect", no_network)


def pytest_collection_modifyitems(config, items):
    skip_ext = pytest.mark.skip(reason="defina RUN_EXTERNAL_TESTS=1 para testes com serviços reais")
    for item in items:
        if "external" in item.keywords and not EXTERNAL:
            item.add_marker(skip_ext)
