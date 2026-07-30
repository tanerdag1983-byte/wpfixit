from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.wordpress.models import (
    PageObservedVersion,
    PageScoreSnapshot,
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
    terminal_claim_token_hash: str | None = None,
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
        terminal_claim_token_hash=terminal_claim_token_hash,
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


def test_one_score_snapshot_is_allowed_per_page_version(
    session, wordpress_page
) -> None:
    version = observed_version(wordpress_page, "score-hash")
    session.add(version)
    session.flush()
    session.add_all(
        [
            PageScoreSnapshot(
                id="score-one",
                page_version_id=version.id,
                overall_score=50,
                factors=[],
            ),
            PageScoreSnapshot(
                id="score-two",
                page_version_id=version.id,
                overall_score=60,
                factors=[],
            ),
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


@pytest.mark.parametrize("state", ["completed", "failed"])
def test_capture_job_requires_terminal_claim_hash_after_completion(
    session, wordpress_page, state
) -> None:
    session.add(snapshot_job(wordpress_page, state=state))

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    ("state", "claim_token"),
    [("queued", None), ("claimed", "claim-token"), ("cancelled", None)],
)
def test_capture_job_rejects_terminal_claim_hash_before_completion(
    session, wordpress_page, state, claim_token
) -> None:
    session.add(
        snapshot_job(
            wordpress_page,
            state=state,
            claim_token=claim_token,
            terminal_claim_token_hash="terminal-hash",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
