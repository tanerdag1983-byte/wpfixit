import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domains.dataforseo.models import (
    KeywordOpportunity,
    KeywordOpportunitySyncRun,
    KeywordOpportunitySyncState,
)
from app.domains.dataforseo.service import sync_keyword_opportunity_window
from app.domains.projects.models import Organization, Project
from app.domains.recommendations.models import CompanyProfile

POSTGRES_TEST_URL = os.getenv("WP_FIXPILOT_POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="WP_FIXPILOT_POSTGRES_TEST_URL is required",
)


def test_project_syncs_are_serialized_on_postgresql() -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"keyword-sync-org-{suffix}"
    project_id = f"keyword-sync-project-{suffix}"
    barrier = Barrier(2)
    calls: list[int] = []
    calls_lock = Lock()

    class Provider:
        def keyword_ideas(
            self,
            seeds: list[str],
            *,
            limit: int,
            offset: int,
        ) -> list[dict]:
            with calls_lock:
                calls.append(offset)
            time.sleep(0.2)
            return [
                {
                    "keyword": f"transmissie {offset + index}",
                    "location_code": 2528,
                    "language_code": "nl",
                }
                for index in range(limit)
            ]

    with Session(engine) as session:
        session.add(
            Organization(id=organization_id, name="Keyword sync concurrency")
        )
        session.commit()
        session.add(
            Project(
                id=project_id,
                organization_id=organization_id,
                name="Keyword sync concurrency",
                domain=f"https://{suffix}.example",
            )
        )
        session.add(
            CompanyProfile(
                project_id=project_id,
                company_name="Transmissiehuis",
                description="Transmissiespecialist.",
                audience="Autobezitters.",
                services=["transmissie advies"],
                tone_of_voice="Duidelijk",
                custom_prompt="",
            )
        )
        session.commit()

    def sync() -> int:
        with Session(engine) as session:
            project = session.get(Project, project_id)
            assert project is not None
            barrier.wait(timeout=10)
            return sync_keyword_opportunity_window(
                session, project, Provider()
            ).offset

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(sync), executor.submit(sync)]
            offsets = [future.result(timeout=15) for future in futures]

        assert sorted(offsets) == [0, 50]
        assert sorted(calls) == [0, 50]
        with Session(engine) as session:
            state = session.get(KeywordOpportunitySyncState, project_id)
            assert state is not None
            assert state.next_offset == 100
            assert session.scalar(
                select(func.count())
                .select_from(KeywordOpportunity)
                .where(KeywordOpportunity.project_id == project_id)
            ) == 100
            assert session.scalar(
                select(func.count())
                .select_from(KeywordOpportunitySyncRun)
                .where(
                    KeywordOpportunitySyncRun.project_id == project_id,
                    KeywordOpportunitySyncRun.state == "completed",
                )
            ) == 2
    finally:
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project is not None:
                session.delete(project)
                session.commit()
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()
