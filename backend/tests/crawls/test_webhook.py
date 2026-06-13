from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.crawls.models import CrawlWebhookEvent
from app.domains.crawls.service import record_webhook_event


def test_duplicate_firecrawl_webhook_is_processed_once() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert record_webhook_event(session, "event-1", {"type": "crawl.completed"})
        assert not record_webhook_event(
            session,
            "event-1",
            {"type": "crawl.completed"},
        )
        assert session.scalar(select(func.count(CrawlWebhookEvent.id))) == 1
