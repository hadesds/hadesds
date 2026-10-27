from __future__ import annotations

import html
import re
import unicodedata

_WS = re.compile(r"\s+")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú0-9\"“])")
PT_WORDS = {"de", "que", "não", "para", "com", "uma", "os", "no", "na", "em", "do", "da", "são", "também", "pela", "mais"}
EN_WORDS = {"the", "and", "of", "to", "is", "in", "for", "with", "that", "this", "are", "on", "you", "we", "new"}


def clean(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", html.unescape(text)).strip()


def strip_html(markup: str | None) -> str:
    if not markup:
        return ""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(markup, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return clean(soup.get_text(" "))


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


_ABBREV = re.compile(r"(?i)(\b(u\.s|u\.k|e\.g|i\.e|inc|ltd|co|corp|mr|mrs|ms|dr|jr|st|vs|no|sr|sra|prof|etc)|\b[A-Z])\.$")


def sentences(text: str) -> list[str]:
    parts: list[str] = []
    for frag in _SENT.split(clean(text)):
        if parts and _ABBREV.search(parts[-1]):
            parts[-1] = f"{parts[-1]} {frag}"
        else:
            parts.append(frag)
    return [s.strip() for s in parts if len(s.strip()) > 20]


def detect_language(text: str) -> str | None:
    words = re.findall(r"[a-zà-ú]+", (text or "").lower())
    if len(words) < 5:
        return None
    pt = sum(w in PT_WORDS for w in words)
    en = sum(w in EN_WORDS for w in words)
    if pt == en == 0:
        return None
    return "pt" if pt > en else "en"


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9.+#]+", " ", text)
    return _WS.sub(" ", text).strip()


def tokens(text: str) -> list[str]:
    return [t for t in normalize_for_match(text).split() if len(t) > 1]
