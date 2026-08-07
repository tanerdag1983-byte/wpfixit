import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import maintenance
from app.api.routes import wordpress as wordpress_routes
from app.core.security import CurrentUser
from app.domains.wordpress.models import (
    PageObservedVersion,
    PageTimelineEvent,
    WordPressPage,
)
from app.maintenance import WeeklyPageCheckResult, main, run_weekly_page_checks

NOW = datetime(2026, 7, 30, tzinfo=UTC)


def _page(session, projects, page_id: str) -> WordPressPage:
    page = WordPressPage(
        id=page_id,
        project_id=projects.member_project.id,
        wordpress_object_id=int(page_id[-1]) + 700,
        post_type="page",
        status="publish",
        title=page_id,
        slug=page_id,
        url=f"https://member.example/{page_id}",
    )
    session.add(page)
    session.flush()
    return page


def _checked(session, page: WordPressPage, at: datetime) -> None:
    session.add(
        PageTimelineEvent(
            id=f"event-{page.id}",
            project_id=page.project_id,
            wordpress_page_id=page.id,
            page_version_id=None,
            event_type="page_checked",
            payload={},
            created_at=at,
        )
    )


def _completed_check(session, page: WordPressPage, at: datetime) -> PageTimelineEvent:
    version = PageObservedVersion(
        id=f"version-{page.id}-{at.timestamp()}",
        project_id=page.project_id,
        wordpress_page_id=page.id,
        content_hash=f"hash-{page.id}-{at.timestamp()}",
        source="scheduled",
        snapshot_payload={"content_hash": f"hash-{page.id}", "values": {}},
        observed_at=at,
    )
    session.add(version)
    session.flush()
    event = PageTimelineEvent(
        id=f"completed-{page.id}-{at.timestamp()}",
        project_id=page.project_id,
        wordpress_page_id=page.id,
        page_version_id=version.id,
        event_type="page_checked",
        payload={"overall_score": 73},
        created_at=at,
    )
    session.add(event)
    session.flush()
    return event


def test_weekly_runner_checks_only_due_pages(session, projects, monkeypatch) -> None:
    due_page = _page(session, projects, "due-page-1")
    recent_page = _page(session, projects, "recent-page-2")
    _checked(session, due_page, NOW - timedelta(days=7))
    _checked(session, recent_page, NOW - timedelta(days=6))
    session.commit()
    monkeypatch.setattr(
        "app.maintenance._current_wordpress_state",
        lambda _session, _project_id, page: {
            "content_hash": f"hash-{page.id}",
            "values": {"title": page.title},
        },
    )

    result = run_weekly_page_checks(session, now=NOW)

    assert result.checked_page_ids == (due_page.id,)
    assert session.scalar(
        select(func.count(PageTimelineEvent.id)).where(
            PageTimelineEvent.wordpress_page_id == due_page.id,
            PageTimelineEvent.event_type == "page_checked",
        )
    ) == 2


def test_weekly_runner_keeps_other_pages_committed_after_a_failure(
    session, projects, monkeypatch
) -> None:
    first_page = _page(session, projects, "first-page-1")
    failing_page = _page(session, projects, "failing-page-2")
    session.commit()

    def current_state(_session, _project_id, page):
        if page.id == failing_page.id:
            raise RuntimeError("WordPress unavailable")
        return {"content_hash": "first-hash", "values": {"title": page.title}}

    monkeypatch.setattr("app.maintenance._current_wordpress_state", current_state)

    result = run_weekly_page_checks(session, now=NOW)

    assert result.checked_page_ids == (first_page.id,)
    assert result.failed_page_ids == (failing_page.id,)
    assert session.scalar(
        select(func.count(PageTimelineEvent.id)).where(
            PageTimelineEvent.wordpress_page_id == first_page.id,
            PageTimelineEvent.event_type == "page_checked",
        )
    ) == 1


def test_weekly_runner_dry_run_does_not_write(session, projects) -> None:
    due_page = _page(session, projects, "dry-run-page-1")
    session.commit()

    result = run_weekly_page_checks(session, now=NOW, dry_run=True)

    assert result.due_page_ids == (due_page.id,)
    assert result.checked_page_ids == ()
    assert session.scalar(select(func.count(PageTimelineEvent.id))) == 0


