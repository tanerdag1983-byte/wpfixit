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


class GscConnection(Base):
    __tablename__ = "gsc_connections"

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
    property_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    permission_level: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(
        String(24),
        default="connected",
        server_default="connected",
        nullable=False,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GscPagePerformance(Base):
    __tablename__ = "gsc_page_performance"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "property_uri",
            "date",
            "page_url",
            name="uq_gsc_page_day",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    property_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    page_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, nullable=False)
    average_position: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class GscQuery(Base):
    __tablename__ = "gsc_queries"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "property_uri",
            "date",
            "query",
            "page_url",
            name="uq_gsc_query_page_day",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    property_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    query: Mapped[str] = mapped_column(String(2048), nullable=False)
    page_url: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, nullable=False)
    average_position: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

