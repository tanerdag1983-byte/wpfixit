import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import (
    OPTIMIZATION_SOURCE_ADAPTER_VERSION,
    PageBlueprint,
    is_optimization_source_blueprint,
    ordinary_blueprint_clause,
)
from app.domains.page_blueprints.schemas import SnapshotTextSchema
from app.domains.page_packages.models import (
    PagePackageHandoff,
    PagePackageProposal,
    PagePackageRegenerationCandidate,
    PageProposalStage,
)
from app.domains.projects.models import Project
from app.domains.projects.service import get_membership
from app.domains.wordpress.draft_jobs import cancel_ineligible_draft_jobs
from app.domains.wordpress.models import (
    WordPressConnection,
    WordPressDraftJob,
    WordPressPage,
    WordPressSnapshotCaptureJob,
)

HANDOFF_TTL = timedelta(minutes=10)
REVOCABLE_HANDOFF_STATES = {"issued", "redeemed"}


def existing_page_snapshot_blueprint(
    session: Session,
    page: WordPressPage,
    snapshot_job: WordPressSnapshotCaptureJob,
    page_type: str,
) -> PageBlueprint:
    result = snapshot_job.snapshot_result
    if (
        snapshot_job.state != "completed"
        or snapshot_job.project_id != page.project_id
        or snapshot_job.wordpress_page_id != page.id
        or not isinstance(result, dict)
        or result.get("source_post_id") != page.wordpress_object_id
        or result.get("source_url") != page.url
        or result.get("source_content_hash") != page.content_hash
        or result.get("snapshot_kind") != "optimization_source"
    ):
        raise ValueError("completed snapshot does not match the existing page")
    schema = SnapshotTextSchema.model_validate(result.get("schema"))
    schema.fields_by_id()
    snapshot_id = result.get("snapshot_id")
    snapshot_version = result.get("snapshot_version")
    structure_hash = result.get("structure_hash")
    captured_at = result.get("captured_at")
    if (
        not isinstance(snapshot_id, int)
        or isinstance(snapshot_id, bool)
        or snapshot_id < 1
        or not isinstance(snapshot_version, int)
        or isinstance(snapshot_version, bool)
        or snapshot_version < 1
        or not isinstance(structure_hash, str)
        or not structure_hash
        or not isinstance(captured_at, str)
    ):
        raise ValueError("completed snapshot identity is invalid")
    verified_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    if verified_at.tzinfo is None:
        raise ValueError("completed snapshot identity is invalid")

    existing = session.scalar(
        select(PageBlueprint).where(
            PageBlueprint.project_id == page.project_id,
            PageBlueprint.wordpress_snapshot_id == snapshot_id,
        )
    )
    if existing is not None:
        if (
            existing.source_wordpress_page_id != page.id
            or existing.snapshot_version != snapshot_version
            or existing.structure_hash != structure_hash
            or existing.content_schema != schema.model_dump(mode="python")
            or existing.state != "ready"
        ):
            raise ValueError("completed snapshot identity conflicts")
        return existing

    blueprint = PageBlueprint(
        id=str(
            uuid5(
                NAMESPACE_URL,
                f"wp-fixpilot-existing-page-snapshot:{page.project_id}:{snapshot_id}",
            )
        ),
        project_id=page.project_id,
        name=f"Existing page: {page.title or page.url}"[:160],
        page_type=page_type,
        source_wordpress_page_id=page.id,
        wordpress_blueprint_id=snapshot_id,
        wordpress_snapshot_id=snapshot_id,
        snapshot_version=snapshot_version,
        schema_version="snapshot-text-v1",
        adapter_version=OPTIMIZATION_SOURCE_ADAPTER_VERSION,
        capture_state="ready",
        migration_state="native",
        verified_at=verified_at,
        builder="snapshot",
        seo_plugin="none",
        version=snapshot_version,
        structure_hash=structure_hash,
        content_schema=schema.model_dump(mode="python"),
        state="ready",
        is_default_for_page_type=False,
    )
    session.add(blueprint)
    session.flush()
    return blueprint


