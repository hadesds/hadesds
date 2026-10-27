"""Refinamento opcional da pontuação com um modelo econômico."""
from __future__ import annotations

import logging

from devpulse.editorial_scoring.scorer import WEIGHTS, ClusterScore
from devpulse.script_generation.llm import LlmClient, LlmError, LlmUnavailable
from devpulse.script_generation.prompts import SCORING_SYSTEM
from devpulse.settings_service import EditableSettings

log = logging.getLogger(__name__)
FIELDS = ["utilidade_pratica", "potencial_visual", "interesse_publico", "explicabilidade"]
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["avaliacoes"],
    "properties": {
        "avaliacoes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", *FIELDS, "justificativa"],
                "properties": {"id": {"type": "integer"}, **{f: {"type": "integer"} for f in FIELDS}, "justificativa": {"type": "string"}},
            },
        }
    },
}


def make_refiner(llm: LlmClient, cfg: EditableSettings):
    def refine(scores: list[ClusterScore]) -> None:
        if not scores:
            return
        listing = "\n".join(
            f"id={cs.cluster.id} | categoria={cs.category} | título={cs.representative.title} | resumo={(cs.representative.summary or '')[:400]}"
            for cs in scores
        )
        try:
            res = llm.generate_json(system=SCORING_SYSTEM, user=f"Avalie cada notícia:\n{listing}", schema=SCHEMA,
                                    model=cfg.llm_model_fast, max_tokens=4000, purpose="scoring", effort="low")
        except (LlmError, LlmUnavailable) as e:
            log.warning("Refinamento por IA ignorado: %s", e)
            return
        by_id = {int(a["id"]): a for a in res.data.get("avaliacoes", [])}
        for cs in scores:
            a = by_id.get(cs.cluster.id)
            if not a:
                continue
            for f in FIELDS:
                cs.components[f] = round(0.5 * cs.components[f] + 0.5 * max(0, min(100, int(a[f]))), 1)
            cs.total = round(sum(cs.components[k] * w for k, w in WEIGHTS.items()), 1)
            cs.method = "heuristic+llm"
            cs.rationale = str(a.get("justificativa", ""))[:500]

    return refine
