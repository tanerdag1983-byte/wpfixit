from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PageBlueprint(Base):
    __tablename__ = "page_blueprints"
    __table_args__ = (
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
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    page_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_wordpress_page_id: Mapped[str] = mapped_column(
        ForeignKey("wordpress_pages.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