def test_weekly_runner_rechecks_due_evidence_after_lock(
    session, projects, monkeypatch
) -> None:
    page = _page(session, projects, "rechecked-page-1")
    session.commit()

    def lock_page(_session, page_id):
        assert page_id == page.id
        _checked(session, page, NOW)
        session.flush()
        return page

    monkeypatch.setattr(maintenance, "_locked_page", lock_page)
    monkeypatch.setattr(
        maintenance,
        "_current_wordpress_state",
        lambda *_args: pytest.fail("a newly checked page must not be fetched"),
    )

    result = run_weekly_page_checks(session, now=NOW)

    assert result.due_page_ids == (page.id,)
    assert result.checked_page_ids == ()
    assert result.failed_page_ids == ()


def test_weekly_runner_logs_a_sanitized_failure(
    session, projects, monkeypatch, caplog
) -> None:
    page = _page(session, projects, "failed-log-page-1")
    session.commit()
    message = '{"api_key":"api-secret","access_token":"access-secret"}'
    monkeypatch.setattr(
        maintenance,
        "_current_wordpress_state",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(message)),
    )
    caplog.set_level(logging.ERROR, logger="app.maintenance")

    result = run_weekly_page_checks(session, now=NOW)

    assert result.failed_page_ids == (page.id,)
    assert page.id in caplog.text
    assert "error_class=runtime_error" in caplog.text
    assert "page_check_failed" in caplog.text
    assert "api-secret" not in caplog.text
    assert "access-secret" not in caplog.text
    assert message not in caplog.text


def test_manual_check_reuses_completed_overlapping_check(
    session, projects, monkeypatch
) -> None:
    page = _page(session, projects, "manual-overlap-page-1")
    session.commit()
    original_page_or_404 = wordpress_routes._page_or_404
    completed = None

    def lock_page(*args, **kwargs):
        nonlocal completed
        locked = original_page_or_404(*args, **kwargs)
        completed = _completed_check(session, locked, datetime.now(UTC))
        return locked

    monkeypatch.setattr(wordpress_routes, "_page_or_404", lock_page)
    monkeypatch.setattr(
        wordpress_routes,
        "_current_wordpress_state",
        lambda *_args: pytest.fail("overlapping completion must be reused"),
    )

    result = wordpress_routes.check_wordpress_page(
        page.project_id,
        page.id,
        session,
        CurrentUser(id=projects.member.id, email=projects.member.email),
    )

    assert completed is not None
    assert result == {
        "version_id": completed.page_version_id,
        "version_created": False,
        "overall_score": 73,
        "recommendations_created": 0,
        "checked_at": completed.created_at,
    }


def test_manual_check_runs_after_a_preexisting_completion(
    session, projects, monkeypatch
) -> None:
    page = _page(session, projects, "manual-explicit-page-1")
    _completed_check(session, page, NOW)
    session.commit()
    fetched_pages = []
    monkeypatch.setattr(
        wordpress_routes,
        "_current_wordpress_state",
        lambda _session, _project_id, locked_page: (
            fetched_pages.append(locked_page.id)
            or {"content_hash": "manual-explicit-hash", "values": {"title": page.title}}
        ),
    )

    wordpress_routes.check_wordpress_page(
        page.project_id,
        page.id,
        session,
        CurrentUser(id=projects.member.id, email=projects.member.email),
    )

    assert fetched_pages == [page.id]
    assert session.scalar(
        select(func.count(PageTimelineEvent.id)).where(
            PageTimelineEvent.wordpress_page_id == page.id,
            PageTimelineEvent.event_type == "page_checked",
        )
    ) == 2


def test_render_cron_reuses_the_api_encryption_secret() -> None:
    render_yaml = Path(__file__).parents[3] / "render.yaml"

    assert """- key: WP_FIXPILOT_ENCRYPTION_KEY
        fromService:
          type: web
          name: wp-fixpilot-api
          envVarKey: WP_FIXPILOT_ENCRYPTION_KEY""" in render_yaml.read_text()


def test_weekly_cli_returns_nonzero_for_failed_pages(monkeypatch) -> None:
    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.maintenance.SessionLocal", SessionContext)
    monkeypatch.setattr(
        "app.maintenance.run_weekly_page_checks",
        lambda _session, dry_run: WeeklyPageCheckResult(("page-1",), (), ("page-1",)),
    )

    assert main(["weekly-page-checks"]) == 1
