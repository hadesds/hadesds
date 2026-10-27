"""Pesquisa de recursos visuais a partir das páginas coletadas.

Só recomenda URLs que o sistema efetivamente encontrou nas fontes. A licença
quase nunca é declarada nas páginas; nesses casos fica registrada como
desconhecida e o roteiro instrui a verificação antes do uso.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from devpulse.content_extraction.extractor import GITHUB_REPO, check_link
from devpulse.editorial_scoring.reliability import domain
from devpulse.script_generation.sources import SourceDoc

DOCS_HINT = re.compile(r"(?i)(/docs?/|docs\.|/documentation|/reference|/guide|/changelog|/release-notes)")
UNKNOWN = "Desconhecida — verificar termos de uso do site antes de reutilizar"
SCREENSHOT = "Captura de tela própria da página, para fins jornalísticos/comentário; cite a fonte na tela"


@dataclass
class AssetCandidate:
    ref: str
    kind: str
    description: str
    url: str | None
    source_page_url: str | None
    license_info: str
    accessible: bool | None = None


def research(docs: list[SourceDoc], http: httpx.Client | None, verify: bool = True, max_assets: int = 10) -> list[AssetCandidate]:
    out: list[AssetCandidate] = []
    seen: set[str] = set()

    def add(kind: str, desc: str, url: str | None, page: str | None, lic: str) -> None:
        key = url or desc
        if key in seen or len(out) >= max_assets:
            return
        seen.add(key)
        out.append(AssetCandidate(f"A{len(out) + 1}", kind, desc, url, page, lic))

    for d in docs:
        add("page_screenshot", f"Página da fonte ({d.publisher}): {d.title}", d.url, d.url, SCREENSHOT)
    for d in docs:
        extraction = (d.item.raw or {}).get("extraction", {})
        for img in extraction.get("images", [])[:1]:
            kind = "official_image" if d.tier <= 2 else "article_image"
            add(kind, f"Imagem de destaque publicada por {d.publisher} ({img.get('kind')})", img["url"], d.url, UNKNOWN)
        links = extraction.get("links", [])
        for link in links:
            if GITHUB_REPO.match(link.rstrip("/")) and "/sponsors" not in link:
                add("repository", f"Repositório citado na fonte: {urlparse(link).path.strip('/')}", link, d.url,
                    "Página pública do GitHub; verifique a licença do repositório para trechos de código")
        for link in links:
            if DOCS_HINT.search(link) and domain(link) == d.publisher:
                add("documentation", f"Documentação/notas citadas em {d.publisher}", link, d.url, SCREENSHOT)
    add(
        "to_produce",
        "Card próprio com o título da notícia e 2–3 pontos-chave (produzir no editor de vídeo; sem imagens de terceiros)",
        None, None, "Material original — livre para uso",
    )
    if verify and http is not None:
        for a in out:
            if a.url:
                ok, _, _ = check_link(http, a.url)
                a.accessible = ok
    return out
