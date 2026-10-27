from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from devpulse.content_extraction.text import tokens

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "ref", "ref_src", "source", "igshid",
    "_hsenc", "_hsmi", "mkt_tok", "s_cid", "cmpid", "spm",
}
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "now", "new",
    "o", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "e", "em", "no", "na", "para",
    "com", "por", "que", "agora", "novo", "nova", "how", "what", "why", "your", "you", "seu", "sua",
}


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if p.port and p.port not in (80, 443):
        host = f"{host}:{p.port}"
    query = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    path = p.path.rstrip("/") or "/"
    return urlunparse(("https", host, path, "", urlencode(sorted(query)), ""))


def title_tokens(title: str) -> list[str]:
    return [t for t in tokens(title) if t not in STOPWORDS]


def title_fingerprint(title: str) -> str:
    return hashlib.sha256(" ".join(sorted(set(title_tokens(title)))).encode()).hexdigest()


def content_hash(text: str) -> str | None:
    norm = " ".join(tokens(text))
    return hashlib.sha256(norm.encode()).hexdigest() if len(norm) > 200 else None
