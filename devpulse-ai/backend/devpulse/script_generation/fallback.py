"""Gerador extrativo (sem IA).

Monta um roteiro-base usando apenas frases literais das fontes. É claramente
identificado como tal: as citações ficam no idioma original e a análise de
impacto fica a cargo do apresentador. Garante que o sistema nunca invente
conteúdo quando não há provedor de IA configurado ou o orçamento acabou.
"""
from __future__ import annotations

import re

from devpulse.content_extraction.text import sentences, truncate
from devpulse.deduplication.normalize import title_tokens
from devpulse.media_research.research import AssetCandidate
from devpulse.script_generation.schema import Claim, Planning, Publication, RecordingGuide, Scene
from devpulse.script_generation.sources import SourceDoc

CATEGORY_LABEL = {
    "desenvolvimento": "desenvolvimento de software",
    "ia": "inteligência artificial",
    "infraestrutura": "infraestrutura",
    "seguranca": "segurança",
    "mercado": "mercado de tecnologia",
}
HASHTAGS = {
    "desenvolvimento": ["#programacao", "#desenvolvimento", "#dev"],
    "ia": ["#inteligenciaartificial", "#ia", "#ai"],
    "infraestrutura": ["#devops", "#cloud", "#infraestrutura"],
    "seguranca": ["#ciberseguranca", "#seguranca", "#infosec"],
    "mercado": ["#carreiratech", "#mercadotech", "#tecnologia"],
}
BOILER = re.compile(r"(?i)(cookie|subscribe|newsletter|sign up|inscreva|all rights reserved|©|share this|compartilhe)")


def _key_sentences(doc: SourceDoc, n: int = 3) -> list[str]:
    """Escolhe as frases mais ligadas ao título (mantendo a ordem original do texto)."""
    title = set(title_tokens(doc.title))
    ranked = []
    for pos, s in enumerate(dict.fromkeys(sentences(doc.text))):
        if BOILER.search(s) or len(s) > 320 or len(s) < 40:
            continue
        overlap = len(title & set(title_tokens(s))) / (len(title) or 1)
        ranked.append((overlap + max(0.0, 0.3 - pos * 0.02), pos, s))
    best = sorted(ranked, reverse=True)[:n]
    return [s for _, _, s in sorted(best, key=lambda r: r[1])] if best else []


def _central(quotes: list[str], title: str) -> str:
    t = set(title_tokens(title))
    return max(quotes, key=lambda q: len(t & set(title_tokens(q))))


