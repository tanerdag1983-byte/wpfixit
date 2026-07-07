from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_packages.models import (
    PagePackageProposal,
    PagePackageRegenerationCandidate,
)
from app.domains.page_packages.service import accept_regeneration_candidate
from tests.recommendations.conftest import ProjectFixtures


def page_proposal_factory(
    session: Session,
    projects: ProjectFixtures,
    *,
    proposal_id: str = "proposal-v1",
    state: str = "proposed",
    version_number: int = 1,
    is_current: bool = True,
    parent_version_id: str | None = None,
    proposal_group_id: str = "proposal-group-1",
) -> PagePackageProposal:
    opportunity = session.get(KeywordOpportunity, "opportunity-new")
    if opportunity is None:
        opportunity = KeywordOpportunity(
            id="opportunity-new",
            project_id=projects.member_project.id,
            keyword="dsg versnellingsbak reviseren",
            location_code=2528,
            language_code="nl",
            search_volume=320,
            target_classification="new_page",
            target_score=0,
            target_evidence=["no_reliable_page_match"],
            source="dataforseo",
            raw_payload={},
        )
        session.add(opportunity)

    job = session.get(Job, f"job-{proposal_id}")
    if job is None:
        job = Job(
            id=f"job-{proposal_id}",
            project_id=projects.member_project.id,
            job_type="page_package_generation",
            state="completed",
            progress=100,
            checkpoint={},
        )
        session.add(job)

    proposal = PagePackageProposal(
        id=proposal_id,
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id=job.id,
        state=state,
        proposal_group_id=proposal_group_id,
        version_number=version_number,
        parent_version_id=parent_version_id,
        is_current=is_current,
        generation_mode="full",
        package={"title": f"Versie {version_number}"},
        rendered_html=f"<h1>Versie {version_number}</h1>",
        config_snapshot={"builder": "acf"},
        proposed_by=projects.member.id,
    )
    session.add(proposal)
    session.commit()
    return proposal


def test_accepting_a_candidate_creates_a_new_current_version(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    current = page_proposal_factory(
        session,
        projects,
        state="approved",
        version_number=1,
        is_current=True,
    )
    candidate = PagePackageRegenerationCandidate(
        id="candidate-1",
        proposal_group_id=current.proposal_group_id,
        base_version_id=current.id,
        generation_mode="block",
        target_block_id="faq",
        candidate_package={"title": "Nieuwe versie"},
        candidate_rendered_html="<h1>Nieuwe versie</h1>",
        status="ready",
    )
    session.add(candidate)
    session.commit()

    next_version = accept_regeneration_candidate(session, candidate.id, "user-2")

    session.refresh(current)
    assert current.is_current is False
    assert next_version.version_number == 2
    assert next_version.parent_version_id == current.id
    assert next_version.state == "proposed"
