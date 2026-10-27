"""Nível da fonte por domínio (1 = oficial ... 5 = independente/agregador)."""
from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from devpulse.models import Source

# Domínios de anúncios oficiais/documentação de empresas e projetos relevantes.
OFFICIAL_DOMAINS = {
    "openai.com": 1, "anthropic.com": 1, "blog.google": 1, "developers.googleblog.com": 1, "deepmind.google": 1,
    "ai.google.dev": 1, "microsoft.com": 1, "devblogs.microsoft.com": 1, "azure.microsoft.com": 1, "ai.meta.com": 1,
    "engineering.fb.com": 1, "about.fb.com": 1, "aws.amazon.com": 1, "cloud.google.com": 1, "python.org": 1,
    "blog.python.org": 1, "nodejs.org": 1, "go.dev": 1, "rust-lang.org": 1, "blog.rust-lang.org": 1,
    "react.dev": 1, "nextjs.org": 1, "vercel.com": 1, "djangoproject.com": 1, "kubernetes.io": 1,
    "docker.com": 1, "github.blog": 1, "about.gitlab.com": 1, "cisa.gov": 1, "nvd.nist.gov": 1,
    "huggingface.co": 1, "mozilla.org": 1, "apple.com": 1, "developer.apple.com": 1, "android-developers.googleblog.com": 1,
    "typescriptlang.org": 1, "fastapi.tiangolo.com": 1, "postgresql.org": 1, "cloudflare.com": 1, "blog.cloudflare.com": 1,
    "github.com": 2, "pypi.org": 2, "npmjs.com": 2, "gitlab.com": 2, "docs.python.org": 1,
}
AGGREGATORS = {"news.ycombinator.com": 5, "reddit.com": 5, "x.com": 5, "twitter.com": 5, "medium.com": 5, "dev.to": 5}


def domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _match(host: str, table: dict[str, int]) -> int | None:
    parts = host.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in table:
            return table[cand]
    return None


def tier_for_url(session: Session | None, url: str, default: int = 4) -> int:
    host = domain(url)
    if session is not None:
        for src in session.scalars(select(Source).where(Source.url.is_not(None))):
            if domain(src.url or "") == host and src.connector_type not in ("json_api", "email_newsletter"):
                return src.priority_tier
    return _match(host, OFFICIAL_DOMAINS) or _match(host, AGGREGATORS) or default


EVIDENCE_BY_TIER = {1: "primary_source", 2: "official_repository", 3: "newsletter", 4: "specialized_press", 5: "independent"}
RELIABILITY_BY_TIER = {1: 1.0, 2: 0.95, 3: 0.7, 4: 0.75, 5: 0.5}
