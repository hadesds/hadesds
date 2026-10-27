"""Classificação por categoria editorial e tipo de conteúdo (léxico ponderado)."""
from __future__ import annotations

import re

from devpulse.content_extraction.text import normalize_for_match

LEXICON: dict[str, dict[str, float]] = {
    "desenvolvimento": {
        "python": 2, "javascript": 2, "typescript": 2, "java": 1.5, "golang": 2, " go ": 1, "rust": 2, "c#": 2,
        ".net": 2, "react": 2, "next.js": 2, "nextjs": 2, "django": 2, "fastapi": 2, "node.js": 2, "nodejs": 2,
        "deno": 2, "bun": 1, "framework": 1.5, "api": 1, "sdk": 1.5, "compiler": 1.5, "compilador": 1.5,
        "release": 1, "lançamento": 0.5, "version": 0.5, "versão": 0.5, "git": 1.5, "github": 1.5, "gitlab": 1.5,
        "ci/cd": 2, "pull request": 1.5, "database": 1.5, "banco de dados": 1.5, "postgres": 2, "sql": 1.5,
        "testing": 1.5, "testes": 1.5, "refactor": 1, "library": 1.5, "biblioteca": 1.5, "npm": 1.5, "pypi": 1.5,
        "vscode": 1.5, "visual studio": 1.5, "ide": 1, "linguagem": 1, "programming": 1.5, "programação": 1.5,
        "developer": 1, "desenvolvedor": 1, "wasm": 1.5, "webassembly": 1.5, "frontend": 1.5, "backend": 1.5,
    },
    "ia": {
        "ai ": 2, " ia ": 2, "artificial intelligence": 3, "inteligência artificial": 3, "llm": 3, "gpt": 2.5,
        "claude": 2.5, "gemini": 2.5, "llama": 2, "openai": 2.5, "anthropic": 2.5, "deepmind": 2.5,
        "copilot": 2, "agent": 1.5, "agente": 1.5, "machine learning": 2.5, "model": 1, "modelo": 0.8,
        "prompt": 1.5, "embedding": 2, "rag": 1.5, "fine-tun": 2, "neural": 1.5, "hugging face": 2, "mcp": 1.5,
        "chatbot": 2, "generative": 2, "generativa": 2, "inference": 1.5, "inferência": 1.5,
    },
    "infraestrutura": {
        "kubernetes": 3, "k8s": 2.5, "docker": 2.5, "container": 2, "cloud": 2, "nuvem": 2, "aws": 2.5,
        "azure": 2.5, "google cloud": 2.5, "gcp": 2, "serverless": 2, "terraform": 2.5, "devops": 2.5,
        "observability": 2.5, "observabilidade": 2.5, "opentelemetry": 2.5, "prometheus": 2, "grafana": 2,
        "linux": 1.5, "datacenter": 2, "cdn": 1.5, "cloudflare": 2, "scalab": 1.5, "escalab": 1.5,
        "outage": 2, "instabilidade": 2, "infrastructure": 2, "infraestrutura": 2, "open source": 1,
    },
    "seguranca": {
        "cve-": 3, "vulnerab": 3, "exploit": 3, "malware": 3, "ransomware": 3, "breach": 2.5, "vazamento": 2.5,
        "phishing": 2.5, "zero-day": 3, "0-day": 3, "patch": 1.5, "correção de segurança": 3, "security": 2,
        "segurança": 2, "supply chain": 2.5, "backdoor": 3, "cisa": 2.5, "attack": 2, "ataque": 2,
        "credential": 1.5, "senha": 1, "authentication": 1, "hacker": 2,
    },
    "mercado": {
        "layoff": 3, "demiss": 3, "hiring": 2.5, "contrata": 2.5, "vagas": 2.5, "jobs": 1.5, "carreira": 2.5,
        "career": 2.5, "salary": 2.5, "salário": 2.5, "startup": 2, "funding": 2.5, "investimento": 2,
        "raises": 2, "series a": 3, "series b": 3, "acquisition": 3, "aquisição": 3, "acquires": 3,
        "adquire": 3, "ipo": 3, "initial public offering": 4, "oferta pública inicial": 4, "abertura de capital": 4, "valuation": 2.5, "market": 1, "mercado": 1.5, "skills": 1.5,
        "competências": 2, "survey": 1.5, "pesquisa": 0.8, "regulation": 2, "regulação": 2, "antitrust": 2.5,
    },
}

RUMOR = re.compile(r"(?i)\b(rumor|boato|reportedly|leak(ed)?|vazad[oa]|allegedly|supostamente|segundo fontes|sources say|could be|pode estar)\b")
OPINION = re.compile(r"(?i)(^why |^por que |opinion|opinião|i think|\bmy take\b|\bacho que\b|editorial|essay)")
FORECAST = re.compile(r"(?i)\b(will|vai|irá|deve(rá)?|forecast|previsão|predict|expected to|espera-se|by 20\d\d|até 20\d\d)\b")


def classify(title: str, text: str = "", hint: str | None = None) -> tuple[str, dict[str, float]]:
    blob = f" {normalize_for_match(title)} {normalize_for_match(title)} {normalize_for_match(text[:3000])} "
    scores = {cat: 0.0 for cat in LEXICON}
    for cat, words in LEXICON.items():
        for w, weight in words.items():
            n = blob.count(normalize_for_match(w) if w.strip() == w else w)
            scores[cat] += weight * min(n, 4)
    if hint in scores:
        scores[hint] += 3
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        best = hint or "desenvolvimento"
    return best, scores


def content_type(title: str, summary: str = "") -> str:
    text = f"{title} {summary[:400]}"
    if RUMOR.search(text):
        return "rumor"
    if OPINION.search(title):
        return "opinion"
    if FORECAST.search(title):
        return "forecast"
    return "fact"
