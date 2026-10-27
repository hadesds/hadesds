"""WhatsApp Business Platform (Cloud API oficial da Meta).

Mensagens iniciadas pela empresa fora da janela de atendimento de 24h exigem
um template aprovado. ``WHATSAPP_MODE=template`` é o padrão.
A resposta da API confirma apenas a ACEITAÇÃO da mensagem; o status de entrega
chega por webhook, que exige uma URL pública e não é habilitado nesta versão local.
"""
from __future__ import annotations

import re

import httpx

from devpulse.config import Settings
from devpulse.delivery_common import SendOutcome, guard_real_send

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
AUTH_CODES = {190, 102, 10, 200, 3}
RETRY_CODES = {4, 80007, 130429, 131000, 131016, 131048, 131056, 133004}


def sanitize_param(text: str, limit: int = 900) -> str:
    """Parâmetros de template não aceitam quebras de linha, tabs ou 4+ espaços seguidos."""
    text = re.sub(r"[\r\n\t]+", " | ", text or "")
    text = re.sub(r" {4,}", "   ", text).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text


class WhatsAppTransport:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.s = settings
        self.http = http

    def configured(self) -> list[str]:
        missing = []
        if not self.s.whatsapp_access_token.get_secret_value():
            missing.append("WHATSAPP_ACCESS_TOKEN")
        if not self.s.whatsapp_phone_number_id:
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
        if self.s.whatsapp_mode == "template" and not self.s.whatsapp_template_name:
            missing.append("WHATSAPP_TEMPLATE_NAME")
        return missing

    @staticmethod
    def validate_recipient(number: str) -> str | None:
        return None if E164.match(number or "") else "Número deve estar no formato E.164 (ex.: +5598999999999)"

    def build_body(self, to: str, *, params: list[str], text: str) -> dict:
        base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to.lstrip("+")}
        if self.s.whatsapp_mode == "text":
            return base | {"type": "text", "text": {"preview_url": False, "body": text[:4096]}}
        return base | {
            "type": "template",
            "template": {
                "name": self.s.whatsapp_template_name,
                "language": {"code": self.s.whatsapp_template_language},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": sanitize_param(p)} for p in params]}],
            },
        }

    def send(self, to: str, *, params: list[str], text: str) -> SendOutcome:
        guard_real_send()
        url = f"https://graph.facebook.com/{self.s.whatsapp_api_version}/{self.s.whatsapp_phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.s.whatsapp_access_token.get_secret_value()}"}
        client = self.http or httpx.Client(timeout=30)
        try:
            r = client.post(url, json=self.build_body(to, params=params, text=text), headers=headers)
        except httpx.HTTPError as e:
            return SendOutcome(ok=False, retryable=True, error=f"Falha de rede: {type(e).__name__}")
        finally:
            if self.http is None:
                client.close()
        return self.interpret(r)

    @staticmethod
    def interpret(r: httpx.Response) -> SendOutcome:
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code < 300 and data.get("messages"):
            m = data["messages"][0]
            return SendOutcome(ok=True, provider_message_id=m.get("id"), provider_status=m.get("message_status", "accepted"))
        err = data.get("error", {}) if isinstance(data, dict) else {}
        code = err.get("code")
        msg = f"WhatsApp API HTTP {r.status_code} código {code}: {err.get('message', '')[:200]}"
        details = {"code": code, "subcode": err.get("error_subcode"), "fbtrace_id": err.get("fbtrace_id")}
        if r.status_code == 401 or code in AUTH_CODES:
            return SendOutcome(ok=False, auth_error=True, error=msg, details=details)
        if code == 131047:
            return SendOutcome(ok=False, error=msg + " — fora da janela de 24h; use WHATSAPP_MODE=template", details=details)
        if r.status_code >= 500 or r.status_code == 429 or code in RETRY_CODES:
            return SendOutcome(ok=False, retryable=True, error=msg, details=details)
        return SendOutcome(ok=False, error=msg, details=details)
