from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domains.wordpress.draft_jobs import hash_project_key
from app.domains.wordpress.models import (
    WordPressOutboundCredential,
    WordPressSnapshotCaptureJob,
)
from app.domains.wordpress.snapshot_jobs import (
    SnapshotJobError,
    claim_next_snapshot_job,
    complete_snapshot_job,
    create_or_get_snapshot_job,
    fail_snapshot_job,
)
from tests.wordpress.test_draft_job_service import _snapshot_schema
from tests.wordpress.test_page_monitoring_models import (
    wordpress_page as _wordpress_page,
)


@pytest.fixture
def wordpress_page(session, projects):
    page = _wordpress_page.__wrapped__(session, projects)
    page.content_hash = "source-content-hash"
    session.add(
        WordPressOutboundCredential(
            id="snapshot-job-credential",
            project_id=page.project_id,
            key_hash=hash_project_key("wpfx_snapshot_test"),
            site_url="https://member.example",
        )
    )
    session.commit()
    return page


def snapshot_result(**overrides) -> dict:
    return {
        "snapshot_id": 901,
        "snapshot_version": 1,
        "structure_hash": "structure-hash",
        "schema_version": "snapshot-text-v1",
        "schema": _snapshot_schema(),
        "snapshot_kind": "optimization_source",
        "source_post_id": 701,
        "source_url": "https://member.example/monitoring-page",
        "source_content_hash": "source-content-hash",
        "captured_at": "2026-07-30T10:00:00+00:00",
    } | overrides


def test_repeated_capture_request_returns_same_open_job(session, wordpress_page):
    first = create_or_get_snapshot_job(session, wordpress_page)
    second = create_or_get_snapshot_job(session, wordpress_page)

    assert first.id == second.id


def test_repeated_capture_retires_a_stale_claim_and_queues_current_identity(
    session,
    wordpress_page,
):
    stale = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert claimed is not None
    wordpress_page.url = "https://member.example/renamed"
    wordpress_page.content_hash = "changed-builder-metadata-hash"
    session.commit()

    fresh = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    session.refresh(stale)

    assert fresh.id != stale.id
    assert fresh.state == "queued"
    assert stale.state == "failed"
    assert stale.error_code == "source_identity_changed"
    assert stale.claim_token is None
    with pytest.raises(SnapshotJobError) as replay_error:
        complete_snapshot_job(
            session,
            stale.id,
            claimed.claim_token,
            snapshot_result(),
        )
    assert replay_error.value.code == "snapshot_source_changed"

    next_claim = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert next_claim is not None
    assert next_claim.job.id == fresh.id
    assert next_claim.source_url == wordpress_page.url
    assert next_claim.source_content_hash == wordpress_page.content_hash


def test_repeated_capture_cancels_a_stale_queued_identity(
    session,
    wordpress_page,
):
    stale = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert claimed is not None
    stale.state = "queued"
    stale.claim_token = None
    stale.claimed_at = None
    stale.claim_expires_at = None
    wordpress_page.content_hash = "changed-after-claim-expiry"
    session.commit()

    fresh = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    session.refresh(stale)

    assert fresh.id != stale.id
    assert fresh.state == "queued"
    assert stale.state == "cancelled"


def test_completion_source_drift_terminalizes_claim_and_opens_fresh_capture(
    session,
    wordpress_page,
):
    stale = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert claimed is not None
    wordpress_page.content_hash = "changed-before-completion"
    session.commit()

    with pytest.raises(SnapshotJobError) as conflict:
        complete_snapshot_job(
            session,
            stale.id,
            claimed.claim_token,
            snapshot_result(),
        )

    assert conflict.value.code == "snapshot_source_changed"
    session.refresh(stale)
    fresh = session.scalar(
        select(WordPressSnapshotCaptureJob).where(
            WordPressSnapshotCaptureJob.wordpress_page_id == wordpress_page.id,
            WordPressSnapshotCaptureJob.state == "queued",
        )
    )
    assert stale.state == "failed"
    assert stale.error_code == "source_identity_changed"
    assert fresh is not None
    assert fresh.id != stale.id

    with pytest.raises(SnapshotJobError) as replay:
        complete_snapshot_job(
            session,
            stale.id,
            claimed.claim_token,
            snapshot_result(),
        )
    assert replay.value.code == "snapshot_source_changed"
    assert session.scalar(
        select(WordPressSnapshotCaptureJob).where(
            WordPressSnapshotCaptureJob.wordpress_page_id == wordpress_page.id,
            WordPressSnapshotCaptureJob.state == "queued",
        )
    ).id == fresh.id


def test_new_snapshot_job_requires_a_source_content_hash(session, wordpress_page):
    wordpress_page.content_hash = None
    session.commit()

    with pytest.raises(SnapshotJobError, match="content hash"):
        create_or_get_snapshot_job(session, wordpress_page)


