import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domains.projects.models import Organization, Project
from app.domains.wordpress.models import (
    PageScoreSnapshot,
    PageTimelineEvent,
    WordPressPage,
)
from app.domains.wordpress.monitoring import check_page

POSTGRES_TEST_URL = os.getenv("WP_FIXPILOT_POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="WP_FIXPILOT_POSTGRES_TEST_URL is not configured",
)


def test_concurrent_same_hash_checks_reuse_version_and_score() -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"monitoring-org-{suffix}"
    project_id = f"monitoring-project-{suffix}"
    page_id = f"monitoring-page-{suffix}"
    with Session(engine) as session:
        session.add(Organization(id=organization_id, name="Monitoring concurrency"))
        session.flush()
        session.add(
            Project(
                id=project_id,
                organization_id=organization_id,
                name="Monitoring concurrency",
                domain=f"https://{suffix}.example",
            )
        )
        session.flush()
        session.add(
            WordPressPage(
                id=page_id,
                project_id=project_id,
                wordpress_object_id=701,
                post_type="page",
                status="publish",
                title="Source",
                slug="source",
                url=f"https://{suffix}.example/source",
                content_hash="hash-a",
            )
        )
        session.commit()

    facts = {
        "content_hash": "hash-a",
        "values": {"title": "Source", "content": "<h1>Source</h1>"},
    }
    barrier = Barrier(2)

    def check() -> str:
        with Session(engine) as session:
            page = session.get(WordPressPage, page_id)
            assert page is not None
            barrier.wait(timeout=10)
            result = check_page(session, page, facts, trigger="sync")
            session.commit()
            return result.version.id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            version_ids = [
                future.result(timeout=10)
                for future in [executor.submit(check), executor.submit(check)]
            ]
        with Session(engine) as session:
            assert version_ids[0] == version_ids[1]
            assert session.scalar(select(func.count(PageScoreSnapshot.id))) == 1
            assert (
                session.scalar(
                    select(func.count(PageTimelineEvent.id)).where(
                        PageTimelineEvent.event_type == "score_created"
                    )
                )
                == 1
            )
    finally:
        with Session(engine) as session:
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()
