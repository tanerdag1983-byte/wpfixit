from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.page_packages.models import PagePackageProposal
from app.domains.wordpress.models import (
    PageTimelineEvent,
    WordPressDraftJob,
    WordPressPage,
)
from app.domains.wordpress.monitoring import PageCheckResult, check_page


def sync_inventory(
    session: Session,
    project_id: str,
    items: list[dict],
) -> int:
    saved_count = 0
    for item in items:
        page = session.scalar(
            select(WordPressPage).where(
                WordPressPage.project_id == project_id,
                WordPressPage.wordpress_object_id == int(item["id"]),
                WordPressPage.post_type == str(item["type"]),
            )
        )
        if page is None:
            page = WordPressPage(
                id=str(uuid4()),
                project_id=project_id,
                wordpress_object_id=int(item["id"]),
                post_type=str(item["type"]),
                status=str(item["status"]),
                title=str(item.get("title") or ""),
                slug=str(item.get("slug") or ""),
                url=str(item["url"]),
            )
            session.add(page)

        page.status = str(item["status"])
        page.title = str(item.get("title") or "")
        page.slug = str(item.get("slug") or "")
        page.url = str(item["url"])
        page.content_hash = item.get("content_hash")
        page.wordpress_modified_at = item.get("modified")
        page.last_synced_at = datetime.now(UTC)
        saved_count += 1

    session.commit()
    return saved_count


def sync_current_state(
    session: Session,
    page: WordPressPage,
    facts: dict,
) -> PageCheckResult:
    proposal = session.scalar(
        select(PagePackageProposal)
        .where(
            PagePackageProposal.project_id == page.project_id,
            PagePackageProposal.wordpress_object_id == page.wordpress_object_id,
            PagePackageProposal.state == "draft_created",
            PagePackageProposal.is_current.is_(True),
        )
        .order_by(PagePackageProposal.updated_at.desc())
    )
    draft_job = (
        session.scalar(
            select(WordPressDraftJob).where(
                WordPressDraftJob.proposal_version_id == proposal.id,
                WordPressDraftJob.state == "completed",
            )
        )
        if proposal is not None
        else None
    )
    published_at = (
        datetime.now(UTC)
        if proposal is not None and page.status == "publish"
        else None
    )
    result = check_page(
        session,
        page,
        facts,
        trigger="sync",
        proposal_version_id=proposal.id if proposal is not None else None,
        draft_job_id=draft_job.id if draft_job is not None else None,
        published_at=published_at,
    )
    if proposal is not None and published_at is not None:
        existing = session.scalar(
            select(PageTimelineEvent.id).where(
                PageTimelineEvent.wordpress_page_id
                == proposal.source_wordpress_page_id,
                PageTimelineEvent.page_version_id == result.version.id,
                PageTimelineEvent.event_type == "published",
            )
        )
        if existing is None and proposal.source_wordpress_page_id is not None:
            session.add(
                PageTimelineEvent(
                    id=f"ptimeline_{uuid4().hex}",
                    project_id=page.project_id,
                    wordpress_page_id=proposal.source_wordpress_page_id,
                    page_version_id=result.version.id,
                    event_type="published",
                    payload={
                        "proposal_id": proposal.id,
                        "draft_job_id": draft_job.id if draft_job is not None else None,
                        "wordpress_object_id": page.wordpress_object_id,
                    },
                    created_at=published_at,
                )
            )
    return result
