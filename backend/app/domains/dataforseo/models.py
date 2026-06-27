from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
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
