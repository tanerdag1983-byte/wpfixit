import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.domains.page_packages.models import PagePackageProposal
    from app.domains.wordpress.models import WordPressDraftJob

JOB_CONTRACT_VERSION = "wordpress-draft-job-v1"
CLAIM_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class ClaimedDraftJob:
    job: "WordPressDraftJob"
    claim_token: str


def new_project_key() -> tuple[str, str]:
    raw = "wpfx_" + secrets.token_urlsafe(32)
    return raw, hash_project_key(raw)


def hash_project_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def hash_draft_job_payload(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_site_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() != "https":
        raise ValueError("WordPress site URL must use HTTPS")
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("WordPress site URL must be an HTTPS origin")
    host = parsed.hostname.casefold()
    if ":" in host:
        host = f"[{host}]"
    authority = host if parsed.port in {None, 443} else f"{host}:{parsed.port}"
    return f"https://{authority}"


def create_or_get_draft_job(
    session: "Session", proposal: "PagePackageProposal"
) -> "WordPressDraftJob":
    from app.domains.page_packages.models import PagePackageHandoff, PagePackageProposal
    from app.domains.wordpress.models import WordPressDraftJob

    locked_proposal = session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == proposal.id)
        .with_for_update()
    )
    if locked_proposal is None:
        raise ValueError("draft job proposal not found")
    proposal = locked_proposal
    existing = session.scalar(
        select(WordPressDraftJob).where(
            WordPressDraftJob.proposal_version_id == proposal.id
        )
    )
    if existing is not None and existing.state not in {"failed", "cancelled"}:
        return existing
    if (
        proposal.state != "approved"
        or not proposal.approved_by
        or not proposal.is_current
        or proposal.current_version_id != proposal.id
    ):
        raise ValueError("draft job requires the current approved proposal version")
    open_handoffs = session.scalars(
        select(PagePackageHandoff)
        .where(
            PagePackageHandoff.proposal_version_id == proposal.id,
            PagePackageHandoff.state.in_(("issued", "redeemed")),
        )
        .with_for_update()
    ).all()
    revoked_at = datetime.now(UTC)
    if any(
        handoff.state == "redeemed"
        and _as_utc(handoff.expires_at) > revoked_at
        for handoff in open_handoffs
    ):
        raise ValueError("manual handoff is already in progress")
    for handoff in open_handoffs:
        handoff.state = "revoked"
        handoff.revoked_at = revoked_at

    if existing is not None:
        existing.state = "queued"
        existing.terminal_claim_token_hash = None
        existing.error_code = None
        existing.error_message = None
        existing.failed_at = None
        existing.cancelled_at = None
        return existing

    payload = _draft_job_payload(session, proposal)
    job = WordPressDraftJob(
        id=f"wjob_{uuid4().hex}",
        project_id=proposal.project_id,
        proposal_version_id=proposal.id,
        contract_version=JOB_CONTRACT_VERSION,
        state="queued",
        payload=payload,
        payload_hash=hash_draft_job_payload(payload),
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
        return job
    except IntegrityError:
        existing = session.scalar(
            select(WordPressDraftJob).where(
                WordPressDraftJob.proposal_version_id == proposal.id
            )
        )
        if existing is None:
            raise
        return existing


def claim_next_draft_job(
    session: "Session",
    project_id: str,
    site_url: str,
    *,
    now: datetime | None = None,
) -> ClaimedDraftJob | None:
    from app.domains.wordpress.models import (
        WordPressDraftJob,
        WordPressOutboundCredential,
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
        raise ValueError("wordpress_outbound_credential_invalid")

    session.execute(
        update(WordPressDraftJob)
        .where(
            WordPressDraftJob.project_id == project_id,
            WordPressDraftJob.state == "claimed",
            WordPressDraftJob.claim_expires_at <= requested_at,
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
    candidate = session.scalar(
        select(WordPressDraftJob)
        .where(
            WordPressDraftJob.project_id == project_id,
            WordPressDraftJob.state == "queued",
        )
        .order_by(WordPressDraftJob.created_at, WordPressDraftJob.id)
        .limit(1)
    )
    if candidate is None:
        credential.last_seen_at = requested_at
        return None

    from app.domains.page_packages.models import PagePackageHandoff, PagePackageProposal

    proposal = session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == candidate.proposal_version_id)
        .with_for_update()
    )
    job = session.scalar(
        select(WordPressDraftJob)
        .where(
            WordPressDraftJob.id == candidate.id,
            WordPressDraftJob.state == "queued",
        )
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    if proposal is None or not proposal.is_current or not proposal.approved_by:
        job.state = "cancelled"
        job.cancelled_at = requested_at
        session.flush()
        return None
    if proposal.state not in {"approved", "draft_in_progress"}:
        job.state = "cancelled"
        job.cancelled_at = requested_at
        session.flush()
        return None
    redeemed_handoff = session.scalar(
        select(PagePackageHandoff.id).where(
            PagePackageHandoff.proposal_version_id == proposal.id,
            PagePackageHandoff.state == "redeemed",
        )
    )
    if redeemed_handoff is not None:
        return None
    issued_handoffs = session.scalars(
        select(PagePackageHandoff)
        .where(
            PagePackageHandoff.proposal_version_id == proposal.id,
            PagePackageHandoff.state == "issued",
        )
        .with_for_update()
    ).all()
    for handoff in issued_handoffs:
        handoff.state = "revoked"
        handoff.revoked_at = requested_at

    claim_token = secrets.token_urlsafe(32)
    proposal.state = "draft_in_progress"
    job.state = "claimed"
    job.claim_token = claim_token
    job.claimed_at = requested_at
    job.claim_expires_at = requested_at + CLAIM_TTL
    job.attempt_count += 1
    credential.last_seen_at = requested_at
    session.flush()
    return ClaimedDraftJob(job=job, claim_token=claim_token)


def complete_draft_job(
    session: "Session",
    job_id: str,
    claim_token: str,
    *,
    wordpress_object_id: int,
    wordpress_edit_url: str | None,
    now: datetime | None = None,
) -> "WordPressDraftJob":
    from app.domains.wordpress.models import WordPressDraftJob

    candidate = session.get(WordPressDraftJob, job_id)
    if candidate is None:
        raise ValueError("draft_job_not_found")
    _lock_job_proposal(session, candidate)
    job = session.scalar(
        select(WordPressDraftJob)
        .where(WordPressDraftJob.id == job_id)
        .with_for_update()
    )
    if job is None:
        raise ValueError("draft_job_not_found")
    if job.state == "completed":
        _require_terminal_claim(job, claim_token)
        if (
            job.wordpress_object_id != wordpress_object_id
            or job.wordpress_edit_url != wordpress_edit_url
        ):
            raise ValueError("draft_job_result_conflict")
        return job
    _require_active_claim(job, claim_token, now=now)
    if wordpress_object_id <= 0:
        raise ValueError("wordpress_object_id_invalid")

    job.state = "completed"
    job.wordpress_object_id = wordpress_object_id
    job.wordpress_edit_url = wordpress_edit_url
    job.completed_at = now or datetime.now(UTC)
    job.terminal_claim_token_hash = hash_project_key(claim_token)
    _clear_claim(job)
    _mark_proposal_draft_created(session, job)
    session.flush()
    return job


def fail_draft_job(
    session: "Session",
    job_id: str,
    claim_token: str,
    *,
    error_code: str,
    error_message: str,
    now: datetime | None = None,
) -> "WordPressDraftJob":
    from app.domains.wordpress.models import WordPressDraftJob

    if not error_code or len(error_code) > 64:
        raise ValueError("draft_job_error_code_invalid")
    if len(error_message) > 500:
        raise ValueError("draft_job_error_message_invalid")
    candidate = session.get(WordPressDraftJob, job_id)
    if candidate is None:
        raise ValueError("draft_job_not_found")
    _lock_job_proposal(session, candidate)
    job = session.scalar(
        select(WordPressDraftJob)
        .where(WordPressDraftJob.id == job_id)
        .with_for_update()
    )
    if job is None:
        raise ValueError("draft_job_not_found")
    if job.state == "failed":
        _require_terminal_claim(job, claim_token)
        if job.error_code != error_code or job.error_message != error_message:
            raise ValueError("draft_job_result_conflict")
        return job
    _require_active_claim(job, claim_token, now=now)
    job.state = "failed"
    job.error_code = error_code
    job.error_message = error_message
    job.failed_at = now or datetime.now(UTC)
    job.terminal_claim_token_hash = hash_project_key(claim_token)
    _clear_claim(job)
    _release_proposal_delivery_lease(session, job)
    session.flush()
    return job


def cancel_ineligible_draft_jobs(
    session: "Session",
    project_id: str,
    proposal_group_id: str,
    *,
    eligible_proposal_version_id: str | None,
    now: datetime | None = None,
) -> int:
    from app.domains.page_packages.models import PagePackageProposal
    from app.domains.wordpress.models import WordPressDraftJob

    jobs = session.scalars(
        select(WordPressDraftJob)
        .join(
            PagePackageProposal,
            PagePackageProposal.id == WordPressDraftJob.proposal_version_id,
        )
        .where(
            WordPressDraftJob.project_id == project_id,
            PagePackageProposal.project_id == project_id,
            PagePackageProposal.proposal_group_id == proposal_group_id,
            WordPressDraftJob.state == "queued",
            WordPressDraftJob.proposal_version_id
            != (eligible_proposal_version_id or ""),
        )
        .with_for_update()
    ).all()
    cancelled_at = now or datetime.now(UTC)
    for job in jobs:
        job.state = "cancelled"
        job.cancelled_at = cancelled_at
        _clear_claim(job)
    session.flush()
    return len(jobs)


def _draft_job_payload(
    session: "Session", proposal: "PagePackageProposal"
) -> dict:
    from app.domains.page_blueprints.models import PageBlueprint
    from app.domains.page_blueprints.schemas import BlueprintSchema
    from app.domains.page_packages.generation import validate_blueprint_replacements
    from app.domains.page_packages.schemas import (
        GeneratedBlueprintPackage,
        PagePackageContext,
    )
    from app.domains.wordpress.models import WordPressPage

    if (
        proposal.blueprint_id is None
        or proposal.blueprint_version is None
        or proposal.blueprint_structure_hash is None
    ):
        raise ValueError("draft job requires an immutable blueprint identity")
    blueprint = session.scalar(
        select(PageBlueprint).where(
            PageBlueprint.project_id == proposal.project_id,
            PageBlueprint.id == proposal.blueprint_id,
            PageBlueprint.version == proposal.blueprint_version,
            PageBlueprint.structure_hash == proposal.blueprint_structure_hash,
        )
    )
    if (
        blueprint is None
        or blueprint.state != "ready"
        or blueprint.content_schema
        != proposal.config_snapshot.get("content_schema")
    ):
        raise ValueError("draft job blueprint snapshot is stale")

    package = GeneratedBlueprintPackage.model_validate(proposal.package)
    schema = BlueprintSchema.model_validate(blueprint.content_schema)
    url_field_ids = {
        field.id
        for block in schema.blocks
        for field in block.fields
        if field.value_type == "url"
    }
    trusted_internal_urls = set(
        session.scalars(
            select(WordPressPage.url).where(
                WordPressPage.project_id == proposal.project_id
            )
        ).all()
    )
    trusted_cta_urls = {
        field.current_value
        for block in schema.blocks
        for field in block.fields
        if field.value_type == "url" and field.current_value
    }
    context = PagePackageContext(
        keyword=package.focus_keyword,
        company_context="approved proposal",
        project_domain="https://wordpress.invalid",
        internal_link_candidates=[
            link for link in package.internal_links if link.url in trusted_internal_urls
        ],
        template_slots={},
        approved_cta_urls=sorted(trusted_cta_urls),
        blueprint_schema=schema,
    )
    validate_blueprint_replacements(package, context)
    approved_urls = sorted(
        {link.url for link in package.internal_links}
        | {
            replacement.value
            for replacement in package.replacements
            if replacement.field_id in url_field_ids
        }
    )
    return {
        "proposal_version_id": proposal.id,
        "wordpress_blueprint_id": blueprint.wordpress_blueprint_id,
        "expected_version": proposal.blueprint_version,
        "expected_structure_hash": proposal.blueprint_structure_hash,
        "idempotency_key": proposal.id,
        "replacements": {
            replacement.field_id: replacement.value
            for replacement in package.replacements
        },
        "approved_urls": approved_urls,
        "seo": {
            "title": package.seo_title,
            "description": package.meta_description,
            "keyword": package.focus_keyword,
        },
    }


def _require_active_claim(
    job: "WordPressDraftJob", claim_token: str, *, now: datetime | None
) -> None:
    current_time = now or datetime.now(UTC)
    if (
        job.state != "claimed"
        or not secrets.compare_digest(job.claim_token or "", claim_token)
        or job.claim_expires_at is None
        or _as_utc(job.claim_expires_at) <= current_time
    ):
        raise ValueError("draft_job_claim_invalid")


def _clear_claim(job: "WordPressDraftJob") -> None:
    job.claim_token = None
    job.claim_expires_at = None
    job.claimed_at = None


def _require_terminal_claim(job: "WordPressDraftJob", claim_token: str) -> None:
    if not secrets.compare_digest(
        job.terminal_claim_token_hash or "", hash_project_key(claim_token)
    ):
        raise ValueError("draft_job_claim_invalid")


def _mark_proposal_draft_created(
    session: "Session", job: "WordPressDraftJob"
) -> None:
    from app.domains.page_packages.models import PagePackageHandoff, PagePackageProposal

    proposal = session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == job.proposal_version_id)
        .with_for_update()
    )
    if proposal is None:
        raise ValueError("draft_job_proposal_not_found")
    if (
        not proposal.is_current
        or proposal.state != "draft_in_progress"
        or proposal.wordpress_object_id not in {None, job.wordpress_object_id}
    ):
        raise ValueError("draft_job_result_conflict")
    proposal.state = "draft_created"
    proposal.wordpress_object_id = job.wordpress_object_id
    proposal.wordpress_edit_url = job.wordpress_edit_url
    now = datetime.now(UTC)
    open_handoffs = session.scalars(
        select(PagePackageHandoff)
        .where(
            PagePackageHandoff.proposal_version_id == proposal.id,
            PagePackageHandoff.state.in_(("issued", "redeemed")),
        )
        .with_for_update()
    ).all()
    for handoff in open_handoffs:
        handoff.state = "revoked"
        handoff.revoked_at = now


def _release_proposal_delivery_lease(
    session: "Session", job: "WordPressDraftJob"
) -> None:
    from app.domains.page_packages.models import PagePackageProposal

    proposal = session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == job.proposal_version_id)
        .with_for_update()
    )
    if (
        proposal is not None
        and proposal.is_current
        and proposal.state == "draft_in_progress"
    ):
        proposal.state = "approved"


def _lock_job_proposal(session: "Session", job: "WordPressDraftJob") -> None:
    from app.domains.page_packages.models import PagePackageProposal

    proposal = session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == job.proposal_version_id)
        .with_for_update()
    )
    if proposal is None:
        raise ValueError("draft_job_proposal_not_found")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
