from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.projects.models import Organization, Project
from app.domains.wordpress.models import WordPressPage
from app.domains.wordpress.service import sync_inventory


def test_inventory_sync_is_idempotent() -> None:
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

        inventory = [
            {
                "id": 10,
                "type": "page",
                "status": "publish",
                "title": "Diensten voor automatische transmissies",
                "slug": "diensten",
                "url": "https://example.com/diensten",
                "modified": "2026-06-01T10:00:00+00:00",
                "content_hash": "hash-1",
            },
            {
                "id": 11,
                "type": "post",
                "status": "publish",
                "title": "Alles over transmissie revisie",
                "slug": "transmissie-revisie",
                "url": "https://example.com/transmissie-revisie",
                "modified": "2026-06-02T10:00:00+00:00",
                "content_hash": "hash-2",
            },
        ]

        sync_inventory(session, "project-1", inventory)
        sync_inventory(session, "project-1", inventory)

        count = session.scalar(select(func.count(WordPressPage.id)))
        assert count == 2
