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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.page_blueprints.lifecycle import blueprint_lifecycle_state_check


class PageBlueprint(Base):
    __tablename__ = "page_blueprints"
    __table_args__ = (
        CheckConstraint(
            blueprint_lifecycle_state_check(),
            name="ck_page_blueprints_state",
        ),
        UniqueConstraint(
            "project_id",
            "id",
            "version",
            "structure_hash",
            name="uq_page_blueprints_project_identity",
        ),
        UniqueConstraint(
            "project_id",
            "wordpress_blueprint_id",
            name="uq_page_blueprint_wordpress_identity",
        ),
        UniqueConstraint(
            "supersedes_id",
            name="uq_page_blueprints_supersedes_id",
        ),
        Index(
            "uq_page_blueprint_default_per_type",
            "project_id",
            "page_type",
            unique=True,
            postgresql_where=text("is_default_for_page_type = true"),
            sqlite_where=text("is_default_for_page_type = 1"),
        ),
        ForeignKeyConstraint(
            ["project_id", "source_wordpress_page_id"],
            ["wordpress_pages.project_id", "wordpress_pages.id"],
            name="fk_page_blueprints_source_wordpress_page_project",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    page_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_wordpress_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    wordpress_blueprint_id: Mapped[int] = mapped_column(Integer, nullable=False)
    builder: Mapped[str] = mapped_column(String(32), nullable=False)
    seo_plugin: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    structure_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    content_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    is_default_for_page_type: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("page_blueprints.id", ondelete="RESTRICT")
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
