import argparse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routes.wordpress import _current_wordpress_state
from app.core.database import SessionLocal
from app.domains.wordpress.models import PageTimelineEvent, WordPressPage
from app.domains.wordpress.monitoring import check_page


@dataclass(frozen=True)
class WeeklyPageCheckResult:
    due_page_ids: tuple[str, ...]
    checked_page_ids: tuple[str, ...]
    failed_page_ids: tuple[str, ...]


def run_weekly_page_checks(
    session: Session,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
) -> WeeklyPageCheckResult:
    checked_at = now or datetime.now(UTC)
    latest_checks = (
        select(
            PageTimelineEvent.wordpress_page_id,
            func.max(PageTimelineEvent.created_at).label("checked_at"),
        )
        .where(PageTimelineEvent.event_type == "page_checked")
        .group_by(PageTimelineEvent.wordpress_page_id)
        .subquery()
    )
    due_pages = tuple(
        session.scalars(
            select(WordPressPage)
            .outerjoin(
                latest_checks,
                latest_checks.c.wordpress_page_id == WordPressPage.id,
            )
            .where(
                or_(
                    latest_checks.c.checked_at.is_(None),
                    latest_checks.c.checked_at <= checked_at - timedelta(days=7),
                )
            )
            .order_by(WordPressPage.id)
        )
    )
    due_page_ids = tuple(page.id for page in due_pages)
    if dry_run:
        return WeeklyPageCheckResult(due_page_ids, (), ())

    checked_page_ids = []
    failed_page_ids = []
    for page in due_pages:
        try:
            check_page(
                session,
                page,
                _current_wordpress_state(session, page.project_id, page),
                trigger="scheduled",
            )
            session.commit()
            checked_page_ids.append(page.id)
        except Exception:
            session.rollback()
            failed_page_ids.append(page.id)
    return WeeklyPageCheckResult(
        due_page_ids,
        tuple(checked_page_ids),
        tuple(failed_page_ids),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    weekly_checks = commands.add_parser("weekly-page-checks")
    weekly_checks.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        result = run_weekly_page_checks(session, dry_run=args.dry_run)
    print(
        f"due={len(result.due_page_ids)} checked={len(result.checked_page_ids)} "
        f"failed={len(result.failed_page_ids)}"
    )
    return int(bool(result.failed_page_ids))


if __name__ == "__main__":
    raise SystemExit(main())
