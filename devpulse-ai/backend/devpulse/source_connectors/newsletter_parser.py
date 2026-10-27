"""Transforma o HTML de uma newsletter em itens (um por matéria citada).

Guarda apenas título, link e um trecho curto de contexto — a newsletter nunca é
armazenada ou reproduzida integralmente.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from devpulse.content_extraction.text import clean, truncate

SKIP_TEXT = re.compile(
    r"(?i)(unsubscribe|descadastr|cancelar inscri|preferênc|ver no navegador|view in browser|"
    r"compartilh|share|indique|patrocin|sponsor|anuncie|advertis|privacidade|privacy|termos|"
    r"instagram|twitter|linkedin|facebook|youtube|tiktok|whatsapp|^\s*aqui\s*$|^\s*leia mais\s*$)"
)
SKIP_HOST = re.compile(r"(?i)(facebook|instagram|twitter|x\.com|linkedin|youtube|tiktok|wa\.me|whatsapp)")
CONTEXT_LIMIT = 400


@dataclass
class NewsletterStory:
    title: str
    url: str
    context: str


def _context_for(a: Tag) -> str:
    block = a.find_parent(["p", "li", "td", "div"])
    return truncate(clean(block.get_text(" ")) if block else "", CONTEXT_LIMIT)


def _title_for(a: Tag) -> str:
    text = clean(a.get_text(" "))
    if len(text) >= 15 and not SKIP_TEXT.search(text):
        return text
    heading = a.find_previous(["h1", "h2", "h3", "h4", "strong", "b"])
    if heading:
        htext = clean(heading.get_text(" "))
        if len(htext) >= 15:
            return htext
    return ""


def parse_newsletter(html: str, text: str = "") -> list[NewsletterStory]:
    if not html and text:
        urls = re.findall(r"https?://[^\s<>\)\]]+", text)
        return [NewsletterStory(title="", url=u, context="") for u in dict.fromkeys(urls)]
    soup = BeautifulSoup(html or "", "lxml")
    stories: dict[str, NewsletterStory] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        anchor = clean(a.get_text(" "))
        if SKIP_TEXT.search(anchor) or SKIP_HOST.search(urlparse(href).netloc):
            continue
        title = _title_for(a)
        if not title or href in stories:
            continue
        stories[href] = NewsletterStory(title=title[:300], url=href, context=_context_for(a))
    return list(stories.values())
