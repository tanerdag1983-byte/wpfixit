import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.api.routes import wordpress as wordpress_routes
from app.core.database import Base
from app.core.security import CurrentUser
from app.domains.projects.models import (
    Organization,
    OrganizationMember,
    Profile,
    Project,
)
from app.domains.wordpress.models import PageTimelineEvent, WordPressPage
from app.maintenance import run_weekly_page_checks

POSTGRES_TEST_URL = os.getenv("WP_FIXPILOT_POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="WP_FIXPILOT_POSTGRES_TEST_URL is not configured",
)


def test_manual_check_lock_makes_concurrent_cron_skip_page(monkeypatch) -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"weekly-org-{suffix}"
    project_id = f"weekly-project-{suffix}"
    profile_id = f"weekly-user-{suffix}"
    page_id = f"weekly-page-{suffix}"
    manual_locked = Event()
    allow_manual_check = Event()
    cron_lock_attempted = Event()

    with Session(engine) as session:
        session.add_all(
            [
                Organization(id=organization_id, name="Weekly checks"),
                Profile(id=profile_id, email=f"{suffix}@example.com"),
                OrganizationMember(
                    organization_id=organization_id,
                    profile_id=profile_id,
                    role="owner",
                ),
                Project(
                    id=project_id,
                    organization_id=organization_id,
                    name="Weekly checks",
                    domain=f"https://{suffix}.example",
                ),
                WordPressPage(
                    id=page_id,
                    project_id=project_id,
                    wordpress_object_id=701,
                    post_type="page",
                    status="publish",
                    title="Source",
                    slug="source",
                    url=f"https://{suffix}.example/source",
                ),
            ]
        )
        session.commit()

    def manual_facts(_session, _project_id, page):
        assert page.id == page_id
        manual_locked.set()
        assert allow_manual_check.wait(timeout=10)
        return {"content_hash": "manual-hash", "values": {"title": "Source"}}

    monkeypatch.setattr(wordpress_routes, "_current_wordpress_state", manual_facts)
    monkeypatch.setattr(
        "app.maintenance._current_wordpress_state",
        lambda *_args: pytest.fail("cron must recheck after waiting for manual lock"),
    )

    def record_cron_lock(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if manual_locked.is_set() and "FOR UPDATE" in statement.upper():
            cron_lock_attempted.set()

    event.listen(engine, "before_cursor_execute", record_cron_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            manual = executor.submit(
                _run_manual_check,
                engine,
                project_id,
                page_id,
                profile_id,
                f"{suffix}@example.com",
            )
            assert manual_locked.wait(timeout=10)
            cron = executor.submit(
                _run_cron,
                engine,
                datetime(2026, 7, 30, tzinfo=UTC),
            )
            assert cron_lock_attempted.wait(timeout=10)
            allow_manual_check.set()
            manual.result(timeout=10)
            result = cron.result(timeout=10)

        assert result.checked_page_ids == ()
        assert result.failed_page_ids == ()
        with Session(engine) as session:
            assert (
                session.scalar(
                    select(func.count(PageTimelineEvent.id)).where(
                        PageTimelineEvent.wordpress_page_id == page_id,
                        PageTimelineEvent.event_type == "page_checked",
                    )
                )
                == 1
            )
    finally:
        event.remove(engine, "before_cursor_execute", record_cron_lock)
        with Session(engine) as session:
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()


def test_cron_check_lock_makes_concurrent_manual_reuse_result(monkeypatch) -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"weekly-cron-org-{suffix}"
    project_id = f"weekly-cron-project-{suffix}"
    profile_id = f"weekly-cron-user-{suffix}"
    page_id = f"weekly-cron-page-{suffix}"
    cron_locked = Event()
    allow_cron_check = Event()
    manual_lock_attempted = Event()

    with Session(engine) as session:
        session.add_all(
            [
                Organization(id=organization_id, name="Weekly cron checks"),
                Profile(id=profile_id, email=f"{suffix}@example.com"),
                OrganizationMember(
                    organization_id=organization_id,
                    profile_id=profile_id,
                    role="owner",
                ),
                Project(
                    id=project_id,
                    organization_id=organization_id,
                    name="Weekly cron checks",
                    domain=f"https://{suffix}.example",
                ),
                WordPressPage(
                    id=page_id,
                    project_id=project_id,
                    wordpress_object_id=702,
                    post_type="page",
                    status="publish",
                    title="Source",
                    slug="source",
                    url=f"https://{suffix}.example/source",
                ),
            ]
        )
        session.commit()

    def cron_facts(_session, _project_id, page):
        assert page.id == page_id
        cron_locked.set()
        assert allow_cron_check.wait(timeout=10)
        return {"content_hash": "cron-hash", "values": {"title": "Source"}}

    monkeypatch.setattr("app.maintenance._current_wordpress_state", cron_facts)
    monkeypatch.setattr(
        wordpress_routes,
        "_current_wordpress_state",
        lambda *_args: pytest.fail("manual check must reuse the cron completion"),
    )

    def record_manual_lock(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if cron_locked.is_set() and "FOR UPDATE" in statement.upper():
            manual_lock_attempted.set()

    event.listen(engine, "before_cursor_execute", record_manual_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            cron = executor.submit(_run_cron, engine, datetime.now(UTC))
            assert cron_locked.wait(timeout=10)
            manual = executor.submit(
                _run_manual_check,
                engine,
                project_id,
                page_id,
                profile_id,
                f"{suffix}@example.com",
            )
            assert manual_lock_attempted.wait(timeout=10)
            allow_cron_check.set()
            cron.result(timeout=10)
            result = manual.result(timeout=10)

        with Session(engine) as session:
            completed = session.scalar(
                select(PageTimelineEvent)
                .where(
                    PageTimelineEvent.wordpress_page_id == page_id,
                    PageTimelineEvent.event_type == "page_checked",
                )
                .order_by(PageTimelineEvent.created_at.desc())
            )
            assert completed is not None
            assert result["version_id"] == completed.page_version_id
            assert (
                session.scalar(
                    select(func.count(PageTimelineEvent.id)).where(
                        PageTimelineEvent.wordpress_page_id == page_id,
                        PageTimelineEvent.event_type == "page_checked",
                    )
                )
                == 1
            )
    finally:
        event.remove(engine, "before_cursor_execute", record_manual_lock)
        with Session(engine) as session:
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()


def _run_cron(engine, now):
    with Session(engine) as session:
        return run_weekly_page_checks(session, now=now)


def _run_manual_check(
    engine,
    project_id: str,
    page_id: str,
    profile_id: str,
    email: str,
) -> dict:
    with Session(engine) as session:
        return wordpress_routes.check_wordpress_page(
            project_id,
            page_id,
            session,
            CurrentUser(id=profile_id, email=email),
        )
