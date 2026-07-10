import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.jobs.models import Job
from app.domains.page_packages.models import (
    PagePackageHandoff,
    PagePackageProposal,
    PagePackageRegenerationCandidate,
)
from app.domains.projects.models import Project
from app.domains.projects.service import get_membership
from app.domains.wordpress.models import WordPressConnection

HANDOFF_TTL = timedelta(minutes=10)
REVOCABLE_HANDOFF_STATES = {"issued", "redeemed"}


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
    if not current.is_current or current.current_version_id != current.id:
        raise ValueError("Base proposal version is no longer current")

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
        blueprint_id=current.blueprint_id,
        blueprint_version=current.blueprint_version,
        blueprint_structure_hash=current.blueprint_structure_hash,
        package=candidate.candidate_package,
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
    if (
        proposal.state != "approved"
        or not proposal.is_current
        or not proposal.approved_by
        or proposal.approved_at is None
    ):
        raise ValueError("Only the approved current proposal version can be handed off")
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
    handoff = session.scalar(
        select(PagePackageHandoff).where(
            PagePackageHandoff.code_hash == _hash_handoff_code(code)
        ).with_for_update()
    )
    if handoff is None:
        raise ValueError("Handoff code is invalid")
    if expected_project_id is not None and handoff.project_id != expected_project_id:
        raise ValueError("Handoff code is invalid")

    connection = session.get(WordPressConnection, handoff.wordpress_connection_id)
    if connection is None:
        raise ValueError("WordPress connection not found")
    normalized_connection_url = connection.site_url.rstrip("/")
    if normalized_connection_url != normalized_site_url:
        raise ValueError("WordPress site mismatch")

    if handoff.state == "completed":
        proposal = session.get(PagePackageProposal, handoff.proposal_version_id)
        if proposal is None:
            raise ValueError("Proposal version is no longer available")
        return RedeemedPagePackageHandoff(handoff=handoff, proposal=proposal)

    if handoff.state == "redeemed":
        proposal = session.get(PagePackageProposal, handoff.proposal_version_id)
        if proposal is None or proposal.state != "approved" or not proposal.is_current:
            raise ValueError("Proposal version is no longer eligible")
        return RedeemedPagePackageHandoff(handoff=handoff, proposal=proposal)

    if handoff.state != "issued":
        raise ValueError("Handoff code is not available")
    if handoff.expires_at <= _utcnow_like(handoff.expires_at):
        handoff.state = "expired"
        session.commit()
        raise ValueError("Handoff code expired")

    proposal = session.get(PagePackageProposal, handoff.proposal_version_id)
    if proposal is None or proposal.state != "approved" or not proposal.is_current:
        raise ValueError("Proposal version is no longer eligible")

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
    handoff = session.get(PagePackageHandoff, handoff_id)
    if handoff is None:
        raise ValueError("Handoff not found")
    if expected_project_id is not None and handoff.project_id != expected_project_id:
        raise ValueError("Handoff not found")
    if handoff.state == "completed":
        return handoff
    if handoff.state != "redeemed":
        raise ValueError("Handoff is not redeemable")

    proposal = session.get(PagePackageProposal, handoff.proposal_version_id)
    if proposal is None:
        raise ValueError("Proposal version is no longer eligible")
    if proposal.state == "approved":
        if (
            not proposal.is_current
            or not proposal.approved_by
            or proposal.approved_at is None
        ):
            raise ValueError("Proposal version is no longer eligible")
    elif proposal.state != "draft_created":
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
    handoff = session.get(PagePackageHandoff, handoff_id)
    if handoff is None:
        raise ValueError("Handoff not found")
    if expected_project_id is not None and handoff.project_id != expected_project_id:
        raise ValueError("Handoff not found")
    if handoff.state == "completed":
        raise ValueError("Completed handoff cannot be revoked")
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
