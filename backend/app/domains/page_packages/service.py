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


def issue_page_package_handoff(
    session: Session,
    proposal: PagePackageProposal,
    actor_id: str,
) -> IssuedPagePackageHandoff:
    if proposal.state != "approved" or not proposal.is_current:
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
