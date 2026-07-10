import secrets

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_packages.models import PagePackageProposal
from app.domains.wordpress.draft_jobs import hash_project_key, new_project_key
from app.domains.wordpress.models import (
    WordPressDraftJob,
    WordPressOutboundCredential,
)


@pytest.fixture
def approved_proposal(session, projects) -> PagePackageProposal:
    opportunity = KeywordOpportunity(
        id="draft-job-opportunity",
        project_id=projects.member_project.id,
        keyword="dsg versnellingsbak reviseren",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=[],
        source="dataforseo",
        raw_payload={},
    )
    generation_job = Job(
        id="draft-job-generation",
        project_id=projects.member_project.id,
        job_type="page_package_generation",
    )
    proposal = PagePackageProposal(
        id="approved-proposal",
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id=generation_job.id,
        proposal_group_id="approved-proposal",
        current_version_id="approved-proposal",
        state="approved",
        package={},
        rendered_html="",
        config_snapshot={},
        proposed_by=projects.member.id,
        approved_by=projects.member.id,
    )
    session.add_all([opportunity, generation_job, proposal])
    session.commit()
    return proposal


def test_project_key_is_256_bit_and_only_hash_is_persisted(session, projects) -> None:
    raw, digest = new_project_key()

    assert len(secrets.token_urlsafe(32)) <= len(raw)
    assert raw != digest

    credential = WordPressOutboundCredential(
        id="credential-1",
        project_id=projects.member_project.id,
        key_hash=digest,
        site_url="https://member.example",
    )
    session.add(credential)
    session.commit()

    persisted = session.get(WordPressOutboundCredential, "credential-1")
    assert persisted is not None
    assert persisted.key_hash == hash_project_key(raw)


def test_one_draft_job_per_proposal_version(session, approved_proposal) -> None:
    session.add(
        WordPressDraftJob(
            id="job-1",
            project_id=approved_proposal.project_id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v1",
            state="queued",
            payload_hash="hash",
            payload={},
        )
    )
    session.commit()

    session.add(
        WordPressDraftJob(
            id="job-2",
            project_id=approved_proposal.project_id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v1",
            state="queued",
            payload_hash="hash",
            payload={},
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_draft_job_rejects_an_unknown_state(session, approved_proposal) -> None:
    session.add(
        WordPressDraftJob(
            id="job-invalid-state",
            project_id=approved_proposal.project_id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v1",
            state="published",
            payload_hash="hash",
            payload={},
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_draft_job_requires_claim_token_and_expiry_together(
    session, approved_proposal
) -> None:
    session.add(
        WordPressDraftJob(
            id="job-incomplete-claim",
            project_id=approved_proposal.project_id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v1",
            state="queued",
            payload_hash="hash",
            payload={},
            claim_token="claim-token",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
