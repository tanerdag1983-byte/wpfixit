import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import maintenance
from app.domains.wordpress.models import PageTimelineEvent, WordPressPage
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


@pytest.mark.parametrize(
    ("message", "secret"),
    [
        ("token=secret-value", "secret-value"),
        ("Authorization: Bearer bearer-secret", "bearer-secret"),
    ],
)
def test_weekly_runner_logs_a_sanitized_failure(
    session, projects, monkeypatch, caplog, message, secret
) -> None:
    page = _page(session, projects, "failed-log-page-1")
    session.commit()
    monkeypatch.setattr(
        maintenance,
        "_current_wordpress_state",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(message)),
    )
    caplog.set_level(logging.ERROR, logger="app.maintenance")

    result = run_weekly_page_checks(session, now=NOW)

    assert result.failed_page_ids == (page.id,)
    assert page.id in caplog.text
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


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
