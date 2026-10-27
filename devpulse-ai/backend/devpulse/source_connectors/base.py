"""Interface comum dos conectores de fontes.

Para criar um novo tipo de fonte, implemente ``SourceConnector`` e registre-o com
``@register("meu_tipo")`` num módulo listado em ``PLUGIN_MODULES``. O núcleo não
precisa ser alterado.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import httpx


@dataclass
class RawItem:
    external_id: str
    url: str
    title: str
    summary: str = ""
    content: str = ""
    content_access: str = "summary_only"  # full | partial | summary_only | unavailable | restricted
    author: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    language: str | None = None
    category_hint: str | None = None
    reference_type: str = "origin"  # origin | newsletter_mention | aggregator
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    items: list[RawItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)  # persistido em source.config["state"]


@dataclass
class ConnectorContext:
    http: httpx.Client
    source_config: dict[str, Any]
    source_url: str | None
    state: dict[str, Any]
    since: datetime | None


class ConnectorError(Exception):
    """Falha esperada (credencial ausente, HTTP 4xx/5xx, formato inválido)."""


class SourceConnector(ABC):
    type_name: ClassVar[str]
    description: ClassVar[str] = ""
    # campos de configuração aceitos (exibidos no painel)
    config_fields: ClassVar[dict[str, str]] = {}

    @abstractmethod
    def fetch(self, ctx: ConnectorContext) -> FetchResult: ...

    def validate_config(self, url: str | None, config: dict[str, Any]) -> list[str]:
        return []
