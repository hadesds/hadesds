"""Modelo de dados (SQLAlchemy 2.0). Alterações exigem uma nova migração Alembic."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JsonType, list[Any]: JsonType}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    connector_type: Mapped[str] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    category: Mapped[str | None] = mapped_column(String(40))
    # 1 = anúncio oficial/documentação, 2 = repositório/changelog oficial, 3 = newsletter,
    # 4 = portal especializado, 5 = fonte independente/agregador
    priority_tier: Mapped[int] = mapped_column(Integer, default=4)
    reliability: Mapped[float] = mapped_column(Float, default=0.7)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    notes: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    runs: Mapped[list[SourceRun]] = relationship(back_populates="source", cascade="all, delete-orphan")


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    scheduled_run_id: Mapped[str | None] = mapped_column(ForeignKey("scheduled_runs.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|partial|failed
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)

    source: Mapped[Source] = relationship(back_populates="runs")


class NewsCluster(TimestampMixin, Base):
    """Agrupa matérias que tratam do mesmo acontecimento."""

    __tablename__ = "news_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title: Mapped[str] = mapped_column(Text)
    topic_key: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str | None] = mapped_column(String(40))
    first_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_count: Mapped[int] = mapped_column(Integer, default=1)
    last_selected_on: Mapped[date | None] = mapped_column(Date)

    items: Mapped[list[NewsItem]] = relationship(back_populates="cluster")


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("normalized_url", name="uq_news_items_normalized_url"),
        UniqueConstraint("source_id", "external_id", name="uq_news_items_source_external"),
        Index("ix_news_items_published_at", "published_at"),
        Index("ix_news_items_discovered_at", "discovered_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("news_clusters.id", ondelete="SET NULL"), index=True)
    external_id: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    title_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    # full | partial | summary_only | unavailable | restricted
    content_access: Mapped[str] = mapped_column(String(20), default="summary_only")
    content_hash: Mapped[str | None] = mapped_column(String(64))
    author: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at_inferred: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str | None] = mapped_column(String(10))
    category: Mapped[str | None] = mapped_column(String(40))
    content_type: Mapped[str] = mapped_column(String(20), default="fact")  # fact|opinion|forecast|rumor
    # unverified | source_only | primary_confirmed | independently_confirmed | insufficient
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified")
    extraction_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|done|failed|skipped
    extraction_error: Mapped[str | None] = mapped_column(Text)
    editorial_score: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)

    source: Mapped[Source] = relationship()
    cluster: Mapped[NewsCluster | None] = relationship(back_populates="items")
    references: Mapped[list[SourceReference]] = relationship(
        back_populates="news_item", cascade="all, delete-orphan"
    )


class SourceReference(Base):
    """Cada vez que uma fonte menciona/publica uma notícia já conhecida."""

    __tablename__ = "source_references"
    __table_args__ = (UniqueConstraint("news_item_id", "source_id", "url", name="uq_source_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    # origin | newsletter_mention | aggregator | republication
    reference_type: Mapped[str] = mapped_column(String(30), default="origin")
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    news_item: Mapped[NewsItem] = relationship(back_populates="references")
    source: Mapped[Source] = relationship()


class EditorialScore(Base):
    __tablename__ = "editorial_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id", ondelete="CASCADE"), index=True)
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"))
    scheduled_run_id: Mapped[str | None] = mapped_column(ForeignKey("scheduled_runs.id", ondelete="SET NULL"))
    total: Mapped[float] = mapped_column(Float)
    components: Mapped[dict[str, Any]] = mapped_column(default=dict)
    method: Mapped[str] = mapped_column(String(30), default="heuristic")
    rationale: Mapped[str | None] = mapped_column(Text)
    eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    ineligibility_reason: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScheduledRun(Base):
    """Execução agendada/manual/recuperada. ``run_key`` garante idempotência."""

    __tablename__ = "scheduled_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_key: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(20))  # collect | edition
    slot: Mapped[str | None] = mapped_column(String(20))  # main | secondary | manual
    edition_date: Mapped[date | None] = mapped_column(Date, index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="schedule")  # schedule|recovery|manual
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # pending | running | completed | failed | skipped
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    step: Mapped[str | None] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scripts: Mapped[list[Script]] = relationship(back_populates="scheduled_run")
    deliveries: Mapped[list[NotificationDelivery]] = relationship(back_populates="scheduled_run")


class Script(TimestampMixin, Base):
    __tablename__ = "scripts"
    __table_args__ = (
        UniqueConstraint("edition_date", "cluster_id", name="uq_scripts_edition_cluster"),
        Index("ix_scripts_edition_date", "edition_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scheduled_run_id: Mapped[str | None] = mapped_column(ForeignKey("scheduled_runs.id", ondelete="SET NULL"))
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id", ondelete="CASCADE"))
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"))
    edition_date: Mapped[date] = mapped_column(Date)
    position: Mapped[int] = mapped_column(Integer, default=1)
    # draft | verified | rejected | recorded | published
    status: Mapped[str] = mapped_column(String(20), default="draft")
    news_title: Mapped[str] = mapped_column(Text)
    video_title: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(40))
    editorial_score: Mapped[float | None] = mapped_column(Float)
    selection_reason: Mapped[str | None] = mapped_column(Text)
    estimated_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    generator: Mapped[str] = mapped_column(String(80))  # ex.: llm:anthropic:claude-opus-5-5 | extractive
    package: Mapped[dict[str, Any]] = mapped_column(default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")
    verification_summary: Mapped[dict[str, Any]] = mapped_column(default=dict)
    edited_manually: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    scheduled_run: Mapped[ScheduledRun | None] = relationship(back_populates="scripts")
    news_item: Mapped[NewsItem] = relationship()
    scenes: Mapped[list[ScriptScene]] = relationship(
        back_populates="script", cascade="all, delete-orphan", order_by="ScriptScene.order"
    )
    fact_checks: Mapped[list[FactCheck]] = relationship(back_populates="script", cascade="all, delete-orphan")
    media_assets: Mapped[list[MediaAsset]] = relationship(back_populates="script", cascade="all, delete-orphan")


class ScriptScene(Base):
    __tablename__ = "script_scenes"
    __table_args__ = (UniqueConstraint("script_id", "order", name="uq_scene_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id", ondelete="CASCADE"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(40))
    start_second: Mapped[int] = mapped_column(Integer)
    end_second: Mapped[int] = mapped_column(Integer)
    speech: Mapped[str] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    on_screen: Mapped[str | None] = mapped_column(Text)
    overlay_text: Mapped[str | None] = mapped_column(Text)
    editing_notes: Mapped[str | None] = mapped_column(Text)
    visual_resource: Mapped[str | None] = mapped_column(Text)

    script: Mapped[Script] = relationship(back_populates="scenes")


class FactCheck(Base):
    __tablename__ = "fact_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id", ondelete="CASCADE"), index=True)
    claim: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(20), default="fact")  # fact|opinion|forecast|rumor
    is_central: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    # primary_source | official_repository | newsletter | specialized_press | independent | none
    evidence_type: Mapped[str] = mapped_column(String(30))
    # supported | partially_supported | unsupported | unverifiable
    result: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    script: Mapped[Script] = relationship(back_populates="fact_checks")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id", ondelete="CASCADE"), index=True)
    scene_order: Mapped[int | None] = mapped_column(Integer)
    # page_screenshot | official_image | repository | documentation | code | chart | to_produce
    kind: Mapped[str] = mapped_column(String(30))
    url: Mapped[str | None] = mapped_column(Text)
    source_page_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    license_info: Mapped[str] = mapped_column(Text, default="Desconhecida — verificar termos de uso do site")
    accessible: Mapped[bool | None] = mapped_column(Boolean)

    script: Mapped[Script] = relationship(back_populates="media_assets")


class NotificationDelivery(Base):
    """Uma entrega por (execução, canal, destinatário). Estados independentes por canal."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_delivery_idempotency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scheduled_run_id: Mapped[str] = mapped_column(ForeignKey("scheduled_runs.id", ondelete="CASCADE"), index=True)
    edition_date: Mapped[date] = mapped_column(Date, index=True)
    channel: Mapped[str] = mapped_column(String(20))  # email | whatsapp
    recipient: Mapped[str] = mapped_column(String(320))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    # pending | sending | sent | retrying | failed | failed_auth | blocked | needs_review | disabled
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_message_id: Mapped[str | None] = mapped_column(String(300))
    provider_status: Mapped[str | None] = mapped_column(String(60))
    attempt_log: Mapped[list[Any]] = mapped_column(default=list)
    payload_summary: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    scheduled_run: Mapped[ScheduledRun] = relationship(back_populates="deliveries")


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JsonType)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LlmUsage(Base):
    """Consumo do provedor de IA por chamada — base para os limites diários."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    request_id: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
