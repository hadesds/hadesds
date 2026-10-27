"""Provedores de modelo de linguagem com limites diários de consumo.

* ``anthropic`` — SDK oficial da Anthropic, saída estruturada via JSON Schema.
* ``openai_compatible`` — qualquer API compatível com ``/chat/completions``
  (OpenAI, OpenRouter, Ollama local etc.).
* ``none`` — sem IA; o sistema usa o gerador extrativo.

O limite de chamadas/tokens por dia é aplicado pelo próprio DevPulse (efetivo).
O custo em dólares é apenas estimado a partir dos preços configurados.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from devpulse.config import get_settings
from devpulse.models import LlmUsage
from devpulse.settings_service import EditableSettings
from devpulse.timeutil import local_today

log = logging.getLogger(__name__)
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


class LlmUnavailable(Exception):
    pass


class LlmBudgetExceeded(LlmUnavailable):
    pass


class LlmError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class LlmResult:
    data: dict
    input_tokens: int
    output_tokens: int
    model: str
    request_id: str | None


class LlmClient:
    provider = "none"

    def __init__(self, session: Session, cfg: EditableSettings):
        self.session = session
        self.cfg = cfg
        self.settings = get_settings()

    def _check_budget(self) -> None:
        today = local_today()
        calls, out_tokens = self.session.execute(
            select(func.count(LlmUsage.id), func.coalesce(func.sum(LlmUsage.output_tokens), 0)).where(LlmUsage.day == today)
        ).one()
        if calls >= self.cfg.llm_max_calls_per_day:
            raise LlmBudgetExceeded(f"Limite diário de {self.cfg.llm_max_calls_per_day} chamadas atingido")
        if out_tokens >= self.settings.llm_max_output_tokens_per_day:
            raise LlmBudgetExceeded("Limite diário de tokens de saída atingido")

    def _record(self, result: LlmResult, purpose: str) -> None:
        s = self.settings
        cost = result.input_tokens / 1e6 * s.llm_price_input_per_mtok + result.output_tokens / 1e6 * s.llm_price_output_per_mtok
        self.session.add(
            LlmUsage(
                day=local_today(), provider=self.provider, model=result.model, purpose=purpose,
                input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                estimated_cost_usd=round(cost, 5), request_id=result.request_id,
            )
        )
        self.session.commit()

    def generate_json(self, *, system: str, user: str, schema: dict, model: str, max_tokens: int, purpose: str, effort: str = "medium") -> LlmResult:
        self._check_budget()
        result = self._call(system=system, user=user, schema=schema, model=model, max_tokens=max_tokens, effort=effort)
        self._record(result, purpose)
        return result

    def _call(self, **kw) -> LlmResult:  # pragma: no cover - sobrescrito
        raise LlmUnavailable("Nenhum provedor de IA configurado")


class AnthropicClient(LlmClient):
    provider = "anthropic"

    def __init__(self, session: Session, cfg: EditableSettings):
        super().__init__(session, cfg)
        import anthropic

        key = self.settings.llm_api_key.get_secret_value()
        if not key:
            raise LlmUnavailable("LLM_API_KEY ausente")
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=300)

    def _call(self, *, system, user, schema, model, max_tokens, effort) -> LlmResult:
        a = self._anthropic
        kwargs = {}
        if model in FALLBACK_MODELS:
            kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            with self.client.beta.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                **kwargs,
            ) as stream:
                msg = stream.get_final_message()
        except a.AuthenticationError as e:
            raise LlmError("Chave da API de IA inválida", retryable=False) from e
        except a.PermissionDeniedError as e:
            raise LlmError("Chave sem permissão para o modelo", retryable=False) from e
        except a.NotFoundError as e:
            raise LlmError(f"Modelo não encontrado: {model}", retryable=False) from e
        except a.BadRequestError as e:
            raise LlmError(f"Requisição rejeitada: {e.message}", retryable=False) from e
        except a.RateLimitError as e:
            raise LlmError("Limite de taxa do provedor de IA", retryable=True) from e
        except a.APIStatusError as e:
            raise LlmError(f"Erro do provedor de IA ({e.status_code})", retryable=e.status_code >= 500) from e
        except a.APIConnectionError as e:
            raise LlmError("Falha de conexão com o provedor de IA", retryable=True) from e
        if msg.stop_reason == "refusal":
            raise LlmError("O modelo recusou a solicitação", retryable=False)
        if msg.stop_reason == "max_tokens":
            raise LlmError("Resposta truncada (max_tokens)", retryable=False)
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LlmError("Resposta do modelo não é JSON válido", retryable=True) from e
        return LlmResult(data, msg.usage.input_tokens, msg.usage.output_tokens, msg.model, getattr(msg, "_request_id", None))


class OpenAICompatibleClient(LlmClient):
    provider = "openai_compatible"

    def __init__(self, session: Session, cfg: EditableSettings):
        super().__init__(session, cfg)
        if not self.settings.llm_base_url:
            raise LlmUnavailable("LLM_BASE_URL ausente para provedor openai_compatible")

    def _call(self, *, system, user, schema, model, max_tokens, effort) -> LlmResult:
        headers = {}
        key = self.settings.llm_api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "saida", "schema": schema, "strict": True}},
        }
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(timeout=300) as c:
                r = c.post(url, json=body, headers=headers)
                if r.status_code == 400:  # alguns servidores não aceitam json_schema
                    body["response_format"] = {"type": "json_object"}
                    body["messages"][0]["content"] += "\nResponda somente JSON válido seguindo o esquema:\n" + json.dumps(schema)
                    r = c.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise LlmError("Falha de conexão com o provedor de IA", retryable=True) from e
        if r.status_code in (401, 403):
            raise LlmError("Credencial do provedor de IA inválida", retryable=False)
        if r.status_code >= 400:
            raise LlmError(f"Erro do provedor de IA ({r.status_code})", retryable=r.status_code >= 500 or r.status_code == 429)
        payload = r.json()
        try:
            data = json.loads(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise LlmError("Resposta do modelo não é JSON válido", retryable=True) from e
        usage = payload.get("usage", {})
        return LlmResult(data, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), model, payload.get("id"))


def get_llm(session: Session, cfg: EditableSettings) -> LlmClient | None:
    try:
        if cfg.llm_provider == "anthropic":
            return AnthropicClient(session, cfg)
        if cfg.llm_provider == "openai_compatible":
            return OpenAICompatibleClient(session, cfg)
    except LlmUnavailable as e:
        log.warning("IA indisponível: %s", e)
    return None
