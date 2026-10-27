"""Gera, checa e persiste o pacote editorial de uma notícia selecionada."""
from __future__ import annotations

import logging
import re
from datetime import date

import httpx
from sqlalchemy.orm import Session

from devpulse.editorial_scoring.scorer import ClusterScore
from devpulse.editorial_scoring.selection import selection_reason
from devpulse.fact_checking.checker import CheckReport, check_package
from devpulse.media_research.research import AssetCandidate, research
from devpulse.models import FactCheck, MediaAsset, Script, ScriptScene
from devpulse.script_generation import fallback, prompts
from devpulse.script_generation.llm import LlmClient, LlmError, LlmUnavailable
from devpulse.script_generation.render import to_markdown
from devpulse.script_generation.schema import (
    Identification,
    LlmDraft,
    ScriptPackage,
    SourceLink,
    VisualResource,
    strict_schema,
)
from devpulse.script_generation.sources import SourceDoc, build_docs
from devpulse.settings_service import EditableSettings
from devpulse.timeutil import local_now

log = logging.getLogger(__name__)
URL = re.compile(r"https?://[^\s)\]>\"']+")
DRAFT_SCHEMA = strict_schema(LlmDraft)


def strip_unknown_urls(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    removed = []

    def repl(m: re.Match) -> str:
        url = m.group(0).rstrip(".,;")
        if url in allowed:
            return m.group(0)
        removed.append(url)
        return "[link removido: não consta nas fontes]"

    return URL.sub(repl, text or ""), removed


def _sanitize_draft(draft: LlmDraft, allowed: set[str]) -> list[str]:
    notes: list[str] = []
    removed_all: list[str] = []
    for s in draft.scenes:
        for f in ("speech", "action", "on_screen", "overlay_text", "editing_notes", "visual_resource"):
            new, removed = strip_unknown_urls(getattr(s, f), allowed)
            setattr(s, f, new)
            removed_all += removed
    draft.recording_guide.pages_to_open = [u for u in draft.recording_guide.pages_to_open if u in allowed]
    pub = draft.publication
    pub.caption, r1 = strip_unknown_urls(pub.caption, allowed)
    pub.pinned_comment, r2 = strip_unknown_urls(pub.pinned_comment, allowed)
    removed_all += r1 + r2
    pub.caption_references = [strip_unknown_urls(r, allowed)[0] for r in pub.caption_references]
    if removed_all:
        notes.append(f"{len(removed_all)} link(s) gerados pela IA e ausentes das fontes foram removidos")
    # linha do tempo contínua e duração entre 30 e 90s
    draft.scenes.sort(key=lambda s: s.start_second)
    t = 0
    for s in draft.scenes:
        length = max(2, s.end_second - s.start_second)
        s.start_second, s.end_second = t, t + length
        t += length
    if draft.scenes and not 30 <= t <= 90:
        factor = min(90, max(30, t)) / t
        t2 = 0
        for s in draft.scenes:
            length = max(2, round((s.end_second - s.start_second) * factor))
            s.start_second, s.end_second = t2, t2 + length
            t2 += length
        t = t2
        notes.append("Tempos das cenas ajustados para a faixa de 30–90s")
    draft.planning.duration_seconds = t
    if draft.recording_guide.demo_status == "executada":
        draft.recording_guide.demo_status = "nao_executada"
        notes.append("Demonstração marcada como executada pela IA foi corrigida: o sistema não executa testes")
    return notes


def _llm_draft(llm: LlmClient, cfg: EditableSettings, user: str) -> LlmDraft:
    result = llm.generate_json(
        system=prompts.SYSTEM, user=user, schema=DRAFT_SCHEMA, model=cfg.llm_model_script,
        max_tokens=16000, purpose="script", effort="high",
    )
    return LlmDraft.model_validate(result.data)


def _visuals(picks, assets: list[AssetCandidate]) -> list[VisualResource]:
    by_ref = {a.ref: a for a in assets}
    used: set[str] = set()
    out: list[VisualResource] = []
    for p in picks:
        a = by_ref.get(p.asset_ref)
        if a:
            used.add(a.ref)
            out.append(VisualResource(scene=p.scene_index, kind=a.kind, description=f"{p.description} — {a.description}",
                                      url=a.url, source_page_url=a.source_page_url, license_info=a.license_info, accessible=a.accessible))
        else:
            out.append(VisualResource(scene=p.scene_index, kind="to_produce", description=p.description, license_info="Material original a produzir"))
    for a in assets:
        if a.ref not in used:
            out.append(VisualResource(scene=None, kind=a.kind, description=a.description, url=a.url,
                                      source_page_url=a.source_page_url, license_info=a.license_info, accessible=a.accessible))
    return out


def _fallback_visuals(scenes, assets: list[AssetCandidate]) -> list:
    from devpulse.script_generation.schema import VisualPick

    return [VisualPick(scene_index=i, asset_ref=s.visual_resource, description=s.on_screen) for i, s in enumerate(scenes, start=1)]


def produce_package(session: Session, cs: ClusterScore, cfg: EditableSettings, llm: LlmClient | None, http: httpx.Client | None) -> tuple[ScriptPackage, CheckReport]:
    docs: list[SourceDoc] = build_docs(session, cs.representative, cs.evidence)
    if not docs:
        raise ValueError("Sem documentos-fonte acessíveis")
    assets = research(docs, http, verify=http is not None)
    allowed = {d.url for d in docs} | {a.url for a in assets if a.url}
    notes: list[str] = []
    newsletter_note = (
        f"A notícia também foi citada em {cs.evidence.newsletter_mentions} newsletter(s) monitorada(s)."
        if cs.evidence.newsletter_mentions else ""
    )
    generator = "extractive"
    draft = None
    report: CheckReport | None = None
    if llm is not None:
        user = prompts.user_prompt(today=local_now().date().isoformat(), category=cs.category, docs=docs, assets=assets, newsletter_note=newsletter_note)
        try:
            draft = _llm_draft(llm, cfg, user)
            notes += _sanitize_draft(draft, allowed)
            report = check_package(draft.claims, draft.scenes, docs, http)
            if report.status == "rejected" or report.unsupported_numbers:
                notes.append("Primeira versão reprovada na checagem; IA solicitada a revisar")
                draft = _llm_draft(llm, cfg, prompts.revision_prompt(user, draft.model_dump(), report.problems))
                notes += _sanitize_draft(draft, allowed)
                report = check_package(draft.claims, draft.scenes, docs, http)
            if report.status == "rejected":
                notes.append("Versão da IA reprovada duas vezes na checagem; usado roteiro-base extrativo")
                draft = None
            else:
                generator = f"llm:{llm.provider}:{cfg.llm_model_script}"
        except (LlmError, LlmUnavailable, ValueError) as e:
            notes.append(f"IA indisponível para este roteiro ({e}); usado roteiro-base extrativo")
            draft = None
    if draft is None:
        title, planning, scenes, guide, publication, claims, uncertainties = fallback.build(docs, assets, cs.category, cs.representative.title)
        report = check_package(claims, scenes, docs, http)
        picks = _fallback_visuals(scenes, assets)
        video_title = title
    else:
        planning, scenes, guide, publication, claims, uncertainties = (
            draft.planning, draft.scenes, draft.recording_guide, draft.publication, draft.claims, draft.uncertainties
        )
        picks, video_title = draft.scene_visuals, draft.video_title
    assert report is not None

    def link(d: SourceDoc) -> SourceLink:
        return SourceLink(ref=d.ref, title=d.title, url=d.url, publisher=d.publisher, evidence_type=d.evidence_type, published_at=d.published_at)

    primary = [link(d) for d in docs if d.tier <= 2] or [link(docs[0])]
    complementary = [link(d) for d in docs if link(d) not in primary]
    published = cs.cluster.first_published_at or cs.representative.published_at
    checklist = list(publication.final_checklist)
    checklist += [p for p in report.problems][:10]
    checklist += ["Conferir se os links da legenda abrem", "Confirmar licença das imagens de terceiros antes de usar"]
    publication.final_checklist = list(dict.fromkeys(checklist))
    log_rows = [
        {"claim": c.claim.text, "claim_type": c.claim.claim_type, "is_central": c.claim.is_central,
         "source_url": c.source_url, "evidence_type": c.evidence_type, "result": c.result, "notes": c.notes,
         "quote": c.claim.quote}
        for c in report.claims
    ]
    for lk in report.links:
        log_rows.append({"claim": f"Link da fonte acessível: {lk['url']}", "claim_type": "fact", "is_central": False,
                         "source_url": lk["url"], "evidence_type": "link_check",
                         "result": "supported" if lk["accessible"] else ("unverifiable" if lk["accessible"] is None else "unsupported"),
                         "notes": f"HTTP {lk.get('status')}" if lk.get("status") else "Não verificado", "quote": ""})
    for n in report.unsupported_numbers:
        uncertainties = [*uncertainties, f"O número/versão '{n}' citado nas falas não foi encontrado nas fontes"]
    uncertainties = list(dict.fromkeys([*uncertainties, *cs.evidence.notes]))
    pkg = ScriptPackage(
        identification=Identification(
            news_title=cs.representative.title, video_title=video_title, category=cs.category,
            published_at=published.isoformat() if published else None,
            last_verified_at=local_now().isoformat(timespec="minutes"), editorial_score=cs.total,
            selection_reason=selection_reason(cs), primary_sources=primary, complementary_sources=complementary,
        ),
        planning=planning, scenes=scenes, recording_guide=guide, visual_resources=_visuals(picks, assets),
        publication=publication, claims=claims, uncertainties=uncertainties, generator=generator,
        generator_notes=notes, fact_check_log=log_rows,
    )
    return pkg, report


def persist_script(session: Session, pkg: ScriptPackage, report: CheckReport, cs: ClusterScore, run_id: str | None, edition_date: date, position: int) -> Script:
    status = "rejected" if report.status == "rejected" else "verified"
    script = Script(
        scheduled_run_id=run_id, cluster_id=cs.cluster.id, news_item_id=cs.representative.id,
        edition_date=edition_date, position=position, status=status, news_title=pkg.identification.news_title,
        video_title=pkg.identification.video_title, category=cs.category, editorial_score=cs.total,
        selection_reason=pkg.identification.selection_reason, estimated_duration_seconds=pkg.planning.duration_seconds,
        generator=pkg.generator, package=pkg.model_dump(mode="json"), markdown=to_markdown(pkg),
        verification_summary={"status": report.status, "problems": report.problems[:30],
                              "unsupported_numbers": report.unsupported_numbers},
        rejection_reason="; ".join(report.problems[:5]) if status == "rejected" else None,
    )
    for n, s in enumerate(pkg.scenes, start=1):
        script.scenes.append(ScriptScene(order=n, section=s.section, start_second=s.start_second, end_second=s.end_second,
                                         speech=s.speech, action=s.action, on_screen=s.on_screen, overlay_text=s.overlay_text,
                                         editing_notes=s.editing_notes, visual_resource=s.visual_resource))
    for row in pkg.fact_check_log:
        script.fact_checks.append(FactCheck(claim=row["claim"], claim_type=row["claim_type"], is_central=row["is_central"],
                                            source_url=row["source_url"], evidence_quote=row.get("quote") or None,
                                            evidence_type=row["evidence_type"], result=row["result"], notes=row["notes"]))
    for v in pkg.visual_resources:
        script.media_assets.append(MediaAsset(scene_order=v.scene, kind=v.kind, url=v.url, source_page_url=v.source_page_url,
                                              description=v.description, license_info=v.license_info, accessible=v.accessible))
    session.add(script)
    if status != "rejected":
        cs.cluster.last_selected_on = edition_date
        cs.representative.verification_status = (
            "primary_confirmed" if cs.evidence.best_tier <= 2 else "independently_confirmed"
        )
    session.flush()
    return script


def render_markdown(script: Script) -> str:
    return to_markdown(ScriptPackage.model_validate(script.package))