def build(docs: list[SourceDoc], assets: list[AssetCandidate], category: str, news_title: str):
    main = docs[0]
    quotes = _key_sentences(main) or [truncate(main.text, 280)]
    while len(quotes) < 3:
        quotes.append(quotes[-1])
    label = CATEGORY_LABEL.get(category, "tecnologia")
    shot = next((a for a in assets if a.kind == "page_screenshot"), None)
    card = next((a for a in assets if a.kind == "to_produce"), None)
    lang_note = " (trecho no idioma original — traduza ao gravar)" if main.item.language != "pt" else ""
    scenes = [
        Scene(start_second=0, end_second=5, section="gancho",
              speech=f"Novidade em {label}: {news_title}.",
              action="Fale direto para a câmera, enquadramento fechado.",
              on_screen="Apresentador", overlay_text=truncate(news_title, 60),
              editing_notes="Corte rápido, legenda dinâmica.", visual_resource=card.ref if card else "PRODUZIR"),
        Scene(start_second=5, end_second=15, section="contexto",
              speech=f"Segundo {main.publisher}, a publicação diz: “{quotes[0]}”{lang_note}",
              action="Mostre a página da fonte.", on_screen=f"Página {main.url}",
              overlay_text=f"Fonte: {main.publisher}", editing_notes="Destaque o trecho citado com marca-texto.",
              visual_resource=shot.ref if shot else "PRODUZIR"),
        Scene(start_second=15, end_second=30, section="novidade",
              speech=f"O ponto principal: “{quotes[1]}”{lang_note}",
              action="Role a página até o trecho.", on_screen="Trecho da fonte ampliado",
              overlay_text="O que mudou", editing_notes="Zoom no parágrafo.", visual_resource=shot.ref if shot else "PRODUZIR"),
        Scene(start_second=30, end_second=42, section="detalhe",
              speech=f"E tem mais: “{quotes[2]}”{lang_note}",
              action="Continue na fonte ou volte para a câmera.", on_screen="Trecho da fonte",
              overlay_text="Detalhe", editing_notes="Alterne câmera/tela a cada frase.", visual_resource=shot.ref if shot else "PRODUZIR"),
        Scene(start_second=42, end_second=52, section="impacto",
              speech="[Apresentador: complete com sua análise do impacto para desenvolvedores — o roteiro-base não gera interpretação sem IA.]",
              action="Fale para a câmera.", on_screen="Apresentador", overlay_text="Impacto para devs",
              editing_notes="Revise antes de gravar.", visual_resource=card.ref if card else "PRODUZIR"),
        Scene(start_second=52, end_second=58, section="encerramento",
              speech="O link da fonte está na legenda. Você já conhecia? Comenta aqui.",
              action="Encerramento para a câmera.", on_screen="Apresentador",
              overlay_text="Fonte na legenda", editing_notes="Tela final com @ do perfil.", visual_resource="PRODUZIR"),
    ]
    planning = Planning(
        objective="Informar a novidade com base na fonte original (roteiro-base para adaptação).",
        audience="Estudantes e profissionais de tecnologia", technical_level="intermediario",
        duration_seconds=58, format="noticia_rapida",
        hook=f"Novidade em {label}: {truncate(news_title, 90)}",
        key_message=truncate(_central(quotes, news_title), 200),
    )
    guide = RecordingGuide(
        on_camera=["Gancho (0–5s)", "Impacto (42–52s)", "Encerramento (52–58s)"],
        screen_capture=["Contexto e novidade (5–42s): página da fonte"],
        pages_to_open=[d.url for d in docs],
        steps=["Abra a página da fonte", "Localize os trechos citados no roteiro", "Grave a rolagem até cada trecho"],
        highlights=[truncate(q, 120) for q in quotes[:3]],
        zoom_in=["Título e data da publicação", "Trechos citados"],
        alternation="Câmera no gancho, tela nos trechos, câmera no impacto e no encerramento.",
        proof_on_screen=["Domínio da fonte visível na barra de endereço", "Data de publicação visível"],
        prerequisites=[], commands=[], demo_status="sem_demonstracao",
        demo_note="Nenhuma demonstração foi executada pelo sistema.",
    )
    tags = HASHTAGS.get(category, ["#tecnologia"]) + ["#tecnologia", "#devpulse"]
    publication = Publication(
        caption=f"{news_title}\n\nResumo com base em {main.publisher}. Fonte completa: {main.url}",
        cover_title=truncate(news_title, 50), call_to_action="Comenta o que você achou e salva para ler a fonte depois.",
        hashtags=list(dict.fromkeys(tags)),
        pinned_comment=f"Fonte: {main.url}",
        caption_references=[f"{d.publisher}: {d.url}" for d in docs],
        materials=["Celular/câmera", "Navegador com a página da fonte aberta", "Gravador de tela"],
        final_checklist=[
            "Traduzir e adaptar os trechos citados",
            "Escrever a análise de impacto",
            "Conferir data e fonte na tela",
            "Conferir licença de qualquer imagem de terceiros",
        ],
    )
    central = _central(quotes, news_title)
    claims = [
        Claim(text=q, claim_type="fact", is_central=q == central, source_ref=main.ref, quote=q)
        for q in dict.fromkeys(quotes)
    ]
    uncertainties = ["Roteiro-base extrativo: a análise de impacto não foi gerada automaticamente."]
    return truncate(news_title, 90), planning, scenes, guide, publication, claims, uncertainties
