from datetime import date

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.gsc.models import GscQuery
from app.domains.gsc.service import import_query_rows
from app.domains.projects.models import Organization, Project


def test_gsc_sync_upserts_same_daily_query() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="Organization"))
        session.add(
            Project(
                id="project-1",
                organization_id="org-1",
                name="Project",
                domain="https://example.com",
            )
        )
        session.commit()
        rows = [
            {
                "date": date(2026, 6, 1),
                "query": "transmissie revisie",
                "page_url": "https://example.com/revisie",
                "clicks": 12,
                "impressions": 400,
                "ctr": 0.03,
                "position": 4.8,
            }
        ]

        import_query_rows(session, "project-1", "sc-domain:example.com", rows)
        import_query_rows(session, "project-1", "sc-domain:example.com", rows)

        assert session.scalar(select(func.count(GscQuery.id))) == 1
