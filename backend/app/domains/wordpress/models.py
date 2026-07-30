import secrets
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    select,
)
from sqlalchemy import (
    inspect as sa_inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.wordpress.draft_jobs import (
    JOB_CONTRACT_VERSIONS,
    hash_draft_job_payload,
    normalize_site_url,
)


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
            "(state = 'claimed' AND claim_token IS NOT NULL AND "
            "claim_expires_at IS NOT NULL AND claimed_at IS NOT NULL) OR "
            "(state != 'claimed' AND claim_token IS NULL AND "
            "claim_expires_at IS NULL AND claimed_at IS NULL)",
            name="ck_wordpress_draft_jobs_claim_fields",
        ),
        CheckConstraint(
            "contract_version IN "
            f"({', '.join(repr(version) for version in JOB_CONTRACT_VERSIONS)})",
            name="ck_wordpress_draft_jobs_contract_version",
        ),
        CheckConstraint(
            "(state IN ('completed', 'failed') AND "
            "terminal_claim_token_hash IS NOT NULL) OR "
            "(state NOT IN ('completed', 'failed') AND "
            "terminal_claim_token_hash IS NULL)",
            name="ck_wordpress_draft_jobs_terminal_claim_hash",
        ),
        ForeignKeyConstraint(
            ["project_id", "proposal_version_id"],
            ["page_package_proposals.project_id", "page_package_proposals.id"],
            name="fk_wordpress_draft_jobs_project_proposal",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "project_id",
            "id",
            name="uq_wordpress_draft_jobs_project_id_id",
        ),
        Index("ix_wordpress_draft_jobs_project_state", "project_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    proposal_version_id: Mapped[str] = mapped_column(
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
    terminal_claim_token_hash: Mapped[str | None] = mapped_column(String(64))
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


@event.listens_for(WordPressOutboundCredential, "before_insert")
@event.listens_for(WordPressOutboundCredential, "before_update")
def _normalize_outbound_credential_site_url(
    _mapper: object,
    _connection: object,
    target: WordPressOutboundCredential,
) -> None:
    target.site_url = normalize_site_url(target.site_url)


@event.listens_for(WordPressDraftJob, "before_insert")
def _validate_draft_job_payload(
    _mapper: object,
    _connection: object,
    target: WordPressDraftJob,
) -> None:
    proposals = Base.metadata.tables["page_package_proposals"]
    proposal_project_id = _connection.execute(
        select(proposals.c.project_id).where(
            proposals.c.id == target.proposal_version_id
        )
    ).scalar_one_or_none()
    if proposal_project_id is not None and proposal_project_id != target.project_id:
        raise ValueError("WordPress draft job proposal belongs to another project")

    expected = hash_draft_job_payload(target.payload)
    if not secrets.compare_digest(expected, target.payload_hash):
        raise ValueError("WordPress draft job payload hash does not match payload")


@event.listens_for(WordPressDraftJob, "before_update")
def _prevent_draft_job_payload_mutation(
    _mapper: object,
    _connection: object,
    target: WordPressDraftJob,
) -> None:
    state = sa_inspect(target)
    if (
        state.attrs.payload.history.has_changes()
        or state.attrs.payload_hash.history.has_changes()
    ):
        raise ValueError("WordPress draft job payload is immutable")


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


class PageObservedVersion(Base):
    __tablename__ = "page_observed_versions"
    __table_args__ = (
        UniqueConstraint(
            "wordpress_page_id",
            "content_hash",
            name="uq_page_observed_versions_page_hash",
        ),
        ForeignKeyConstraint(
            ["project_id", "wordpress_page_id"],
            ["wordpress_pages.project_id", "wordpress_pages.id"],
            name="fk_page_observed_versions_project_page",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["project_id", "proposal_version_id"],
            ["page_package_proposals.project_id", "page_package_proposals.id"],
            name="fk_page_observed_versions_project_proposal",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "draft_job_id"],
            ["wordpress_draft_jobs.project_id", "wordpress_draft_jobs.id"],
            name="fk_page_observed_versions_project_draft_job",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "project_id",
            "id",
            name="uq_page_observed_versions_project_id_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    wordpress_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    proposal_version_id: Mapped[str | None] = mapped_column(String(64))
    draft_job_id: Mapped[str | None] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PageScoreSnapshot(Base):
    __tablename__ = "page_score_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "page_version_id",
            name="uq_page_score_snapshots_page_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    page_version_id: Mapped[str] = mapped_column(
        ForeignKey("page_observed_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    factors: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PageRecommendation(Base):
    __tablename__ = "page_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "wordpress_page_id",
            "fingerprint",
            name="uq_page_recommendations_page_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    page_version_id: Mapped[str] = mapped_column(
        ForeignKey("page_observed_versions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    wordpress_page_id: Mapped[str] = mapped_column(
        ForeignKey("wordpress_pages.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PageTimelineEvent(Base):
    __tablename__ = "page_timeline_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "wordpress_page_id"],
            ["wordpress_pages.project_id", "wordpress_pages.id"],
            name="fk_page_timeline_events_project_page",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["project_id", "page_version_id"],
            ["page_observed_versions.project_id", "page_observed_versions.id"],
            name="fk_page_timeline_events_project_version",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_page_timeline_events_page_created",
            "wordpress_page_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    wordpress_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    page_version_id: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WordPressSnapshotCaptureJob(Base):
    __tablename__ = "wordpress_snapshot_capture_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'claimed', 'completed', 'failed', 'cancelled')",
            name="ck_wordpress_snapshot_capture_jobs_state",
        ),
        CheckConstraint(
            "(state = 'claimed' AND claim_token IS NOT NULL AND "
            "claim_expires_at IS NOT NULL AND claimed_at IS NOT NULL) OR "
            "(state != 'claimed' AND claim_token IS NULL AND "
            "claim_expires_at IS NULL AND claimed_at IS NULL)",
            name="ck_wordpress_snapshot_capture_jobs_claim_fields",
        ),
        CheckConstraint(
            "(state IN ('completed', 'failed') AND "
            "terminal_claim_token_hash IS NOT NULL) OR "
            "(state NOT IN ('completed', 'failed') AND "
            "terminal_claim_token_hash IS NULL)",
            name="ck_wordpress_snapshot_capture_jobs_terminal_claim_hash",
        ),
        ForeignKeyConstraint(
            ["project_id", "wordpress_page_id"],
            ["wordpress_pages.project_id", "wordpress_pages.id"],
            name="fk_wordpress_snapshot_capture_jobs_project_page",
            ondelete="CASCADE",
        ),
        Index(
            "ix_wordpress_snapshot_capture_jobs_project_state",
            "project_id",
            "state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    wordpress_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24),
        default="queued",
        server_default="queued",
        nullable=False,
    )
    claim_token: Mapped[str | None] = mapped_column(String(128))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_claim_token_hash: Mapped[str | None] = mapped_column(String(64))
    snapshot_result: Mapped[dict | None] = mapped_column(JSON)
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
