"""Estrutura do pacote editorial de cada roteiro."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VideoFormat = Literal["noticia_rapida", "explicacao", "tutorial", "demonstracao", "analise"]
ClaimType = Literal["fact", "opinion", "forecast", "rumor"]


class SourceLink(BaseModel):
    ref: str  # S1, S2...
    title: str
    url: str
    publisher: str
    evidence_type: str
    published_at: str | None = None


class Identification(BaseModel):
    news_title: str
    video_title: str
    category: str
    published_at: str | None
    last_verified_at: str
    editorial_score: float
    selection_reason: str
    primary_sources: list[SourceLink]
    complementary_sources: list[SourceLink] = Field(default_factory=list)


class Planning(BaseModel):
    objective: str
    audience: str
    technical_level: Literal["iniciante", "intermediario", "avancado"]
    duration_seconds: int
    format: VideoFormat
    hook: str
    key_message: str


class Scene(BaseModel):
    start_second: int
    end_second: int
    section: str
    speech: str
    action: str
    on_screen: str
    overlay_text: str
    editing_notes: str
    visual_resource: str


class RecordingGuide(BaseModel):
    on_camera: list[str]
    screen_capture: list[str]
    pages_to_open: list[str]
    steps: list[str]
    highlights: list[str]
    zoom_in: list[str]
    alternation: str
    proof_on_screen: list[str]
    prerequisites: list[str]
    commands: list[str]
    demo_status: Literal["nao_executada", "executada", "sem_demonstracao"]
    demo_note: str


class VisualResource(BaseModel):
    scene: int | None
    kind: str
    description: str
    url: str | None = None
    source_page_url: str | None = None
    license_info: str = "Desconhecida — verificar termos de uso do site"
    accessible: bool | None = None


class Publication(BaseModel):
    caption: str
    cover_title: str
    call_to_action: str
    hashtags: list[str]
    pinned_comment: str
    caption_references: list[str]
    materials: list[str]
    final_checklist: list[str]


class Claim(BaseModel):
    text: str
    claim_type: ClaimType
    is_central: bool
    source_ref: str
    quote: str


class ScriptPackage(BaseModel):
    identification: Identification
    planning: Planning
    scenes: list[Scene]
    recording_guide: RecordingGuide
    visual_resources: list[VisualResource]
    publication: Publication
    claims: list[Claim]
    uncertainties: list[str]
    generator: str
    generator_notes: list[str] = Field(default_factory=list)
    fact_check_log: list[dict[str, Any]] = Field(default_factory=list)


class LlmDraft(BaseModel):
    """O que o modelo de linguagem preenche. Links e fontes vêm do sistema."""

    video_title: str
    planning: Planning
    scenes: list[Scene]
    recording_guide: RecordingGuide
    scene_visuals: list[VisualPick]
    publication: Publication
    claims: list[Claim]
    uncertainties: list[str]


class VisualPick(BaseModel):
    scene_index: int
    asset_ref: str  # A1, A2... ou "PRODUZIR"
    description: str


LlmDraft.model_rebuild()


def strict_schema(model: type[BaseModel]) -> dict:
    """JSON Schema compatível com saídas estruturadas (todos os campos obrigatórios)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return fix(defs[node["$ref"].split("/")[-1]])
            node = {k: fix(v) for k, v in node.items() if k not in ("title", "default", "description")}
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            return node
        if isinstance(node, list):
            return [fix(n) for n in node]
        return node

    return fix(schema)
