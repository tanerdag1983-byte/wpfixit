import re
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_packages.models import PagePackageProposal
from app.domains.wordpress.draft_jobs import (
    hash_draft_job_payload,
    hash_project_key,
    new_project_key,
)
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

    assert raw.startswith("wpfx_")
    assert len(raw.removeprefix("wpfx_")) == len(secrets.token_urlsafe(32))
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
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


def test_credential_normalizes_https_site_url(session, projects) -> None:
    credential = WordPressOutboundCredential(
        id="credential-normalized",
        project_id=projects.member_project.id,
        key_hash="a" * 64,
        site_url="HTTPS://MEMBER.EXAMPLE:443/",
    )
    session.add(credential)
    session.commit()

    assert credential.site_url == "https://member.example"


def test_credential_rejects_non_https_site_url(session, projects) -> None:
    session.add(
        WordPressOutboundCredential(
            id="credential-insecure",
            project_id=projects.member_project.id,
            key_hash="a" * 64,
            site_url="http://member.example",
        )
    )

    with pytest.raises(ValueError, match="HTTPS"):
        session.flush()


def test_one_draft_job_per_proposal_version(session, approved_proposal) -> None:
    session.add(
        WordPressDraftJob(
            id="job-1",
            project_id=approved_proposal.project_id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v1",
            state="queued",
            payload_hash=hash_draft_job_payload({}),
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
            payload_hash=hash_draft_job_payload({}),
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
            payload_hash=hash_draft_job_payload({}),
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
            state="claimed",
            payload_hash=hash_draft_job_payload({}),
            payload={},
            claim_token="claim-token",
            claim_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_non_claimed_job_rejects_claim_fields(session, approved_proposal) -> None:
    session.add(
        WordPressDraftJob(
            id="job-queued-with-claim",
            project_id=approved_proposal.project_id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v1",
            state="queued",
            payload_hash=hash_draft_job_payload({}),
            payload={},
            claim_token="claim-token",
            claim_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            claimed_at=datetime.now(UTC),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_job_rejects_cross_project_proposal_binding(
    session, projects, approved_proposal
) -> None:
    session.add(
        WordPressDraftJob(
            id="job-cross-project",
            project_id=projects.other_project.id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v1",
            state="queued",
            payload_hash=hash_draft_job_payload({}),
            payload={},
        )
    )

    with pytest.raises((IntegrityError, ValueError)):
        session.commit()


def test_job_rejects_unknown_contract_version(session, approved_proposal) -> None:
    session.add(
        WordPressDraftJob(
            id="job-unknown-contract",
            project_id=approved_proposal.project_id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v2",
            state="queued",
            payload_hash=hash_draft_job_payload({}),
            payload={},
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_job_rejects_payload_hash_mismatch(session, approved_proposal) -> None:
    session.add(
        WordPressDraftJob(
            id="job-wrong-hash",
            project_id=approved_proposal.project_id,
            proposal_version_id=approved_proposal.id,
            contract_version="wordpress-draft-job-v1",
            state="queued",
            payload_hash="0" * 64,
            payload={"title": "Concept"},
        )
    )

    with pytest.raises(ValueError, match="payload hash"):
        session.flush()


def test_job_payload_is_immutable_after_insert(session, approved_proposal) -> None:
    job = WordPressDraftJob(
        id="job-immutable",
        project_id=approved_proposal.project_id,
        proposal_version_id=approved_proposal.id,
        contract_version="wordpress-draft-job-v1",
        state="queued",
        payload_hash=hash_draft_job_payload({"title": "Concept"}),
        payload={"title": "Concept"},
    )
    session.add(job)
    session.commit()

    job.payload = {"title": "Gewijzigd"}
    job.payload_hash = hash_draft_job_payload(job.payload)

    with pytest.raises(ValueError, match="immutable"):
        session.flush()
