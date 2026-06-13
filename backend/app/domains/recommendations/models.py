from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrganizationAiSettings(Base):
    __tablename__ = "organization_ai_settings"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    services: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tone_of_voice: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )
    custom_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
