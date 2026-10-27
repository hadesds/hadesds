"""Exportação do pacote editorial em Markdown."""
from __future__ import annotations

from devpulse.script_generation.schema import ScriptPackage

FORMAT = {"noticia_rapida": "Notícia rápida", "explicacao": "Explicação", "tutorial": "Tutorial",
          "demonstracao": "Demonstração", "analise": "Análise fundamentada"}
DEMO = {"nao_executada": "Demonstração NÃO executada pelo sistema — reproduzir antes de gravar",
        "executada": "Demonstração executada", "sem_demonstracao": "Sem demonstração"}
RESULT = {"supported": "✅ sustentada", "partially_supported": "⚠️ parcialmente sustentada",
          "unsupported": "❌ não sustentada", "unverifiable": "❔ não verificável"}


def _cell(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", "<br>")


def _list(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- —"


def to_markdown(p: ScriptPackage) -> str:
    i, pl, g, pub = p.identification, p.planning, p.recording_guide, p.publication
    out = [f"# {i.video_title}", ""]
    if p.generator == "extractive":
        out += ["> **Roteiro-base extrativo (gerado sem IA).** Trechos citados no idioma original; "
                "traduza, adapte e complete a análise antes de gravar.", ""]
    out += [
        "## 1. Identificação", "",
        f"- **Notícia:** {i.news_title}",
        f"- **Título sugerido para o vídeo:** {i.video_title}",
        f"- **Categoria:** {i.category}",
        f"- **Publicação original:** {i.published_at or 'não informada pela fonte'}",
        f"- **Última verificação:** {i.last_verified_at}",
        f"- **Pontuação editorial:** {i.editorial_score:.0f}/100",
        f"- **Motivo da seleção:** {i.selection_reason}",
        "- **Fontes principais:**",
        *[f"  - [{s.ref}] [{s.title}]({s.url}) — {s.publisher} ({s.evidence_type})" for s in i.primary_sources],
    ]
    if i.complementary_sources:
        out += ["- **Fontes complementares:**",
                *[f"  - [{s.ref}] [{s.title}]({s.url}) — {s.publisher} ({s.evidence_type})" for s in i.complementary_sources]]
    out += [
        "", "## 2. Planejamento", "",
        f"- **Objetivo:** {pl.objective}", f"- **Público-alvo:** {pl.audience}",
        f"- **Nível técnico:** {pl.technical_level}", f"- **Duração estimada:** {pl.duration_seconds}s",
        f"- **Formato:** {FORMAT.get(pl.format, pl.format)}", f"- **Gancho:** {pl.hook}",
        f"- **Mensagem principal:** {pl.key_message}",
        "", "## 3. Roteiro cronometrado", "",
        "| Tempo | Fala | Ação/cena | Na tela | Texto sobreposto | Edição | Recurso |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in p.scenes:
        out.append(
            f"| {s.start_second}–{s.end_second}s ({_cell(s.section)}) | {_cell(s.speech)} | {_cell(s.action)} | "
            f"{_cell(s.on_screen)} | {_cell(s.overlay_text)} | {_cell(s.editing_notes)} | {_cell(s.visual_resource)} |"
        )
    out += [
        "", "## 4. Guia de gravação", "",
        "**Diante da câmera:**", _list(g.on_camera), "", "**Captura de tela:**", _list(g.screen_capture), "",
        "**Páginas/ferramentas a abrir:**", _list(g.pages_to_open), "", "**Passos:**", _list(g.steps), "",
        "**O que destacar:**", _list(g.highlights), "", "**Trechos para ampliar:**", _list(g.zoom_in), "",
        f"**Alternância fala/demonstração:** {g.alternation}", "",
        "**Informações visíveis para comprovar a afirmação:**", _list(g.proof_on_screen), "",
        "**Pré-requisitos:**", _list(g.prerequisites), "",
    ]
    if g.commands:
        out += ["**Comandos:**", "```bash", *g.commands, "```", ""]
    out += [f"**Status da demonstração:** {DEMO.get(g.demo_status, g.demo_status)}. {g.demo_note}", "",
            "## 5. Recursos visuais", "", "| Cena | Tipo | Descrição | Link | Origem | Licença/condições | Acessível |",
            "|---|---|---|---|---|---|---|"]
    for v in p.visual_resources:
        acc = "sim" if v.accessible else "não" if v.accessible is False else "não verificado"
        out.append(f"| {v.scene if v.scene is not None else '—'} | {v.kind} | {_cell(v.description)} | "
                   f"{v.url or '—'} | {v.source_page_url or '—'} | {_cell(v.license_info)} | {acc} |")
    out += [
        "", "## 6. Pacote de publicação", "", f"**Título de capa:** {pub.cover_title}", "",
        "**Legenda:**", "", pub.caption, "", f"**Chamada para interação:** {pub.call_to_action}", "",
        f"**Hashtags:** {' '.join(pub.hashtags)}", "", f"**Comentário fixado:** {pub.pinned_comment}", "",
        "**Referências para a legenda:**", _list(pub.caption_references), "",
        "**Materiais para gravar:**", _list(pub.materials), "", "**Checklist final:**",
        "\n".join(f"- [ ] {c}" for c in pub.final_checklist), "",
        "## 7. Registro de checagem", "",
        "| Afirmação | Tipo | Central | Fonte | Evidência | Resultado | Observações |", "|---|---|---|---|---|---|---|",
    ]
    for fc in p.fact_check_log:
        out.append(f"| {_cell(fc['claim'])} | {fc['claim_type']} | {'sim' if fc['is_central'] else 'não'} | "
                   f"{fc.get('source_url') or '—'} | {fc['evidence_type']} | {RESULT.get(fc['result'], fc['result'])} | {_cell(fc['notes'])} |")
    if p.uncertainties:
        out += ["", "**Incertezas e limitações:**", _list(p.uncertainties)]
    if p.generator_notes:
        out += ["", "**Notas do gerador:**", _list(p.generator_notes)]
    out += ["", f"_Gerado por DevPulse AI ({p.generator}). Revise antes de publicar._", ""]
    return "\n".join(out)
