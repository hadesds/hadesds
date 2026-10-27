"""Extração do conteúdo legitimamente acessível de uma página.

Respeita robots.txt e não tenta contornar paywalls ou autenticação: quando o
conteúdo não está disponível, registra a limitação.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from devpulse.config import get_settings
from devpulse.content_extraction.text import clean, detect_language
from devpulse.http import get_limited
from devpulse.source_connectors.dates import parse_any

log = logging.getLogger(__name__)
_robots_cache: dict[str, RobotFileParser | None] = {}


@dataclass
class ExtractedPage:
    requested_url: str
    final_url: str
    status_code: int
    accessible: bool
    access: str  # full | partial | summary_only | unavailable | restricted
    title: str = ""
    description: str = ""
    text: str = ""
    author: str | None = None
    published_at: datetime | None = None
    modified_at: datetime | None = None
    language: str | None = None
    images: list[dict] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    error: str | None = None


def robots_allowed(http: httpx.Client, url: str) -> bool:
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots_cache:
        rp = RobotFileParser()
        try:
            r = http.get(base + "/robots.txt", timeout=8)
            if r.status_code >= 400:
                _robots_cache[base] = None
            else:
                rp.parse(r.text.splitlines())
                _robots_cache[base] = rp
        except httpx.HTTPError:
            _robots_cache[base] = None
    rp = _robots_cache[base]
    return True if rp is None else rp.can_fetch(get_settings().http_user_agent, url)


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if tag and tag.get("content"):
            return clean(tag["content"])
    return ""


def _jsonld(soup: BeautifulSoup) -> list[dict]:
    out = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        out.extend(i for i in items if isinstance(i, dict))
    return out


def _main_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [clean(p.get_text(" ")) for p in root.find_all(["p", "li", "h2", "h3", "pre"])]
    return "\n".join(p for p in paragraphs if len(p) > 30)


def parse_html(requested_url: str, final_url: str, status: int, markup: str) -> ExtractedPage:
    soup = BeautifulSoup(markup, "lxml")
    ld = _jsonld(soup)
    article_ld = next((i for i in ld if str(i.get("@type", "")).lower() in {"newsarticle", "article", "blogposting", "techarticle"}), {})
    published = parse_any(
        _meta(soup, "article:published_time", "og:published_time", "datePublished", "pubdate")
        or article_ld.get("datePublished")
    )
    if not published:
        t = soup.find("time", datetime=True)
        published = parse_any(t["datetime"]) if t else None
    modified = parse_any(_meta(soup, "article:modified_time", "og:updated_time") or article_ld.get("dateModified"))
    author = _meta(soup, "author", "article:author")
    if not author and isinstance(article_ld.get("author"), dict):
        author = article_ld["author"].get("name", "")
    restricted = article_ld.get("isAccessibleForFree") in (False, "False", "false")
    images = []
    for prop in ("og:image", "twitter:image"):
        src = _meta(soup, prop)
        if src:
            images.append({"url": urljoin(final_url, src), "kind": prop})
    links = sorted(
        {urljoin(final_url, a["href"]) for a in soup.find_all("a", href=True) if a["href"].startswith(("http", "/"))}
    )
    title = _meta(soup, "og:title") or clean(soup.title.get_text() if soup.title else "")
    description = _meta(soup, "og:description", "description")
    text = _main_text(soup)
    if restricted:
        access = "restricted"
    elif len(text) > 1500:
        access = "full"
    elif text:
        access = "partial"
    else:
        access = "summary_only" if description else "unavailable"
    return ExtractedPage(
        requested_url=requested_url,
        final_url=final_url,
        status_code=status,
        accessible=True,
        access=access,
        title=title,
        description=description,
        text=text[:60_000],
        author=author or None,
        published_at=published,
        modified_at=modified,
        language=(soup.html.get("lang", "")[:2].lower() if soup.html and soup.html.get("lang") else None)
        or detect_language(text),
        images=images,
        links=links[:300],
    )


def extract(http: httpx.Client, url: str) -> ExtractedPage:
    if not robots_allowed(http, url):
        return ExtractedPage(url, url, 0, False, "unavailable", error="Bloqueado por robots.txt")
    try:
        resp = get_limited(http, url)
    except (httpx.HTTPError, ValueError) as e:
        return ExtractedPage(url, url, 0, False, "unavailable", error=f"Erro de rede: {type(e).__name__}")
    final = str(resp.url)
    if resp.status_code in (401, 402, 403):
        return ExtractedPage(url, final, resp.status_code, False, "restricted", error=f"Acesso restrito (HTTP {resp.status_code})")
    if resp.status_code >= 400:
        return ExtractedPage(url, final, resp.status_code, False, "unavailable", error=f"HTTP {resp.status_code}")
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype:
        return ExtractedPage(url, final, resp.status_code, True, "unavailable", error=f"Conteúdo não-HTML ({ctype})")
    return parse_html(url, final, resp.status_code, resp.text)


def check_link(http: httpx.Client, url: str) -> tuple[bool, int, str]:
    """Verifica se um link responde. Retorna (acessível, status, url_final)."""
    try:
        r = http.head(url)
        if r.status_code in (405, 403, 400) or r.status_code >= 500:
            r = http.get(url)
        return r.status_code < 400, r.status_code, str(r.url)
    except httpx.HTTPError:
        return False, 0, url


GITHUB_REPO = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/?$")
