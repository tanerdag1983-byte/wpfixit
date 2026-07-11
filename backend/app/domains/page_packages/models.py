from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.page_blueprints import models as page_blueprint_models  # noqa: F401


class ProjectPagePackageSettings(Base):
    __tablename__ = "project_page_package_settings"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    builder: Mapped[str] = mapped_column(String(32), nullable=False)
    template_wordpress_page_id: Mapped[str] = mapped_column(
        ForeignKey("wordpress_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    seo_plugin: Mapped[str] = mapped_column(String(32), nullable=False)
    slot_mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    template_content_hash: Mapped[str | None] = mapped_column(String(128))
    validation_state: Mapped[str] = mapped_column(
        String(24),
        default="unvalidated",
        server_default="unvalidated",
        nullable=False,
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class PagePackageProposal(Base):
    __tablename__ = "page_package_proposals"
    __table_args__ = (
        CheckConstraint(
            "("
            "(blueprint_id IS NULL AND blueprint_version IS NULL AND "
            "blueprint_structure_hash IS NULL) OR "
            "(blueprint_id IS NOT NULL AND blueprint_version IS NOT NULL AND "
            "blueprint_structure_hash IS NOT NULL)"
            ")",
            name="ck_page_package_proposals_blueprint_identity_all_or_none",
        ),
        ForeignKeyConstraint(
            [
                "project_id",
                "blueprint_id",
                "blueprint_version",
                "blueprint_structure_hash",
            ],
            [
                "page_blueprints.project_id",
                "page_blueprints.id",
                "page_blueprints.version",
                "page_blueprints.structure_hash",
            ],
            name="fk_page_package_proposals_blueprint_identity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "project_id",
            "id",
            name="uq_page_package_proposals_project_id_id",
        ),
        CheckConstraint(
            "("
            "(is_current = true AND id = current_version_id) OR "
            "(is_current = false AND id != current_version_id)"
            ")",
            name="ck_page_package_proposals_current_pointer_matches_flag",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("keyword_opportunities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(24), default="generating", server_default="generating", nullable=False
    )
    proposal_group_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("page_package_proposals.id", ondelete="RESTRICT")
    )
    current_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    generation_mode: Mapped[str] = mapped_column(
        String(24),
        default="full",
        server_default="full",
        nullable=False,
    )
    target_block_id: Mapped[str | None] = mapped_column(String(128))
    user_instruction: Mapped[str | None] = mapped_column(Text)
    blueprint_id: Mapped[str | None] = mapped_column(String(64))
    blueprint_version: Mapped[int | None] = mapped_column(Integer)
    blueprint_structure_hash: Mapped[str | None] = mapped_column(String(128))
    package: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    rendered_html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wordpress_object_id: Mapped[int | None] = mapped_column(Integer)
    wordpress_edit_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


PagePackageProposalVersion = PagePackageProposal


class PagePackageRegenerationCandidate(Base):
    __tablename__ = "page_package_regeneration_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposal_group_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    base_version_id: Mapped[str] = mapped_column(
        ForeignKey("page_package_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    generation_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    target_block_id: Mapped[str | None] = mapped_column(String(128))
    instruction: Mapped[str | None] = mapped_column(Text)
    candidate_package: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    candidate_rendered_html: Mapped[str] = mapped_column(
        Text, default="", nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        default="generating",
        server_default="generating",
        nullable=False,
    )
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


class PagePackageHandoff(Base):
    __tablename__ = "page_package_handoffs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    proposal_version_id: Mapped[str] = mapped_column(
        ForeignKey("page_package_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    wordpress_connection_id: Mapped[str] = mapped_column(
        ForeignKey("wordpress_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    issued_by: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24),
        default="issued",
        server_default="issued",
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wordpress_object_id: Mapped[int | None] = mapped_column(Integer)
    wordpress_edit_url: Mapped[str | None] = mapped_column(String(2048))
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


Index(
    "ix_page_package_proposals_current_version_per_group",
    PagePackageProposal.proposal_group_id,
    unique=True,
    sqlite_where=PagePackageProposal.is_current.is_(True),
    postgresql_where=PagePackageProposal.is_current.is_(True),
)
