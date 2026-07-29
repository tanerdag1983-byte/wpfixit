from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DataForSeoConnection(Base):
    __tablename__ = "dataforseo_connections"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    login: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_status: Mapped[str | None] = mapped_column(String(24))
    last_test_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KeywordOpportunity(Base):
    __tablename__ = "keyword_opportunities"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "keyword",
            "location_code",
            "language_code",
            name="uq_keyword_opportunity_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(String(512), nullable=False)
    location_code: Mapped[int] = mapped_column(Integer, nullable=False)
    language_code: Mapped[str] = mapped_column(String(8), nullable=False)
    search_volume: Mapped[int | None] = mapped_column(Integer)
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    competition: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    competition_level: Mapped[str | None] = mapped_column(String(32))
    keyword_difficulty: Mapped[int | None] = mapped_column(Integer)
    intent: Mapped[str | None] = mapped_column(String(64))
    target_url: Mapped[str | None] = mapped_column(String(2048))
    target_classification: Mapped[str] = mapped_column(
        String(24),
        default="new_page",
        server_default="new_page",
        nullable=False,
    )
    target_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    target_evidence: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    recommended_action: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(
        String(64),
        default="dataforseo",
        server_default="dataforseo",
        nullable=False,
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    first_seen_run_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "keyword_opportunity_sync_runs.id",
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        )
    )
    last_seen_run_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "keyword_opportunity_sync_runs.id",
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        )
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KeywordOpportunitySyncRun(Base):
    __tablename__ = "keyword_opportunity_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('running', 'completed', 'failed')",
            name="ck_keyword_opportunity_sync_runs_state",
        ),
        CheckConstraint(
            '"offset" >= 0',
            name="ck_keyword_opportunity_sync_runs_offset",
        ),
        CheckConstraint(
            '"limit" >= 0',
            name="ck_keyword_opportunity_sync_runs_limit",
        ),
        CheckConstraint(
            "provider_count >= 0 AND accepted_count >= 0 AND created_count >= 0 "
            "AND updated_count >= 0 AND rejected_count >= 0",
            name="ck_keyword_opportunity_sync_runs_counts",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    seed_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    offset: Mapped[int] = mapped_column(Integer, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(
        String(16),
        default="running",
        server_default="running",
        nullable=False,
    )
    provider_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    accepted_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    created_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    updated_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    rejected_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    @classmethod
    def started(
        cls,
        project_id: str,
        seed_fingerprint: str,
        offset: int,
        limit: int,
    ) -> Self:
        return cls(
            id=uuid4().hex,
            project_id=project_id,
            seed_fingerprint=seed_fingerprint,
            offset=offset,
            limit=limit,
        )


class KeywordOpportunitySyncState(Base):
    __tablename__ = "keyword_opportunity_sync_states"
    __table_args__ = (
        CheckConstraint(
            "next_offset >= 0",
            name="ck_keyword_opportunity_sync_states_next_offset",
        ),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seed_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    next_offset: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    exhausted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    last_successful_run_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "keyword_opportunity_sync_runs.id",
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        )
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
