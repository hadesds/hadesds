"""Conector genérico para APIs JSON públicas, com predefinições.

Configuração (``source.config``):
  preset: hackernews | cisa_kev   (opcional)
  items_path: caminho até a lista (ex.: "hits")
  fields: {id, title, url, summary, published, author}  — caminhos com ponto
  url_template: usado quando o item não tem URL (ex.: "https://x/{id}")
  min_points / max_items / max_age_days
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from devpulse.content_extraction.text import clean, truncate
from devpulse.http import get_limited
from devpulse.source_connectors.base import ConnectorContext, ConnectorError, FetchResult, RawItem, SourceConnector
from devpulse.source_connectors.dates import parse_any
from devpulse.source_connectors.registry import register
from devpulse.timeutil import utcnow

PRESETS: dict[str, dict[str, Any]] = {
    "hackernews": {
        "items_path": "hits",
        "fields": {
            "id": "objectID",
            "title": "title",
            "url": "url",
            "published": "created_at",
            "author": "author",
            "points": "points",
        },
        "url_template": "https://news.ycombinator.com/item?id={id}",
        "reference_type": "aggregator",
    },
    "cisa_kev": {
        "items_path": "vulnerabilities",
        "fields": {
            "id": "cveID",
            "title": "{vendorProject} {product}: {vulnerabilityName} ({cveID})",
            "summary": "shortDescription",
            "published": "dateAdded",
        },
        "url_template": "https://nvd.nist.gov/vuln/detail/{id}",
        "sort_desc_by": "dateAdded",
        "category": "seguranca",
    },
}


def dig(obj: Any, path: str) -> Any:
    for part in path.split(".") if path else []:
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit():
            obj = obj[int(part)] if int(part) < len(obj) else None
        else:
            return None
    return obj


def render(template_or_path: str, item: dict) -> Any:
    if "{" in template_or_path:
        try:
            return template_or_path.format(**{k: v for k, v in item.items() if isinstance(v, (str, int, float))})
        except (KeyError, IndexError):
            return None
    return dig(item, template_or_path)


@register("json_api")
class JsonApiConnector(SourceConnector):
    description = "API JSON pública com mapeamento de campos (predefinições: hackernews, cisa_kev)."
    config_fields = {
        "preset": "hackernews | cisa_kev",
        "items_path": "Caminho até a lista de itens",
        "fields": "Mapa de campos",
        "max_items": "Máximo de itens",
        "max_age_days": "Ignorar itens mais antigos",
        "min_points": "Pontuação mínima (Hacker News)",
    }

    def fetch(self, ctx: ConnectorContext) -> FetchResult:
        cfg = dict(PRESETS.get(ctx.source_config.get("preset", ""), {}))
        cfg.update({k: v for k, v in ctx.source_config.items() if k != "state"})
        if not ctx.source_url:
            raise ConnectorError("Fonte JSON sem URL")
        resp = get_limited(ctx.http, ctx.source_url, headers={"Accept": "application/json"})
        if resp.status_code >= 400:
            raise ConnectorError(f"HTTP {resp.status_code} na API")
        try:
            data = resp.json()
        except ValueError as e:
            raise ConnectorError("Resposta não é JSON") from e
        items = dig(data, cfg.get("items_path", "")) if cfg.get("items_path") else data
        if not isinstance(items, list):
            raise ConnectorError("Caminho de itens não aponta para uma lista")
        if cfg.get("sort_desc_by"):
            items = sorted(items, key=lambda i: str(i.get(cfg["sort_desc_by"], "")), reverse=True)
        fields = cfg.get("fields", {})
        max_age = cfg.get("max_age_days")
        cutoff = utcnow() - timedelta(days=int(max_age)) if max_age else None
        result = FetchResult()
        for it in items[: int(cfg.get("max_items", 30))]:
            ext_id = str(render(fields.get("id", "id"), it) or "")
            title = clean(str(render(fields.get("title", "title"), it) or ""))
            url = render(fields.get("url", "url"), it) if fields.get("url") else None
            if not url and cfg.get("url_template") and ext_id:
                url = cfg["url_template"].format(id=ext_id)
            if not ext_id or not title or not url:
                continue
            points = render(fields["points"], it) if fields.get("points") else None
            if cfg.get("min_points") and (points or 0) < int(cfg["min_points"]):
                continue
            published = parse_any(render(fields["published"], it)) if fields.get("published") else None
            if cutoff and published and published < cutoff:
                continue
            summary = render(fields["summary"], it) if fields.get("summary") else ""
            result.items.append(
                RawItem(
                    external_id=ext_id,
                    url=str(url),
                    title=title,
                    summary=truncate(clean(str(summary or "")), 1200),
                    author=(render(fields["author"], it) if fields.get("author") else None),
                    published_at=published,
                    category_hint=cfg.get("category"),
                    reference_type=cfg.get("reference_type", "origin"),
                    raw={"points": points, "api_item_id": ext_id},
                )
            )
        return result
