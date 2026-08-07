import argparse
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routes.wordpress import _current_wordpress_state
from app.core.database import SessionLocal
from app.domains.wordpress.models import PageTimelineEvent, WordPressPage
from app.domains.wordpress.monitoring import check_page

logger = logging.getLogger(__name__)
_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(token|secret|password|authorization|api[-_ ]?key|key)\b"
    r"(?:\s*(?:[:=]|is)\s*|\s+)(?:bearer\s+)?\S+"
)

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
    due_page_ids = _due_page_ids(session, checked_at)
    if dry_run:
        return WeeklyPageCheckResult(due_page_ids, (), ())

    checked_page_ids = []
    failed_page_ids = []
    for page_id in due_page_ids:
        try:
            page = _locked_page(session, page_id)
            if page is None or not _page_is_due(session, page.id, checked_at):
                session.rollback()
                continue
            check_page(
                session,
                page,
                _current_wordpress_state(session, page.project_id, page),
                trigger="scheduled",
            )
            session.commit()
            checked_page_ids.append(page.id)
        except Exception as error:
            session.rollback()
            failed_page_ids.append(page_id)
            logger.error(
                "Weekly page check failed page_id=%s error=%s message=%s",
                page_id,
                type(error).__name__,
                _safe_error_message(error),
            )
    return WeeklyPageCheckResult(
        due_page_ids,
        tuple(checked_page_ids),
        tuple(failed_page_ids),
    )


def _due_page_ids(session: Session, checked_at: datetime) -> tuple[str, ...]:
    latest_checks = (
        select(
            PageTimelineEvent.wordpress_page_id,
            func.max(PageTimelineEvent.created_at).label("checked_at"),
        )
        .where(PageTimelineEvent.event_type == "page_checked")
        .group_by(PageTimelineEvent.wordpress_page_id)
        .subquery()
    )
    return tuple(
        session.scalars(
            select(WordPressPage.id)
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

def _locked_page(session: Session, page_id: str) -> WordPressPage | None:
    return session.scalar(
        select(WordPressPage)
        .where(WordPressPage.id == page_id)
        .with_for_update()
    )


def _page_is_due(session: Session, page_id: str, checked_at: datetime) -> bool:
    latest_check = session.scalar(
        select(func.max(PageTimelineEvent.created_at)).where(
            PageTimelineEvent.wordpress_page_id == page_id,
            PageTimelineEvent.event_type == "page_checked",
        )
    )
    if latest_check is not None and latest_check.tzinfo is None:
        latest_check = latest_check.replace(tzinfo=UTC)
    return latest_check is None or latest_check <= checked_at - timedelta(days=7)


def _safe_error_message(error: Exception) -> str:
    message = _SENSITIVE_VALUE.sub(r"\1=[redacted]", str(error).strip())
    return message[:500] or "(no message)"


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
