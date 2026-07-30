import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select, update

from app.domains.page_blueprints.schemas import SnapshotTextSchema
from app.domains.wordpress.draft_jobs import normalize_site_url

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.domains.wordpress.models import (
        WordPressPage,
        WordPressSnapshotCaptureJob,
    )

CLAIM_TTL = timedelta(minutes=5)
RESULT_KEYS = {
    "snapshot_id",
    "snapshot_version",
    "structure_hash",
    "schema_version",
    "schema",
    "snapshot_kind",
    "source_post_id",
    "source_url",
    "source_content_hash",
    "captured_at",
}


class SnapshotJobError(ValueError):
    pass


@dataclass(frozen=True)
class ClaimedSnapshotJob:
    job: "WordPressSnapshotCaptureJob"
    claim_token: str
    source_post_id: int
    source_url: str
    source_content_hash: str | None


def create_or_get_snapshot_job(
    session: "Session", page: "WordPressPage"
) -> "WordPressSnapshotCaptureJob":
    from app.domains.wordpress.models import (
        WordPressPage,
        WordPressSnapshotCaptureJob,
    )

    locked_page = session.scalar(
        select(WordPressPage).where(WordPressPage.id == page.id).with_for_update()
    )
    if locked_page is None:
        raise SnapshotJobError("snapshot job source page not found")
    existing = session.scalar(
        select(WordPressSnapshotCaptureJob).where(
            WordPressSnapshotCaptureJob.project_id == locked_page.project_id,
            WordPressSnapshotCaptureJob.wordpress_page_id == locked_page.id,
            WordPressSnapshotCaptureJob.state.in_(("queued", "claimed")),
        )
    )
    if existing is not None:
        return existing
    job = WordPressSnapshotCaptureJob(
        id=f"wsnapjob_{uuid4().hex}",
        project_id=locked_page.project_id,
        wordpress_page_id=locked_page.id,
        state="queued",
    )
    session.add(job)
    session.flush()
    return job


