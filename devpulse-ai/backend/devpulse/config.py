"""Configuração da aplicação carregada de variáveis de ambiente.

Segredos (senhas, tokens, chaves) só existem aqui e nunca são gravados no banco
nem expostos pela API. Parâmetros editoriais e operacionais podem ser
sobrescritos pelo painel (ver ``devpulse.settings_service``).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Aplicação ---
    app_env: Literal["development", "production", "test"] = "production"
    log_level: str = "INFO"
    timezone: str = "America/Fortaleza"
    secret_key: SecretStr = SecretStr("")
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("")
    dashboard_public_url: str = "http://localhost:8080"
    cors_origins: str = "http://localhost:5173"
    frontend_dist: str = "/app/frontend_dist"
    sources_file: str = "/app/config/sources.yaml"
    plugin_modules: str = ""  # módulos extras com conectores, separados por vírgula
    http_user_agent: str = "DevPulseAI/1.0 (+uso pessoal; leitor de feeds)"
    http_timeout_seconds: float = 20.0

    # --- Banco ---
    database_url: str = "postgresql+psycopg://devpulse:devpulse@db:5432/devpulse"

    # --- Agenda (valores iniciais; podem ser alterados no painel) ---
    edition_main_time: str = "08:00"
    edition_secondary_time: str = ""  # vazio = desativado
    edition_catchup_until: str = "14:00"
    collect_interval_minutes: int = 60
    daily_script_limit: int = 3

    # --- IA ---
    llm_provider: Literal["anthropic", "openai_compatible", "none"] = "none"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""  # para openai_compatible (ex.: http://host.docker.internal:11434/v1)
    llm_model_script: str = "claude-opus-5-5"
    llm_model_fast: str = "claude-haiku-5-5"
    llm_max_calls_per_day: int = 40
    llm_max_output_tokens_per_day: int = 400_000
    llm_price_input_per_mtok: float = 4.0
    llm_price_output_per_mtok: float = 20.0

    # --- Caixa de entrada de newsletters ---
    newsletter_mailbox_provider: Literal["none", "imap", "gmail", "graph"] = "none"
    newsletter_mailbox_address: str = ""  # conta que RECEBE a newsletter (não é o remetente)
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: SecretStr = SecretStr("")
    imap_folder: str = "INBOX"
    gmail_client_id: str = ""
    gmail_client_secret: SecretStr = SecretStr("")
    gmail_refresh_token: SecretStr = SecretStr("")
    graph_tenant_id: str = "consumers"
    graph_client_id: str = ""
    graph_client_secret: SecretStr = SecretStr("")
    graph_refresh_token: SecretStr = SecretStr("")

    # --- E-mail de saída ---
    email_enabled: bool = False
    email_recipient: str = ""  # destinatário das edições
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_security: Literal["starttls", "ssl"] = "starttls"

    # --- WhatsApp Business Platform (Cloud API) ---
    whatsapp_enabled: bool = False
    whatsapp_access_token: SecretStr = SecretStr("")
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = "v23.0"
    whatsapp_recipient: str = ""  # E.164, ex.: +5598999999999
    whatsapp_recipient_opt_in: bool = False
    whatsapp_mode: Literal["template", "text"] = "template"
    whatsapp_template_name: str = ""
    whatsapp_template_language: str = "pt_BR"

    # --- GitHub (opcional, só aumenta limite de requisições) ---
    github_token: SecretStr = SecretStr("")

    # --- Testes / segurança de envio ---
    allow_real_sends_in_tests: bool = False

    @field_validator("daily_script_limit")
    @classmethod
    def _limit(cls, v: int) -> int:
        if not 0 <= v <= 3:
            raise ValueError("DAILY_SCRIPT_LIMIT deve estar entre 0 e 3")
        return v

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()


SECRET_FIELD_NAMES = {
    name for name, field in Settings.model_fields.items() if field.annotation is SecretStr
}

__all__ = ["Settings", "get_settings", "reset_settings_cache", "SECRET_FIELD_NAMES"]