def lock_active_default_blueprint(
    session: Session,
    project_id: str,
    page_type: str,
) -> tuple[PageBlueprint | None, bool]:
    selected_id = session.scalar(
        select(PageBlueprint.id).where(
            PageBlueprint.project_id == project_id,
            PageBlueprint.page_type == page_type,
            PageBlueprint.state == "ready",
            PageBlueprint.is_default_for_page_type.is_(True),
            ordinary_blueprint_clause(),
        )
    )
    if selected_id is None:
        return None, False

    for _attempt in range(2):
        candidate = session.scalar(
            select(PageBlueprint)
            .where(
                PageBlueprint.project_id == project_id,
                PageBlueprint.id == selected_id,
            )
            .with_for_update()
        )
        has_successor = (
            candidate is not None
            and session.scalar(
                select(PageBlueprint.id).where(
                    PageBlueprint.project_id == project_id,
                    PageBlueprint.supersedes_id == candidate.id,
                )
            )
            is not None
        )
        if (
            candidate is not None
            and candidate.state == "ready"
            and candidate.is_default_for_page_type
            and not is_optimization_source_blueprint(candidate)
            and not has_successor
        ):
            return candidate, True
        selected_id = session.scalar(
            select(PageBlueprint.id).where(
                PageBlueprint.project_id == project_id,
                PageBlueprint.page_type == page_type,
                PageBlueprint.state == "ready",
                PageBlueprint.is_default_for_page_type.is_(True),
                ordinary_blueprint_clause(),
            )
        )
        if selected_id is None:
            break

    return None, True


@dataclass
class IssuedPagePackageHandoff:
    record: PagePackageHandoff
    raw_code: str


@dataclass
class RedeemedPagePackageHandoff:
    handoff: PagePackageHandoff
    proposal: PagePackageProposal


@dataclass
class AcceptedRegenerationCandidate:
    proposal: PagePackageProposal
    revoked_handoff_ids: list[str]


def accept_regeneration_candidate(
    session: Session,
    candidate_id: str,
    actor_id: str,
) -> PagePackageProposal:
    candidate = session.get(PagePackageRegenerationCandidate, candidate_id)
    if candidate is None:
        raise ValueError("Regeneration candidate not found")
    if candidate.status != "ready":
        raise ValueError("Regeneration candidate is not ready")

    current = session.get(PagePackageProposal, candidate.base_version_id)
    if current is None:
        raise ValueError("Base proposal version not found")
    if (
        not current.is_current
        or current.current_version_id != current.id
        or current.state != "approved"
    ):
        raise ValueError("Base proposal version is no longer current")
    snapshot_replacements: dict[str, str] | None = None
    snapshot_approved_urls: list[str] | None = None
    content_schema = current.config_snapshot.get("content_schema")
    if (
        isinstance(content_schema, dict)
        and content_schema.get("schema_version") == "snapshot-text-v1"
    ):
        replacements = candidate.candidate_package.get("text_replacements")
        approved_urls = candidate.candidate_package.get("approved_urls")
        if (
            not isinstance(replacements, dict)
            or not all(
                isinstance(field_id, str) and isinstance(value, str)
                for field_id, value in replacements.items()
            )
            or not isinstance(approved_urls, list)
            or not all(isinstance(url, str) for url in approved_urls)
        ):
            raise ValueError("Snapshot regeneration candidate is invalid")
        snapshot_replacements = replacements
        snapshot_approved_urls = approved_urls

    job = Job(
        id=str(uuid4()),
        project_id=current.project_id,
        job_type="page_package_regeneration",
        state="completed",
        progress=100,
        checkpoint={"accepted_candidate_id": candidate.id},
    )
    next_version_id = str(uuid4())

    next_version = PagePackageProposal(
        id=next_version_id,
        project_id=current.project_id,
        opportunity_id=current.opportunity_id,
        job_id=job.id,
        state="proposed",
        proposal_group_id=current.proposal_group_id,
        version_number=current.version_number + 1,
        parent_version_id=current.id,
        current_version_id=next_version_id,
        is_current=True,
        generation_mode=candidate.generation_mode,
        target_block_id=candidate.target_block_id,
        user_instruction=candidate.instruction,
        source_wordpress_page_id=current.source_wordpress_page_id,
        blueprint_id=current.blueprint_id,
        blueprint_version=current.blueprint_version,
        blueprint_structure_hash=current.blueprint_structure_hash,
        package=(
            {"text_replacements": snapshot_replacements}
            if snapshot_replacements is not None
            else candidate.candidate_package
        ),
        rendered_html=candidate.candidate_rendered_html,
        config_snapshot=current.config_snapshot,
        provider=candidate.provider,
        model=candidate.model,
        prompt_version=candidate.prompt_version,
        input_tokens=candidate.input_tokens,
        output_tokens=candidate.output_tokens,
        proposed_by=actor_id,
    )

    current.is_current = False
    current.current_version_id = next_version_id
    _revoke_open_handoffs(session, current.id)
    candidate.status = "accepted"
    session.query(PagePackageProposal).filter(
        PagePackageProposal.proposal_group_id == current.proposal_group_id
    ).update(
        {PagePackageProposal.current_version_id: next_version_id},
        synchronize_session="fetch",
    )
    session.add_all([job, next_version])
    if snapshot_replacements is not None and snapshot_approved_urls is not None:
        session.add_all(
            [
                PageProposalStage(
                    proposal_version_id=next_version_id,
                    name="template",
                    state="ready",
                    result={},
                    errors={},
                    completed_at=datetime.now(UTC),
                ),
                PageProposalStage(
                    proposal_version_id=next_version_id,
                    name="text",
                    state="ready",
                    result={
                        "text_replacements": {
                            field_id: {"value": value}
                            for field_id, value in snapshot_replacements.items()
                        }
                    },
                    errors={},
                    completed_at=datetime.now(UTC),
                ),
                PageProposalStage(
                    proposal_version_id=next_version_id,
                    name="validation",
                    state="ready",
                    result={
                        "text_replacements": snapshot_replacements,
                        "approved_urls": snapshot_approved_urls,
                        "field_errors": {},
                        "blocking_field_ids": [],
                        "ignored_field_ids": [],
                        "missing_required_field_ids": [],
                    },
                    errors={},
                    completed_at=datetime.now(UTC),
                ),
            ]
        )
    cancel_ineligible_draft_jobs(
        session,
        current.project_id,
        current.proposal_group_id,
        eligible_proposal_version_id=next_version_id,
    )
    session.commit()
    session.refresh(next_version)
    return next_version


