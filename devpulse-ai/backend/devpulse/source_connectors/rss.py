from __future__ import annotations

import feedparser

from devpulse.content_extraction.text import clean, strip_html, truncate
from devpulse.http import get_limited
from devpulse.source_connectors.base import (
    ConnectorContext,
    ConnectorError,
    FetchResult,
    RawItem,
    SourceConnector,
)
from devpulse.source_connectors.dates import from_struct
from devpulse.source_connectors.registry import register


@register("rss")
class RssConnector(SourceConnector):
    description = "Feed RSS ou Atom (usa ETag/Last-Modified para coleta incremental)."
    config_fields = {"max_items": "Máximo de itens por coleta (padrão 30)"}

    def validate_config(self, url, config):
        return [] if url and url.startswith(("http://", "https://")) else ["URL do feed obrigatória"]

    def fetch(self, ctx: ConnectorContext) -> FetchResult:
        if not ctx.source_url:
            raise ConnectorError("Fonte RSS sem URL")
        headers = {}
        if ctx.state.get("etag"):
            headers["If-None-Match"] = ctx.state["etag"]
        if ctx.state.get("last_modified"):
            headers["If-Modified-Since"] = ctx.state["last_modified"]
        resp = get_limited(ctx.http, ctx.source_url, headers=headers)
        state = {"etag": resp.headers.get("etag"), "last_modified": resp.headers.get("last-modified")}
        if resp.status_code == 304:
            return FetchResult(state=ctx.state, warnings=["Feed sem alterações (304)"])
        if resp.status_code >= 400:
            raise ConnectorError(f"HTTP {resp.status_code} ao ler o feed")
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            raise ConnectorError(f"Feed inválido: {feed.get('bozo_exception')}")
        result = FetchResult(state=state)
        limit = int(ctx.source_config.get("max_items", 30))
        for entry in feed.entries[:limit]:
            link = entry.get("link")
            title = clean(entry.get("title"))
            if not link or not str(link).startswith(("http://", "https://")) or not title:
                result.warnings.append("Entrada sem link ou título ignorada")
                continue
            content_html = ""
            if entry.get("content"):
                content_html = entry["content"][0].get("value", "")
            summary = strip_html(entry.get("summary", ""))
            content = strip_html(content_html)
            result.items.append(
                RawItem(
                    external_id=entry.get("id") or link,
                    url=link,
                    title=title,
                    summary=truncate(summary, 1200),
                    content=content,
                    content_access="full" if len(content) > 1500 else ("partial" if content else "summary_only"),
                    author=clean(entry.get("author")) or None,
                    published_at=from_struct(dict.get(entry, "published_parsed")),
                    # dict.get evita o mapeamento implícito do feedparser de updated -> published
                    updated_at=from_struct(dict.get(entry, "updated_parsed")),
                    language=(feed.feed.get("language") or "")[:2] or None,
                    raw={"tags": [t.get("term") for t in entry.get("tags", []) if t.get("term")]},
                )
            )
        return result
