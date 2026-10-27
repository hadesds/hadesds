from datetime import datetime, timezone
from types import SimpleNamespace

from devpulse.fact_checking.checker import check_package, quote_support, significant_numbers
from devpulse.media_research.research import AssetCandidate
from devpulse.script_generation import fallback
from devpulse.script_generation.generator import _sanitize_draft, strip_unknown_urls
from devpulse.script_generation.render import to_markdown
from devpulse.script_generation.schema import Claim, LlmDraft, Scene, strict_schema
from devpulse.script_generation.sources import SourceDoc

TEXT = (
    "Today the Example team released Example Framework 5.0. The new version reduces build times by 40% on large projects. "
    "It also adds a new CLI command called example doctor. Version 5.0 requires Node.js 22 or later."
)


def doc(text=TEXT, tier=1):
    item = SimpleNamespace(language="en", raw={}, id=1)
    return SourceDoc(ref="S1", item=item, url="https://example.dev/blog/v5", title="Example Framework 5.0 released",
                     publisher="example.dev", tier=tier, evidence_type="primary_source", published_at=None, text=text)


def scene(speech, start=0, end=10):
    return Scene(start_second=start, end_second=end, section="x", speech=speech, action="", on_screen="",
                 overlay_text="", editing_notes="", visual_resource="")


def test_quote_support_exact_and_missing():
    assert quote_support("reduces build times by 40% on large projects", TEXT) == 1.0
    assert quote_support("adds GPU acceleration for every platform", TEXT) < 0.6


def test_numbers_extraction():
    assert significant_numbers("versão 5.0 com 40% mais rápido em 3 passos") == {"5.0", "40"}


def test_supported_claim_passes():
    claims = [Claim(text="O build ficou 40% mais rápido", claim_type="fact", is_central=True, source_ref="S1",
                    quote="The new version reduces build times by 40% on large projects.")]
    report = check_package(claims, [scene("A versão 5.0 deixa o build 40% mais rápido.")], [doc()], http=None)
    assert report.status == "verified"
    assert report.claims[0].result == "supported"


def test_invented_number_and_quote_are_flagged():
    claims = [Claim(text="O build ficou 70% mais rápido", claim_type="fact", is_central=True, source_ref="S1",
                    quote="Builds are now 70% faster.")]
    report = check_package(claims, [scene("Agora com 70% de ganho e suporte ao Python 3.14.")], [doc()], http=None)
    assert report.status == "rejected"
    assert {"70", "3.14"} <= set(report.unsupported_numbers)


def test_claim_without_valid_source_is_unverifiable():
    claims = [Claim(text="x", claim_type="fact", is_central=True, source_ref="S9", quote="x")]
    report = check_package(claims, [], [doc()], http=None)
    assert report.claims[0].result == "unverifiable"
    assert report.status == "rejected"


def test_fallback_builds_complete_package_from_source_only():
    assets = [AssetCandidate("A1", "page_screenshot", "Página", "https://example.dev/blog/v5", "https://example.dev/blog/v5", "x"),
              AssetCandidate("A2", "to_produce", "Card", None, None, "original")]
    title, planning, scenes, guide, pub, claims, unc = fallback.build([doc()], assets, "desenvolvimento", "Example Framework 5.0 released")
    assert 30 <= planning.duration_seconds <= 90
    assert all(s.speech and s.visual_resource for s in scenes)
    assert sum(c.is_central for c in claims) == 1
    report = check_package(claims, scenes, [doc()], http=None)
    assert report.central_ok and report.status in ("verified", "verified_with_warnings")
    assert guide.demo_status == "sem_demonstracao"


def test_strict_schema_requires_all_fields():
    schema = strict_schema(LlmDraft)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    scene_schema = schema["properties"]["scenes"]["items"]
    assert scene_schema["additionalProperties"] is False


def test_unknown_urls_are_removed():
    text, removed = strip_unknown_urls("veja https://fake.example/x e https://example.dev/blog/v5.", {"https://example.dev/blog/v5"})
    assert removed == ["https://fake.example/x"]
    assert "https://example.dev/blog/v5" in text


def _draft(**over):
    base = {
        "video_title": "t",
        "planning": {"objective": "o", "audience": "a", "technical_level": "iniciante", "duration_seconds": 10,
                     "format": "explicacao", "hook": "h", "key_message": "k"},
        "scenes": [
            {"start_second": 5, "end_second": 15, "section": "b", "speech": "fonte https://inventado.dev", "action": "", "on_screen": "", "overlay_text": "", "editing_notes": "", "visual_resource": "A1"},
            {"start_second": 0, "end_second": 5, "section": "a", "speech": "oi", "action": "", "on_screen": "", "overlay_text": "", "editing_notes": "", "visual_resource": "A1"},
        ],
        "recording_guide": {"on_camera": [], "screen_capture": [], "pages_to_open": ["https://example.dev/blog/v5", "https://inventado.dev"],
                            "steps": [], "highlights": [], "zoom_in": [], "alternation": "", "proof_on_screen": [],
                            "prerequisites": [], "commands": [], "demo_status": "executada", "demo_note": ""},
        "scene_visuals": [],
        "publication": {"caption": "c", "cover_title": "c", "call_to_action": "c", "hashtags": [], "pinned_comment": "p",
                        "caption_references": [], "materials": [], "final_checklist": []},
        "claims": [], "uncertainties": [],
    }
    base.update(over)
    return LlmDraft.model_validate(base)


def test_sanitize_draft_fixes_links_timeline_and_demo_status():
    d = _draft()
    notes = _sanitize_draft(d, {"https://example.dev/blog/v5"})
    assert "inventado" not in d.scenes[1].speech
    assert d.recording_guide.pages_to_open == ["https://example.dev/blog/v5"]
    assert d.scenes[0].start_second == 0 and 30 <= d.planning.duration_seconds <= 90
    assert d.recording_guide.demo_status == "nao_executada"
    assert any("executada" in n for n in notes)


def test_markdown_render_contains_all_sections():
    from devpulse.script_generation.schema import Identification, ScriptPackage, SourceLink

    assets = [AssetCandidate("A1", "to_produce", "Card", None, None, "original")]
    title, planning, scenes, guide, pub, claims, unc = fallback.build([doc()], assets, "desenvolvimento", "Example 5.0")
    pkg = ScriptPackage(
        identification=Identification(news_title="Example 5.0", video_title=title, category="desenvolvimento", published_at=None,
                                      last_verified_at=datetime.now(timezone.utc).isoformat(), editorial_score=70,
                                      selection_reason="r", primary_sources=[SourceLink(ref="S1", title="t", url="https://example.dev", publisher="example.dev", evidence_type="primary_source")]),
        planning=planning, scenes=scenes, recording_guide=guide, visual_resources=[], publication=pub, claims=claims,
        uncertainties=unc, generator="extractive",
    )
    md = to_markdown(pkg)
    for section in ("## 1. Identificação", "## 2. Planejamento", "## 3. Roteiro cronometrado", "## 4. Guia de gravação",
                    "## 5. Recursos visuais", "## 6. Pacote de publicação", "## 7. Registro de checagem"):
        assert section in md
