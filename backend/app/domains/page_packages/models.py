from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


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
