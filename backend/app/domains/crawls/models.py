from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_crawl_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
    )
    root_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    page_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlPage(Base):
    __tablename__ = "crawl_pages"
    __table_args__ = (
        UniqueConstraint("crawl_run_id", "url", name="uq_crawl_page_url"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    crawl_run_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    robots: Mapped[str | None] = mapped_column(String(255))
    markdown: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    indexable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    raw_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CrawlLink(Base):
    __tablename__ = "crawl_links"
    __table_args__ = (
        UniqueConstraint(
            "crawl_page_id",
            "target_url",
            name="uq_crawl_page_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    crawl_page_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    anchor: Mapped[str | None] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    follow: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CrawlIssue(Base):
    __tablename__ = "crawl_issues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    crawl_run_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    crawl_page_id: Mapped[str | None] = mapped_column(
        ForeignKey("crawl_pages.id", ondelete="CASCADE"),
        index=True,
    )
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CrawlWebhookEvent(Base):
    __tablename__ = "crawl_webhook_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    webhook_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
