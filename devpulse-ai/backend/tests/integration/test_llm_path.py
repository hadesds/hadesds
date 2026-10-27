import pytest
from sqlalchemy import func, select

from devpulse.models import LlmUsage
from devpulse.script_generation import generator
from devpulse.script_generation.llm import LlmBudgetExceeded, LlmClient, LlmResult
from devpulse.settings_service import load, save
from devpulse.editorial_scoring.selection import score_candidates

from .conftest import add_story, make_source

pytestmark = pytest.mark.integration


def draft(quote, number="25%"):
    return {
        "video_title": "Example 2.0 chegou",
        "planning": {"objective": "o", "audience": "devs", "technical_level": "intermediario", "duration_seconds": 45,
                     "format": "noticia_rapida", "hook": "h", "key_message": "k"},
        "scenes": [{"start_second": 0, "end_second": 45, "section": "gancho", "speech": f"A API ficou {number} mais rápida. Veja https://inventado.example/x",
                    "action": "", "on_screen": "", "overlay_text": "", "editing_notes": "", "visual_resource": "A1"}],
        "recording_guide": {"on_camera": [], "screen_capture": [], "pages_to_open": [], "steps": [], "highlights": [], "zoom_in": [],
                            "alternation": "", "proof_on_screen": [], "prerequisites": [], "commands": [], "demo_status": "nao_executada", "demo_note": "reproduzir"},
        "scene_visuals": [{"scene_index": 1, "asset_ref": "A1", "description": "página"}],
        "publication": {"caption": "c", "cover_title": "c", "call_to_action": "c", "hashtags": ["#dev"], "pinned_comment": "p",
                        "caption_references": [], "materials": [], "final_checklist": []},
        "claims": [{"text": f"A API ficou {number} mais rápida", "claim_type": "fact", "is_central": True, "source_ref": "S1", "quote": quote}],
        "uncertainties": [],
    }


class FakeLlm(LlmClient):
    provider = "fake"

    def __init__(self, session, cfg, responses):
        super().__init__(session, cfg)
        self.responses = list(responses)
        self.prompts = []

    def _call(self, *, system, user, schema, model, max_tokens, effort):
        self.prompts.append(user)
        return LlmResult(self.responses.pop(0), 1000, 500, model, "req_fake")


def _candidate(db):
    src = make_source(db, "oficial", tier=1, category="desenvolvimento")
    add_story(db, src, "Example 2.0 released with new CLI", "https://oficial.example.com/blog/example-2")
    cfg = load(db)
    return cfg, [s for s in score_candidates(db, cfg) if s.eligible][0]


def test_llm_draft_is_checked_and_links_sanitized(db):
    cfg, cs = _candidate(db)
    good = "improves performance of the API by 25% in our benchmarks"
    llm = FakeLlm(db, cfg, [draft(good)])
    pkg, report = generator.produce_package(db, cs, cfg, llm, http=None)
    assert pkg.generator.startswith("llm:fake")
    assert report.status in ("verified", "verified_with_warnings") and report.central_ok
    assert "inventado" not in pkg.scenes[0].speech
    assert db.scalar(select(func.count(LlmUsage.id))) == 1


def test_unsupported_llm_claim_triggers_revision_then_fallback(db):
    cfg, cs = _candidate(db)
    bad = draft("the API is now 90% faster than any competitor", number="90%")
    llm = FakeLlm(db, cfg, [bad, bad])
    pkg, report = generator.produce_package(db, cs, cfg, llm, http=None)
    assert len(llm.prompts) == 2 and "PROBLEMAS" in llm.prompts[1]
    assert pkg.generator == "extractive"  # nunca entrega a versão sem sustentação
    assert "90" not in " ".join(s.speech for s in pkg.scenes)


def test_daily_llm_budget_is_enforced(db):
    save(db, {"llm_max_calls_per_day": 1})
    cfg, cs = _candidate(db)
    good = "improves performance of the API by 25% in our benchmarks"
    llm = FakeLlm(db, cfg, [draft(good), draft(good)])
    llm.generate_json(system="s", user="u", schema={}, model="m", max_tokens=10, purpose="t")
    with pytest.raises(LlmBudgetExceeded):
        llm.generate_json(system="s", user="u", schema={}, model="m", max_tokens=10, purpose="t")
    pkg, _ = generator.produce_package(db, cs, cfg, llm, http=None)
    assert pkg.generator == "extractive" and any("Limite diário" in n for n in pkg.generator_notes)
