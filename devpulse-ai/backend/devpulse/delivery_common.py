"""Tipos compartilhados pelos canais de entrega."""
from __future__ import annotations

from dataclasses import dataclass

from devpulse.config import get_settings


class RealSendBlocked(RuntimeError):
    """Impede envios reais durante os testes automatizados."""


def guard_real_send() -> None:
    s = get_settings()
    if s.app_env == "test" and not s.allow_real_sends_in_tests:
        raise RealSendBlocked("Envio real bloqueado em APP_ENV=test (defina ALLOW_REAL_SENDS_IN_TESTS=true)")


@dataclass
class SendOutcome:
    ok: bool
    retryable: bool = False
    auth_error: bool = False
    provider_message_id: str | None = None
    provider_status: str | None = None
    error: str | None = None
    details: dict | None = None
