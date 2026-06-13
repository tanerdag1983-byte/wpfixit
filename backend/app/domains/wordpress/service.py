from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.wordpress.models import WordPressPage


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