def accept_regeneration_candidate_with_revocations(
    session: Session,
    candidate_id: str,
    actor_id: str,
    *,
    expected_project_id: str | None = None,
) -> AcceptedRegenerationCandidate:
    candidate = session.get(PagePackageRegenerationCandidate, candidate_id)
    if candidate is None:
        raise ValueError("Regeneration candidate not found")
    if expected_project_id is not None:
        proposal = session.get(PagePackageProposal, candidate.base_version_id)
        if proposal is None or proposal.project_id != expected_project_id:
            raise ValueError("Regeneration candidate not found")
    revoked_handoff_ids = open_handoff_ids(session, candidate.base_version_id)
    proposal = accept_regeneration_candidate(session, candidate_id, actor_id)
    return AcceptedRegenerationCandidate(
        proposal=proposal,
        revoked_handoff_ids=revoked_handoff_ids,
    )


def issue_page_package_handoff(
    session: Session,
    proposal: PagePackageProposal,
    actor_id: str,
) -> IssuedPagePackageHandoff:
    locked_proposal = session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == proposal.id)
        .with_for_update()
    )
    if locked_proposal is None:
        raise ValueError("Proposal version is no longer available")
    proposal = locked_proposal
    _require_manual_handoff_path(proposal)
    if (
        proposal.state != "approved"
        or not proposal.is_current
        or not proposal.approved_by
        or proposal.approved_at is None
    ):
        raise ValueError("Only the approved current proposal version can be handed off")
    outbound_job = session.scalar(
        select(WordPressDraftJob.id).where(
            WordPressDraftJob.proposal_version_id == proposal.id,
            WordPressDraftJob.state.in_(("queued", "claimed", "completed")),
        )
    )
    if outbound_job is not None:
        raise ValueError("Outbound WordPress delivery already exists")
    _require_handoff_manager(session, proposal, actor_id)

    connection = session.scalar(
        select(WordPressConnection).where(
            WordPressConnection.project_id == proposal.project_id
        )
    )
    if connection is None:
        raise ValueError("WordPress connection not found")

    raw_code = secrets.token_urlsafe(24)
    handoff = PagePackageHandoff(
        id=str(uuid4()),
        project_id=proposal.project_id,
        proposal_version_id=proposal.id,
        wordpress_connection_id=connection.id,
        code_hash=_hash_handoff_code(raw_code),
        issued_by=actor_id,
        state="issued",
        expires_at=datetime.now(UTC) + HANDOFF_TTL,
    )
    session.add(handoff)
    session.commit()
    session.refresh(handoff)
    return IssuedPagePackageHandoff(record=handoff, raw_code=raw_code)


