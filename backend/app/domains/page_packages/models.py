from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
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
