from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

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