def create_regeneration_candidate(
    session: Session,
    proposal: PagePackageProposal,
    *,
    mode: str,
    target_block_id: str | None,
    instruction: str | None,
    candidate_package: dict,
    candidate_rendered_html: str,
    provider: str | None,
    model: str | None,
    prompt_version: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    status: str = "generating",
) -> PagePackageRegenerationCandidate:
    candidate = PagePackageRegenerationCandidate(
        id=str(uuid4()),
        proposal_group_id=proposal.proposal_group_id,
        base_version_id=proposal.id,
        generation_mode=mode,
        target_block_id=target_block_id,
        instruction=instruction,
        candidate_package=candidate_package,
        candidate_rendered_html=candidate_rendered_html,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        status=status,
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def discard_regeneration_candidate(
    session: Session,
    candidate_id: str,
    *,
    expected_project_id: str | None = None,
) -> PagePackageRegenerationCandidate:
    candidate = session.get(PagePackageRegenerationCandidate, candidate_id)
    if candidate is None:
        raise ValueError("Regeneration candidate not found")
    if expected_project_id is not None:
        proposal = session.get(PagePackageProposal, candidate.base_version_id)
        if proposal is None or proposal.project_id != expected_project_id:
            raise ValueError("Regeneration candidate not found")
    candidate.status = "discarded"
    session.commit()
    session.refresh(candidate)
    return candidate


def redeem_page_package_handoff(
    session: Session,
    code: str,
    site_url: str,
    wordpress_user_id: int,
    *,
    expected_project_id: str | None = None,
) -> RedeemedPagePackageHandoff:
    del wordpress_user_id
    normalized_site_url = site_url.rstrip("/")
    candidate = session.scalar(
        select(PagePackageHandoff).where(
            PagePackageHandoff.code_hash == _hash_handoff_code(code)
        )
    )
    if candidate is None:
        raise ValueError("Handoff code is invalid")
    proposal = session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == candidate.proposal_version_id)
        .with_for_update()
    )
    handoff = session.scalar(
        select(PagePackageHandoff)
        .where(PagePackageHandoff.id == candidate.id)
        .with_for_update()
    )
    if handoff is None:
        raise ValueError("Handoff code is invalid")
    if expected_project_id is not None and handoff.project_id != expected_project_id:
        raise ValueError("Handoff code is invalid")
    if proposal is None:
        raise ValueError("Proposal version is no longer available")
    _require_manual_handoff_path(proposal)

    connection = session.get(WordPressConnection, handoff.wordpress_connection_id)
    if connection is None:
        raise ValueError("WordPress connection not found")
    normalized_connection_url = connection.site_url.rstrip("/")
    if normalized_connection_url != normalized_site_url:
        raise ValueError("WordPress site mismatch")

    if handoff.state == "completed":
        if proposal is None:
            raise ValueError("Proposal version is no longer available")
        return RedeemedPagePackageHandoff(handoff=handoff, proposal=proposal)

    if handoff.state == "redeemed":
        if (
            proposal is None
            or proposal.state != "draft_in_progress"
            or not proposal.is_current
        ):
            raise ValueError("Proposal version is no longer eligible")
        return RedeemedPagePackageHandoff(handoff=handoff, proposal=proposal)

    if handoff.state != "issued":
        raise ValueError("Handoff code is not available")
    if handoff.expires_at <= _utcnow_like(handoff.expires_at):
        handoff.state = "expired"
        session.commit()
        raise ValueError("Handoff code expired")

    if proposal is None or proposal.state != "approved" or not proposal.is_current:
        raise ValueError("Proposal version is no longer eligible")

    outbound_job = session.scalar(
        select(WordPressDraftJob.id).where(
            WordPressDraftJob.proposal_version_id == proposal.id,
            WordPressDraftJob.state.in_(("queued", "claimed", "completed")),
        )
    )
    if outbound_job is not None:
        raise ValueError("Outbound WordPress delivery already exists")
    proposal.state = "draft_in_progress"
    handoff.state = "redeemed"
    handoff.redeemed_at = datetime.now(UTC)
    session.commit()
    session.refresh(handoff)
    return RedeemedPagePackageHandoff(handoff=handoff, proposal=proposal)