def claim_next_snapshot_job(
    session: "Session",
    project_id: str,
    site_url: str,
    *,
    now: datetime | None = None,
) -> ClaimedSnapshotJob | None:
    from app.domains.wordpress.models import (
        WordPressOutboundCredential,
        WordPressPage,
        WordPressSnapshotCaptureJob,
    )

    requested_at = now or datetime.now(UTC)
    normalized_site_url = normalize_site_url(site_url)
    credential = session.scalar(
        select(WordPressOutboundCredential).where(
            WordPressOutboundCredential.project_id == project_id,
            WordPressOutboundCredential.revoked_at.is_(None),
        )
    )
    if credential is None or credential.site_url != normalized_site_url:
        raise SnapshotJobError("wordpress_outbound_credential_invalid")
    session.execute(
        update(WordPressSnapshotCaptureJob)
        .where(
            WordPressSnapshotCaptureJob.project_id == project_id,
            WordPressSnapshotCaptureJob.state == "claimed",
            WordPressSnapshotCaptureJob.claim_expires_at <= requested_at,
        )
        .values(
            state="queued",
            claim_token=None,
            claim_expires_at=None,
            claimed_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    session.expire_all()
    job = session.scalar(
        select(WordPressSnapshotCaptureJob)
        .where(
            WordPressSnapshotCaptureJob.project_id == project_id,
            WordPressSnapshotCaptureJob.state == "queued",
        )
        .order_by(
            WordPressSnapshotCaptureJob.created_at,
            WordPressSnapshotCaptureJob.id,
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        credential.last_seen_at = requested_at
        return None
    page = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == job.wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if page is None:
        job.state = "cancelled"
        job.cancelled_at = requested_at
        session.flush()
        return None

    claim_token = secrets.token_urlsafe(32)
    job.state = "claimed"
    job.claim_token = claim_token
    job.claimed_at = requested_at
    job.claim_expires_at = requested_at + CLAIM_TTL
    job.attempt_count += 1
    credential.last_seen_at = requested_at
    session.flush()
    return ClaimedSnapshotJob(
        job=job,
        claim_token=claim_token,
        source_post_id=page.wordpress_object_id,
        source_url=page.url,
        source_content_hash=page.content_hash,
    )


def complete_snapshot_job(
    session: "Session",
    job_id: str,
    claim_token: str,
    result: dict,
    *,
    now: datetime | None = None,
) -> "WordPressSnapshotCaptureJob":
    from app.domains.wordpress.models import (
        WordPressPage,
        WordPressSnapshotCaptureJob,
    )

    job = session.scalar(
        select(WordPressSnapshotCaptureJob)
        .where(WordPressSnapshotCaptureJob.id == job_id)
        .with_for_update()
    )
    if job is None:
        raise SnapshotJobError("snapshot job not found")
    if job.state == "completed":
        _require_terminal_claim(job, claim_token)
        if job.snapshot_result != result:
            raise SnapshotJobError("snapshot job result conflict")
        return job
    _require_active_claim(job, claim_token, now=now)
    _validate_result(result)
    page = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == job.wordpress_page_id,
            WordPressPage.project_id == job.project_id,
        ).with_for_update()
    )
    if page is None or result["source_post_id"] != page.wordpress_object_id:
        raise SnapshotJobError("snapshot result source page mismatch")
    if result["source_url"] != page.url:
        raise SnapshotJobError("snapshot result source page URL mismatch")
    if page.content_hash is not None and (
        result["source_content_hash"] != page.content_hash
    ):
        raise SnapshotJobError("snapshot result source page content changed")

    job.state = "completed"
    job.snapshot_result = result
    job.completed_at = now or datetime.now(UTC)
    job.terminal_claim_token_hash = _hash_claim_token(claim_token)
    _clear_claim(job)
    session.flush()
    return job


def fail_snapshot_job(
    session: "Session",
    job_id: str,
    claim_token: str,
    *,
    error_code: str,
    error_message: str,
    now: datetime | None = None,
) -> "WordPressSnapshotCaptureJob":
    from app.domains.wordpress.models import WordPressSnapshotCaptureJob

    if not error_code or len(error_code) > 64:
        raise SnapshotJobError("snapshot job error code invalid")
    if len(error_message) > 500:
        raise SnapshotJobError("snapshot job error message invalid")
    job = session.scalar(
        select(WordPressSnapshotCaptureJob)
        .where(WordPressSnapshotCaptureJob.id == job_id)
        .with_for_update()
    )
    if job is None:
        raise SnapshotJobError("snapshot job not found")
    if job.state == "failed":
        _require_terminal_claim(job, claim_token)
        if job.error_code != error_code or job.error_message != error_message:
            raise SnapshotJobError("snapshot job result conflict")
        return job
    _require_active_claim(job, claim_token, now=now)
    job.state = "failed"
    job.error_code = error_code
    job.error_message = error_message
    job.failed_at = now or datetime.now(UTC)
    job.terminal_claim_token_hash = _hash_claim_token(claim_token)
    _clear_claim(job)
    session.flush()
    return job


def _validate_result(result: dict) -> None:
    if set(result) != RESULT_KEYS:
        raise SnapshotJobError("snapshot result invalid")
    if (
        not isinstance(result["snapshot_id"], int)
        or isinstance(result["snapshot_id"], bool)
        or result["snapshot_id"] < 1
        or not isinstance(result["snapshot_version"], int)
        or isinstance(result["snapshot_version"], bool)
        or result["snapshot_version"] < 1
        or not isinstance(result["source_post_id"], int)
        or isinstance(result["source_post_id"], bool)
        or result["source_post_id"] < 1
        or not isinstance(result["schema"], dict)
        or result["schema_version"] != "snapshot-text-v1"
        or result["schema"].get("schema_version") != result["schema_version"]
        or result["snapshot_kind"] != "optimization_source"
    ):
        raise SnapshotJobError("snapshot result invalid")
    for key, maximum in (
        ("structure_hash", 128),
        ("source_url", 2048),
        ("source_content_hash", 128),
        ("captured_at", 64),
    ):
        value = result[key]
        if not isinstance(value, str) or not value or len(value) > maximum:
            raise SnapshotJobError("snapshot result invalid")
    try:
        schema = SnapshotTextSchema.model_validate(result["schema"])
        schema.fields_by_id()
        captured_at = datetime.fromisoformat(
            result["captured_at"].replace("Z", "+00:00")
        )
    except ValueError as error:
        raise SnapshotJobError("snapshot result invalid") from error
    if captured_at.tzinfo is None:
        raise SnapshotJobError("snapshot result invalid")


def _require_active_claim(
    job: "WordPressSnapshotCaptureJob",
    claim_token: str,
    *,
    now: datetime | None,
) -> None:
    requested_at = now or datetime.now(UTC)
    if (
        job.state != "claimed"
        or not job.claim_token
        or not secrets.compare_digest(job.claim_token, claim_token)
        or job.claim_expires_at is None
        or _as_utc(job.claim_expires_at) <= requested_at
    ):
        raise SnapshotJobError("snapshot job claim invalid")


def _require_terminal_claim(
    job: "WordPressSnapshotCaptureJob", claim_token: str
) -> None:
    if (
        not job.terminal_claim_token_hash
        or not secrets.compare_digest(
            job.terminal_claim_token_hash,
            _hash_claim_token(claim_token),
        )
    ):
        raise SnapshotJobError("snapshot job claim invalid")


def _clear_claim(job: "WordPressSnapshotCaptureJob") -> None:
    job.claim_token = None
    job.claim_expires_at = None
    job.claimed_at = None


def _hash_claim_token(claim_token: str) -> str:
    return hashlib.sha256(claim_token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