def test_claim_contains_immutable_source_identity(session, wordpress_page):
    job = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()

    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )

    assert claimed is not None
    assert claimed.job.id == job.id
    assert claimed.source_post_id == 701
    assert claimed.source_url == "https://member.example/monitoring-page"
    assert claimed.source_content_hash == "source-content-hash"
    assert claimed.claim_token


def test_expired_claim_source_drift_terminalizes_and_claims_fresh_job(
    session,
    wordpress_page,
):
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    first = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert first is not None
    first.job.claim_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    wordpress_page.url = "https://member.example/renamed"
    wordpress_page.content_hash = "changed-builder-metadata-hash"
    session.commit()

    second = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert second is not None
    session.refresh(first.job)

    assert first.job.state == "failed"
    assert first.job.error_code == "source_identity_changed"
    assert second.job.id != first.job.id
    assert second.source_url == wordpress_page.url
    assert second.source_content_hash == wordpress_page.content_hash
    with pytest.raises(SnapshotJobError) as replay:
        complete_snapshot_job(
            session,
            first.job.id,
            first.claim_token,
            snapshot_result(),
        )
    assert replay.value.code == "snapshot_source_changed"


def test_completion_rejects_a_different_source_page(session, wordpress_page):
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert claimed is not None

    with pytest.raises(SnapshotJobError, match="source page"):
        complete_snapshot_job(
            session,
            claimed.job.id,
            claimed.claim_token,
            snapshot_result(source_post_id=999),
        )


def test_completion_rejects_a_changed_source_page(session, wordpress_page):
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert claimed is not None
    wordpress_page.content_hash = "new-content-hash"
    session.commit()

    with pytest.raises(SnapshotJobError) as conflict:
        complete_snapshot_job(
            session,
            claimed.job.id,
            claimed.claim_token,
            snapshot_result(),
        )
    assert conflict.value.code == "snapshot_source_changed"


def test_completion_rejects_a_legacy_null_source_hash(session, wordpress_page):
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert claimed is not None
    wordpress_page.content_hash = None
    session.commit()

    with pytest.raises(SnapshotJobError) as conflict:
        complete_snapshot_job(
            session,
            claimed.job.id,
            claimed.claim_token,
            snapshot_result(),
        )
    assert conflict.value.code == "snapshot_source_changed"
    session.refresh(claimed.job)
    assert claimed.job.state == "failed"
    assert (
        session.query(WordPressSnapshotCaptureJob)
        .filter(
            WordPressSnapshotCaptureJob.wordpress_page_id == wordpress_page.id,
            WordPressSnapshotCaptureJob.state.in_(("queued", "claimed")),
        )
        .count()
        == 0
    )
    with pytest.raises(SnapshotJobError, match="content hash missing"):
        create_or_get_snapshot_job(session, wordpress_page)


def test_completion_is_idempotent_only_for_the_same_result(session, wordpress_page):
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert claimed is not None
    result = snapshot_result()

    completed = complete_snapshot_job(
        session,
        claimed.job.id,
        claimed.claim_token,
        result,
    )
    replay = complete_snapshot_job(
        session,
        claimed.job.id,
        claimed.claim_token,
        result,
    )

    assert replay.id == completed.id
    assert replay.state == "completed"
    assert replay.snapshot_result == result
    with pytest.raises(SnapshotJobError, match="result conflict"):
        complete_snapshot_job(
            session,
            claimed.job.id,
            claimed.claim_token,
            snapshot_result(snapshot_id=902),
        )


def test_expired_claim_is_reclaimed_with_a_new_token(session, wordpress_page):
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    first = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert first is not None
    first.job.claim_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()

    second = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )

    assert second is not None
    assert second.job.id == first.job.id
    assert second.claim_token != first.claim_token
    assert second.job.attempt_count == 2


def test_failure_replay_preserves_one_terminal_result(session, wordpress_page):
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    claimed = claim_next_snapshot_job(
        session,
        wordpress_page.project_id,
        "https://member.example",
    )
    assert claimed is not None

    failed = fail_snapshot_job(
        session,
        claimed.job.id,
        claimed.claim_token,
        error_code="wordpress_error",
        error_message="Capture failed",
    )
    replay = fail_snapshot_job(
        session,
        claimed.job.id,
        claimed.claim_token,
        error_code="wordpress_error",
        error_message="Capture failed",
    )

    assert replay.id == failed.id
    assert replay.state == "failed"
    with pytest.raises(SnapshotJobError, match="claim"):
        fail_snapshot_job(
            session,
            claimed.job.id,
            "different-claim-token-with-valid-length",
            error_code="wordpress_error",
            error_message="Capture failed",
        )


def test_claim_rejects_a_different_bound_site(session, wordpress_page):
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()

    with pytest.raises(SnapshotJobError, match="credential"):
        claim_next_snapshot_job(
            session,
            wordpress_page.project_id,
            "https://other.example",
        )
