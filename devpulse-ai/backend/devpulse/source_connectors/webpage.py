"""Página de listagem configurada pelo usuário (ex.: sala de imprensa sem RSS).

Extrai links que casam com ``link_pattern``. Datas de publicação não são
inferidas a partir da coleta: ficam vazias até a extração do artigo encontrar
metadados (``article:published_time``, JSON-LD, ``<time>``).
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from devpulse.content_extraction.text import clean
from devpulse.http import get_limited
from devpulse.source_connectors.base import ConnectorContext, ConnectorError, FetchResult, RawItem, SourceConnector
from devpulse.source_connectors.registry import register


@register("webpage")
class WebpageConnector(SourceConnector):
    description = "Página de listagem de notícias (links filtrados por expressão regular)."
    config_fields = {
        "link_pattern": "Regex aplicada ao href (ex.: ^/news/)",
        "exclude_pattern": "Regex de links a ignorar (ex.: páginas de categoria)",
        "max_items": "padrão 20",
    }

    def validate_config(self, url, config):
        errors = [] if url else ["URL obrigatória"]
        try:
            re.compile(config.get("link_pattern", "."))
        except re.error:
            errors.append("link_pattern inválido")
        return errors

    def fetch(self, ctx: ConnectorContext) -> FetchResult:
        if not ctx.source_url:
            raise ConnectorError("Fonte sem URL")
        resp = get_limited(ctx.http, ctx.source_url)
        if resp.status_code >= 400:
            raise ConnectorError(f"HTTP {resp.status_code} ao ler a página")
        pattern = re.compile(ctx.source_config.get("link_pattern", "."))
        exclude = re.compile(ctx.source_config["exclude_pattern"]) if ctx.source_config.get("exclude_pattern") else None
        soup = BeautifulSoup(resp.text, "lxml")
        seen: set[str] = set()
        result = FetchResult()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not pattern.search(href) or (exclude and exclude.search(href)):
                continue
            url = urljoin(str(resp.url), href)
            if url in seen or url.rstrip("/") == str(resp.url).rstrip("/"):
                continue
            heading = a.find(["h1", "h2", "h3", "h4"])
            title = clean((heading or a).get_text(" "))
            if len(title) < 12:
                continue
            seen.add(url)
            result.items.append(RawItem(external_id=url, url=url, title=title[:300], content_access="unavailable"))
            if len(result.items) >= int(ctx.source_config.get("max_items", 20)):
                break
        if not result.items:
            result.warnings.append("Nenhum link casou com link_pattern")
        return result