def complete_page_package_handoff(
    session: Session,
    handoff_id: str,
    *,
    wordpress_object_id: int,
    edit_url: str,
    expected_project_id: str | None = None,
) -> PagePackageHandoff:
    candidate = session.get(PagePackageHandoff, handoff_id)
    if candidate is None:
        raise ValueError("Handoff not found")
    proposal = session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == candidate.proposal_version_id)
        .with_for_update()
    )
    handoff = session.scalar(
        select(PagePackageHandoff)
        .where(PagePackageHandoff.id == handoff_id)
        .with_for_update()
    )
    if handoff is None:
        raise ValueError("Handoff not found")
    if expected_project_id is not None and handoff.project_id != expected_project_id:
        raise ValueError("Handoff not found")
    if proposal is None:
        raise ValueError("Proposal version is no longer eligible")
    _require_manual_handoff_path(proposal)
    if handoff.state == "completed":
        return handoff
    if handoff.state != "redeemed":
        raise ValueError("Handoff is not redeemable")

    if proposal.state == "draft_in_progress":
        if not proposal.is_current or not proposal.approved_by:
            raise ValueError("Proposal version is no longer eligible")
    elif proposal.state == "draft_created":
        if proposal.wordpress_object_id != wordpress_object_id:
            raise ValueError("Proposal already has another WordPress draft")
        return handoff
    else:
        raise ValueError("Proposal version is no longer eligible")

    handoff.state = "completed"
    handoff.completed_at = datetime.now(UTC)
    handoff.wordpress_object_id = wordpress_object_id
    handoff.wordpress_edit_url = edit_url
    proposal.state = "draft_created"
    proposal.wordpress_object_id = wordpress_object_id
    proposal.wordpress_edit_url = edit_url
    session.commit()
    session.refresh(handoff)
    return handoff


def revoke_page_package_handoff(
    session: Session,
    handoff_id: str,
    *,
    expected_project_id: str | None = None,
) -> PagePackageHandoff:
    candidate = session.get(PagePackageHandoff, handoff_id)
    if candidate is None:
        raise ValueError("Handoff not found")
    session.scalar(
        select(PagePackageProposal)
        .where(PagePackageProposal.id == candidate.proposal_version_id)
        .with_for_update()
    )
    handoff = session.scalar(
        select(PagePackageHandoff)
        .where(PagePackageHandoff.id == handoff_id)
        .with_for_update()
    )
    if handoff is None:
        raise ValueError("Handoff not found")
    if expected_project_id is not None and handoff.project_id != expected_project_id:
        raise ValueError("Handoff not found")
    if handoff.state == "completed":
        raise ValueError("Completed handoff cannot be revoked")
    if handoff.state == "redeemed":
        raise ValueError("Redeemed handoff cannot be revoked")
    if handoff.state != "revoked":
        handoff.state = "revoked"
        handoff.revoked_at = datetime.now(UTC)
        session.commit()
        session.refresh(handoff)
    return handoff


def open_handoff_ids(session: Session, proposal_version_id: str) -> list[str]:
    return [
        handoff.id
        for handoff in session.scalars(
            select(PagePackageHandoff).where(
                PagePackageHandoff.proposal_version_id == proposal_version_id,
                PagePackageHandoff.state.in_(tuple(REVOCABLE_HANDOFF_STATES)),
            )
        ).all()
    ]


def _revoke_open_handoffs(session: Session, proposal_version_id: str) -> None:
    now = datetime.now(UTC)
    handoffs = session.scalars(
        select(PagePackageHandoff).where(
            PagePackageHandoff.proposal_version_id == proposal_version_id,
            PagePackageHandoff.state.in_(tuple(REVOCABLE_HANDOFF_STATES)),
        )
    ).all()
    for handoff in handoffs:
        handoff.state = "revoked"
        handoff.revoked_at = now


def _hash_handoff_code(raw_code: str) -> str:
    return hashlib.sha256(raw_code.encode("utf-8")).hexdigest()


def _require_manual_handoff_path(proposal: PagePackageProposal) -> None:
    if proposal.source_wordpress_page_id is not None:
        raise ValueError("Existing-page drafts require the outbound draft-job path")


def _utcnow_like(value: datetime) -> datetime:
    if value.tzinfo is None:
        return datetime.now(UTC).replace(tzinfo=None)
    return datetime.now(UTC)


def _require_handoff_manager(
    session: Session,
    proposal: PagePackageProposal,
    actor_id: str,
) -> None:
    project = session.get(Project, proposal.project_id)
    if project is None:
        raise ValueError("Project not found")
    membership = get_membership(session, actor_id, project.organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise PermissionError("Only organization owners or admins can issue handoffs")
