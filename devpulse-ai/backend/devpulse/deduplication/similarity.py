"""Similaridade entre matérias (lexical + termos-chave).

Combina Jaccard de tokens do título, razão de sequência e sobreposição de
"termos-chave" (nomes próprios, versões, números) — uma aproximação semântica
barata e determinística. Pode ser complementada por embeddings no futuro.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from devpulse.content_extraction.text import normalize_for_match, tokens
from devpulse.deduplication.normalize import STOPWORDS, title_tokens

_KEY = re.compile(r"\b(?:[A-Z][\w.+#-]*[A-Za-z0-9+#]|[A-Za-z]*\d[\w.]*)\b")
GENERIC_KEYS = {"The", "A", "An", "How", "Why", "What", "New", "Now", "O", "A", "Como", "Por", "Novo", "Nova"}


def key_terms(text: str) -> set[str]:
    return {m.lower() for m in _KEY.findall(text or "") if m not in GENERIC_KEYS and len(m) > 1}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)*\b")


def versions(text: str) -> set[str]:
    return set(_VERSION.findall((text or "").lower()))


def title_similarity(a: str, b: str) -> float:
    va, vb = versions(a), versions(b)
    if va and vb and not (va & vb):
        return 0.0  # versões diferentes (ex.: 26.11.0 x 26.11.1) são acontecimentos distintos
    ta, tb = set(title_tokens(a)), set(title_tokens(b))
    jac = jaccard(ta, tb)
    seq = SequenceMatcher(None, normalize_for_match(a), normalize_for_match(b)).ratio()
    keys = jaccard(key_terms(a), key_terms(b))
    return round(0.45 * jac + 0.25 * seq + 0.30 * keys, 4)


def shingles(text: str, n: int = 5) -> set[tuple[str, ...]]:
    t = [w for w in tokens(text) if w not in STOPWORDS]
    return {tuple(t[i : i + n]) for i in range(max(0, len(t) - n + 1))}


def content_similarity(a: str, b: str) -> float:
    """Alta similaridade indica republicação do mesmo comunicado."""
    return round(jaccard(shingles(a), shingles(b)), 4)


SAME_EVENT_THRESHOLD = 0.55
SAME_TEXT_THRESHOLD = 0.5
