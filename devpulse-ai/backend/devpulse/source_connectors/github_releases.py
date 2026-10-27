from __future__ import annotations

from devpulse.config import get_settings
from devpulse.content_extraction.text import clean, truncate
from devpulse.http import get_limited
from devpulse.source_connectors.base import ConnectorContext, ConnectorError, FetchResult, RawItem, SourceConnector
from devpulse.source_connectors.dates import parse_any
from devpulse.source_connectors.registry import register


@register("github_releases")
class GithubReleasesConnector(SourceConnector):
    description = "Releases oficiais de um repositório GitHub (API REST pública)."
    config_fields = {"repo": "owner/repo", "include_prereleases": "true/false", "max_items": "padrão 5"}

    def validate_config(self, url, config):
        repo = config.get("repo", "")
        return [] if repo.count("/") == 1 else ["Informe config.repo no formato owner/repo"]

    def fetch(self, ctx: ConnectorContext) -> FetchResult:
        repo = ctx.source_config.get("repo")
        if not repo:
            raise ConnectorError("config.repo ausente")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        token = get_settings().github_token.get_secret_value()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        per_page = int(ctx.source_config.get("max_items", 5))
        resp = get_limited(ctx.http, f"https://api.github.com/repos/{repo}/releases?per_page={per_page}", headers=headers)
        if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
            raise ConnectorError("Limite de requisições da API do GitHub atingido (configure GITHUB_TOKEN)")
        if resp.status_code >= 400:
            raise ConnectorError(f"HTTP {resp.status_code} na API do GitHub")
        result = FetchResult()
        for rel in resp.json():
            if rel.get("draft") or (rel.get("prerelease") and not ctx.source_config.get("include_prereleases")):
                continue
            body = clean(rel.get("body") or "")
            name = clean(rel.get("name") or rel.get("tag_name") or "")
            result.items.append(
                RawItem(
                    external_id=str(rel["id"]),
                    url=rel["html_url"],
                    title=f"{repo} {name}" if repo.split("/")[1].lower() not in name.lower() else name,
                    summary=truncate(body, 1200),
                    content=body,
                    content_access="full" if body else "summary_only",
                    author=(rel.get("author") or {}).get("login"),
                    published_at=parse_any(rel.get("published_at")),
                    language="en",
                    raw={"tag": rel.get("tag_name"), "repo": repo, "prerelease": rel.get("prerelease")},
                )
            )
        return result
