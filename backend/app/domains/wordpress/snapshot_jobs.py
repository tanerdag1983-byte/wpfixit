import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import and_, or_, select

from app.domains.page_blueprints.schemas import SnapshotTextSchema
from app.domains.wordpress.draft_jobs import normalize_site_url

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.domains.wordpress.models import (
        WordPressPage,
        WordPressSnapshotCaptureJob,
    )

CLAIM_TTL = timedelta(minutes=5)
CLAIM_IDENTITY_KEY = "_claim_identity"
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
    def __init__(
        self,
        message: str,
        *,
        code: str = "snapshot_conflict",
        persist_changes: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.persist_changes = persist_changes


@dataclass(frozen=True)
class ClaimedSnapshotJob:
    job: "WordPressSnapshotCaptureJob"
    claim_token: str
    source_post_id: int
    source_url: str
    source_content_hash: str


def create_or_get_snapshot_job(
    session: "Session", page: "WordPressPage"
) -> "WordPressSnapshotCaptureJob":
    from app.domains.wordpress.models import WordPressPage

    locked_page = session.scalar(
        select(WordPressPage).where(WordPressPage.id == page.id).with_for_update()
    )
    if locked_page is None:
        raise SnapshotJobError("snapshot job source page not found")
    return _create_or_reuse_current_job(
        session,
        locked_page,
        now=datetime.now(UTC),
    )


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
    while True:
        candidate = session.execute(
            select(
                WordPressSnapshotCaptureJob.id,
                WordPressSnapshotCaptureJob.wordpress_page_id,
            )
            .where(
                WordPressSnapshotCaptureJob.project_id == project_id,
                or_(
                    WordPressSnapshotCaptureJob.state == "queued",
                    and_(
                        WordPressSnapshotCaptureJob.state == "claimed",
                        WordPressSnapshotCaptureJob.claim_expires_at <= requested_at,
                    ),
                ),
            )
            .order_by(
                WordPressSnapshotCaptureJob.created_at,
                WordPressSnapshotCaptureJob.id,
            )
            .limit(1)
        ).one_or_none()
        if candidate is None:
            credential.last_seen_at = requested_at
            return None
        page = session.scalar(
            select(WordPressPage).where(
                WordPressPage.id == candidate.wordpress_page_id,
                WordPressPage.project_id == project_id,
            ).with_for_update()
        )
        job = session.scalar(
            select(WordPressSnapshotCaptureJob)
            .where(WordPressSnapshotCaptureJob.id == candidate.id)
            .with_for_update()
        )
        if job is None:
            continue
        expired = (
            job.state == "claimed"
            and job.claim_expires_at is not None
            and _as_utc(job.claim_expires_at) <= requested_at
        )
        if job.state != "queued" and not expired:
            continue
        if page is None:
            job.state = "cancelled"
            job.cancelled_at = requested_at
            _clear_claim(job)
            session.flush()
            return None

        frozen_identity = _claim_identity(job)
        current_identity = _page_identity(page)
        recovered_drift = False
        if frozen_identity is not None and frozen_identity != current_identity:
            _retire_source_drift(job, requested_at)
            if not page.content_hash:
                session.flush()
                raise SnapshotJobError(
                    "snapshot job source content hash missing",
                    persist_changes=True,
                )
            job = _create_or_reuse_current_job(
                session,
                page,
                now=requested_at,
                exclude_job_id=job.id,
            )
            recovered_drift = True
            if job.state == "claimed":
                credential.last_seen_at = requested_at
                session.flush()
                return None
            frozen_identity = _claim_identity(job)
        elif expired:
            job.state = "queued"
            _clear_claim(job)

        if frozen_identity is None:
            if not page.content_hash:
                session.flush()
                raise SnapshotJobError(
                    "snapshot job source content hash missing",
                    persist_changes=recovered_drift,
                )
            frozen_identity = current_identity
            job.snapshot_result = {CLAIM_IDENTITY_KEY: frozen_identity}

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
            source_post_id=frozen_identity["source_post_id"],
            source_url=frozen_identity["source_url"],
            source_content_hash=frozen_identity["source_content_hash"],
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

    identity = session.execute(
        select(
            WordPressSnapshotCaptureJob.project_id,
            WordPressSnapshotCaptureJob.wordpress_page_id,
        ).where(WordPressSnapshotCaptureJob.id == job_id)
    ).one_or_none()
    if identity is None:
        raise SnapshotJobError("snapshot job not found")
    page = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == identity.wordpress_page_id,
            WordPressPage.project_id == identity.project_id,
        ).with_for_update()
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
    if job.state == "failed" and job.error_code == "source_identity_changed":
        _require_terminal_claim(job, claim_token)
        raise SnapshotJobError(
            "snapshot job source identity changed",
            code="snapshot_source_changed",
        )
    _require_active_claim(job, claim_token, now=now)
    _validate_result(result)
    frozen_identity = _claim_identity(job)
    if frozen_identity is None:
        raise SnapshotJobError("snapshot job source identity missing")
    if page is not None and _page_identity(page) != frozen_identity:
        requested_at = now or datetime.now(UTC)
        _retire_source_drift(job, requested_at)
        if page.content_hash:
            _create_or_reuse_current_job(
                session,
                page,
                now=requested_at,
                exclude_job_id=job.id,
            )
        session.flush()
        raise SnapshotJobError(
            "snapshot job source identity changed",
            code="snapshot_source_changed",
            persist_changes=True,
        )
    if (
        page is None
        or result["source_post_id"] != frozen_identity["source_post_id"]
    ):
        raise SnapshotJobError("snapshot result source page mismatch")
    if (
        result["source_url"] != frozen_identity["source_url"]
    ):
        raise SnapshotJobError("snapshot result source page URL mismatch")
    if (
        result["source_content_hash"] != frozen_identity["source_content_hash"]
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


def _create_or_reuse_current_job(
    session: "Session",
    page: "WordPressPage",
    *,
    now: datetime,
    exclude_job_id: str | None = None,
) -> "WordPressSnapshotCaptureJob":
    from app.domains.wordpress.models import WordPressSnapshotCaptureJob

    statement = (
        select(WordPressSnapshotCaptureJob)
        .where(
            WordPressSnapshotCaptureJob.project_id == page.project_id,
            WordPressSnapshotCaptureJob.wordpress_page_id == page.id,
            WordPressSnapshotCaptureJob.state.in_(("queued", "claimed")),
        )
        .order_by(
            WordPressSnapshotCaptureJob.created_at,
            WordPressSnapshotCaptureJob.id,
        )
        .with_for_update()
    )
    if exclude_job_id is not None:
        statement = statement.where(
            WordPressSnapshotCaptureJob.id != exclude_job_id
        )
    current_identity = _page_identity(page)
    reusable = None
    retired_stale = False
    for existing in session.scalars(statement).all():
        frozen_identity = _claim_identity(existing)
        if frozen_identity is None and not page.content_hash:
            _retire_source_drift(existing, now)
            retired_stale = True
        elif frozen_identity is None or frozen_identity == current_identity:
            reusable = reusable or existing
        else:
            _retire_source_drift(existing, now)
            retired_stale = True
    if not page.content_hash:
        session.flush()
        raise SnapshotJobError(
            "snapshot job source content hash missing",
            persist_changes=retired_stale,
        )
    if reusable is not None:
        session.flush()
        return reusable

    job = WordPressSnapshotCaptureJob(
        id=f"wsnapjob_{uuid4().hex}",
        project_id=page.project_id,
        wordpress_page_id=page.id,
        state="queued",
    )
    session.add(job)
    session.flush()
    return job


def _retire_source_drift(
    job: "WordPressSnapshotCaptureJob",
    now: datetime,
) -> None:
    if job.state == "claimed" and job.claim_token:
        job.state = "failed"
        job.error_code = "source_identity_changed"
        job.error_message = "Source identity changed after the capture claim"
        job.failed_at = now
        job.terminal_claim_token_hash = _hash_claim_token(job.claim_token)
    else:
        job.state = "cancelled"
        job.cancelled_at = now
    _clear_claim(job)


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


def _page_identity(page: "WordPressPage") -> dict[str, int | str | None]:
    return {
        "source_post_id": page.wordpress_object_id,
        "source_url": page.url,
        "source_content_hash": page.content_hash,
    }


def _claim_identity(
    job: "WordPressSnapshotCaptureJob",
) -> dict[str, int | str] | None:
    stored = job.snapshot_result
    if not isinstance(stored, dict):
        return None
    identity = stored.get(CLAIM_IDENTITY_KEY)
    if (
        not isinstance(identity, dict)
        or not isinstance(identity.get("source_post_id"), int)
        or isinstance(identity.get("source_post_id"), bool)
        or identity["source_post_id"] < 1
        or not isinstance(identity.get("source_url"), str)
        or not identity["source_url"]
        or not isinstance(identity.get("source_content_hash"), str)
        or not identity["source_content_hash"]
    ):
        return None
    return {
        "source_post_id": identity["source_post_id"],
        "source_url": identity["source_url"],
        "source_content_hash": identity["source_content_hash"],
    }


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
        raise SnapshotJobError(
            "snapshot job claim invalid",
            code="snapshot_claim_invalid",
        )


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
        raise SnapshotJobError(
            "snapshot job claim invalid",
            code="snapshot_claim_invalid",
        )


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
