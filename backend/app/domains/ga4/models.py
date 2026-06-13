from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Ga4Connection(Base):
    __tablename__ = "ga4_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    google_connection_id: Mapped[str] = mapped_column(
        ForeignKey("google_connections.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    account_id: Mapped[str | None] = mapped_column(String(64))
    property_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(16))
    timezone: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(
        String(24),
        default="connected",
        server_default="connected",
        nullable=False,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Ga4PagePerformance(Base):
    __tablename__ = "ga4_page_performance"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "property_id",
            "date",
            "page_path",
            name="uq_ga4_page_day",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    property_id: Mapped[str] = mapped_column(String(64), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    page_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False)
    engagement_rate: Mapped[float] = mapped_column(Float, nullable=False)
    key_events: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Ga4TrafficSource(Base):
    __tablename__ = "ga4_traffic_sources"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "property_id",
            "date",
            "source",
            "medium",
            "campaign",
            name="uq_ga4_source_day",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    property_id: Mapped[str] = mapped_column(String(64), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    medium: Mapped[str] = mapped_column(String(512), nullable=False)
    campaign: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False)
    engagement_rate: Mapped[float] = mapped_column(Float, nullable=False)
    key_events: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

