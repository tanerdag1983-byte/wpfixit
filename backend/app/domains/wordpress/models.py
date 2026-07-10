from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WordPressConnection(Base):
    __tablename__ = "wordpress_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    site_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    plugin_version: Mapped[str | None] = mapped_column(String(32))
    seo_plugin: Mapped[str | None] = mapped_column(String(32))
    health_state: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        server_default="pending",
        nullable=False,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WordPressOutboundCredential(Base):
    __tablename__ = "wordpress_outbound_credentials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    site_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class WordPressDraftJob(Base):
    __tablename__ = "wordpress_draft_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'claimed', 'completed', 'failed', 'cancelled')",
            name="ck_wordpress_draft_jobs_state",
        ),
        CheckConstraint(
            "(claim_token IS NULL AND claim_expires_at IS NULL) OR "
            "(claim_token IS NOT NULL AND claim_expires_at IS NOT NULL)",
            name="ck_wordpress_draft_jobs_claim_fields",
        ),
        Index("ix_wordpress_draft_jobs_project_state", "project_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    proposal_version_id: Mapped[str] = mapped_column(
        ForeignKey("page_package_proposals.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24),
        default="queued",
        server_default="queued",
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_token: Mapped[str | None] = mapped_column(String(128))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wordpress_object_id: Mapped[int | None] = mapped_column(Integer)
    wordpress_edit_url: Mapped[str | None] = mapped_column(String(2048))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class WordPressPage(Base):
    __tablename__ = "wordpress_pages"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "wordpress_object_id",
            "post_type",
            name="uq_wordpress_page_identity",
        ),
        UniqueConstraint(
            "project_id",
            "id",
            name="uq_wordpress_pages_project_id_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    wordpress_object_id: Mapped[int] = mapped_column(Integer, nullable=False)
    post_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    slug: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    wordpress_modified_at: Mapped[str | None] = mapped_column(String(64))
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WordPressChangeProposal(Base):
    __tablename__ = "wordpress_change_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    wordpress_page_id: Mapped[str] = mapped_column(
        ForeignKey("wordpress_pages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    recommendation_id: Mapped[str | None] = mapped_column(
        ForeignKey("seo_recommendations.id", ondelete="SET NULL"),
    )
    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    before_value: Mapped[object] = mapped_column(JSON, nullable=False)
    after_value: Mapped[object] = mapped_column(JSON, nullable=False)
    base_content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    approval_state: Mapped[str] = mapped_column(
        String(24),
        default="proposed",
        server_default="proposed",
        nullable=False,
    )
    proposed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_content_hash: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WordPressChangeEvent(Base):
    __tablename__ = "wordpress_change_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("wordpress_change_proposals.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mutation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    before_value: Mapped[object] = mapped_column(JSON, nullable=False)
    after_value: Mapped[object] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_response: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
