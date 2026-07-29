import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
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


def test_failed_sync_cannot_overwrite_newer_successful_state() -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"keyword-race-org-{suffix}"
    project_id = f"keyword-race-project-{suffix}"
    failing_provider_entered = Event()
    allow_failing_rows = Event()
    success_lock_attempted = Event()
    failure_rolled_back = Event()
    allow_failed_run_persistence = Event()

    class FailingProvider:
        def keyword_ideas(
            self,
            seeds: list[str],
            *,
            limit: int,
            offset: int,
        ) -> list[dict]:
            failing_provider_entered.set()
            assert allow_failing_rows.wait(timeout=10)
            return [
                {
                    "keyword": "transmissie rollback",
                    "location_code": 2528,
                    "language_code": "nl",
                },
                {
                    "keyword": "transmissie ongeldige locatie",
                    "location_code": "niet-numeriek",
                    "language_code": "nl",
                },
            ]

    class SuccessfulProvider:
        def keyword_ideas(
            self,
            seeds: list[str],
            *,
            limit: int,
            offset: int,
        ) -> list[dict]:
            return [
                {
                    "keyword": f"transmissie success {index}",
                    "location_code": 2528,
                    "language_code": "nl",
                }
                for index in range(limit)
            ]

    with Session(engine) as session:
        session.add(
            Organization(id=organization_id, name="Keyword failure race")
        )
        session.commit()
        session.add(
            Project(
                id=project_id,
                organization_id=organization_id,
                name="Keyword failure race",
                domain=f"https://failure-{suffix}.example",
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

    def fail_sync() -> str:
        with Session(engine) as session:
            project = session.get(Project, project_id)
            assert project is not None

            def pause_after_rollback(_session: Session) -> None:
                failure_rolled_back.set()
                assert allow_failed_run_persistence.wait(timeout=10)

            event.listen(session, "after_rollback", pause_after_rollback)
            with pytest.raises(ValueError):
                sync_keyword_opportunity_window(
                    session,
                    project,
                    FailingProvider(),
                )
            return "failed"

    def succeed_sync():
        with Session(engine) as session:
            project = session.get(Project, project_id)
            assert project is not None
            connection = session.connection()

            def record_project_lock(
                _connection,
                _cursor,
                statement: str,
                _parameters,
                _context,
                _executemany: bool,
            ) -> None:
                normalized = statement.upper()
                if "FROM PROJECTS" in normalized and "FOR UPDATE" in normalized:
                    success_lock_attempted.set()

            event.listen(
                connection,
                "before_cursor_execute",
                record_project_lock,
            )
            return sync_keyword_opportunity_window(
                session,
                project,
                SuccessfulProvider(),
            )

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        failed_future = executor.submit(fail_sync)
        assert failing_provider_entered.wait(timeout=10)
        successful_future = executor.submit(succeed_sync)
        assert success_lock_attempted.wait(timeout=10)
        allow_failing_rows.set()
        assert failure_rolled_back.wait(timeout=10)

        successful_result = successful_future.result(timeout=10)
        allow_failed_run_persistence.set()
        assert failed_future.result(timeout=10) == "failed"

        with Session(engine) as session:
            state = session.get(KeywordOpportunitySyncState, project_id)
            assert state is not None
            assert state.next_offset == 50
            assert state.last_successful_run_id == successful_result.run_id
            assert state.last_error is None

            opportunities = session.scalars(
                select(KeywordOpportunity).where(
                    KeywordOpportunity.project_id == project_id
                )
            ).all()
            assert len(opportunities) == 50
            assert all(
                item.keyword.startswith("transmissie success ")
                for item in opportunities
            )

            runs = session.scalars(
                select(KeywordOpportunitySyncRun).where(
                    KeywordOpportunitySyncRun.project_id == project_id
                )
            ).all()
            assert sorted(run.state for run in runs) == [
                "completed",
                "failed",
            ]
            completed = next(run for run in runs if run.state == "completed")
            assert completed.id == successful_result.run_id
    finally:
        allow_failing_rows.set()
        allow_failed_run_persistence.set()
        executor.shutdown(wait=True)
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
