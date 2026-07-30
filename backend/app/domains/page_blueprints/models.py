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
    or_,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.page_blueprints.lifecycle import blueprint_lifecycle_state_check

OPTIMIZATION_SOURCE_ADAPTER_VERSION = "optimization-source-v1"


class PageBlueprint(Base):
    __tablename__ = "page_blueprints"
    __table_args__ = (
        CheckConstraint(
            blueprint_lifecycle_state_check(),
            name="ck_page_blueprints_state",
        ),
        CheckConstraint(
            "is_default_for_page_type = false OR state = 'ready'",
            name="ck_page_blueprints_default_ready",
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
            "id",
            name="uq_page_blueprints_project_id_id",
        ),
        UniqueConstraint(
            "project_id",
            "wordpress_blueprint_id",
            name="uq_page_blueprint_wordpress_identity",
        ),
        UniqueConstraint(
            "project_id",
            "wordpress_snapshot_id",
            name="uq_page_blueprint_wordpress_snapshot_identity",
        ),
        CheckConstraint(
            "("
            "(wordpress_snapshot_id IS NULL AND snapshot_version IS NULL AND "
            "schema_version IS NULL AND adapter_version IS NULL AND "
            "capture_state IS NULL AND migration_state IS NULL AND "
            "verified_at IS NULL) OR "
            "(wordpress_snapshot_id IS NOT NULL AND snapshot_version IS NOT NULL AND "
            "schema_version IS NOT NULL AND schema_version = 'snapshot-text-v1' AND "
            "adapter_version IS NOT NULL AND capture_state IS NOT NULL AND "
            "capture_state = 'ready' AND migration_state IS NOT NULL AND "
            "migration_state = 'native' AND "
            "verified_at IS NOT NULL)"
            ")",
            name="ck_page_blueprints_snapshot_identity",
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
        ForeignKeyConstraint(
            ["project_id", "supersedes_id"],
            ["page_blueprints.project_id", "page_blueprints.id"],
            name="fk_page_blueprints_supersedes_project",
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
    wordpress_snapshot_id: Mapped[int | None] = mapped_column(Integer)
    snapshot_version: Mapped[int | None] = mapped_column(Integer)
    schema_version: Mapped[str | None] = mapped_column(String(32))
    adapter_version: Mapped[str | None] = mapped_column(String(64))
    capture_state: Mapped[str | None] = mapped_column(String(24))
    migration_state: Mapped[str | None] = mapped_column(String(24))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    supersedes_id: Mapped[str | None] = mapped_column(String(64))
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


def ordinary_blueprint_clause():
    return or_(
        PageBlueprint.adapter_version.is_(None),
        PageBlueprint.adapter_version != OPTIMIZATION_SOURCE_ADAPTER_VERSION,
    )


def is_optimization_source_blueprint(blueprint: PageBlueprint) -> bool:
    return blueprint.adapter_version == OPTIMIZATION_SOURCE_ADAPTER_VERSION
