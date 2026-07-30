from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.wordpress.models import (
    PageObservedVersion,
    WordPressPage,
    WordPressSnapshotCaptureJob,
)


@pytest.fixture
def wordpress_page(session, projects) -> WordPressPage:
    page = WordPressPage(
        id="monitoring-page",
        project_id=projects.member_project.id,
        wordpress_object_id=701,
        post_type="page",
        status="publish",
        title="Monitoring page",
        slug="monitoring-page",
        url="https://member.example/monitoring-page",
    )
    session.add(page)
    session.commit()
    return page


def observed_version(
    wordpress_page: WordPressPage, content_hash: str
) -> PageObservedVersion:
    return PageObservedVersion(
        id=f"version-{content_hash}",
        project_id=wordpress_page.project_id,
        wordpress_page_id=wordpress_page.id,
        content_hash=content_hash,
        source="synchronized",
        snapshot_payload={"content_hash": content_hash},
    )


def snapshot_job(
    wordpress_page: WordPressPage,
    *,
    state: str = "queued",
    claim_token: str | None = None,
) -> WordPressSnapshotCaptureJob:
    claimed_at = datetime.now(UTC) if claim_token else None
    return WordPressSnapshotCaptureJob(
        id=f"snapshot-job-{state}",
        project_id=wordpress_page.project_id,
        wordpress_page_id=wordpress_page.id,
        state=state,
        claim_token=claim_token,
        claim_expires_at=(
            datetime.now(UTC) + timedelta(minutes=5) if claim_token else None
        ),
        claimed_at=claimed_at,
    )


def test_same_page_hash_is_unique(session, wordpress_page) -> None:
    session.add_all(
        [
            observed_version(wordpress_page, "hash-a"),
            observed_version(wordpress_page, "hash-a"),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_capture_job_requires_claim_fields_only_while_claimed(
    session, wordpress_page
) -> None:
    session.add(snapshot_job(wordpress_page, state="claimed", claim_token=None))

    with pytest.raises(IntegrityError):
        session.commit()
