import pytest
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_packages.models import (
    PagePackageProposal,
    PagePackageRegenerationCandidate,
)
from app.domains.page_packages.service import accept_regeneration_candidate
from app.domains.wordpress.draft_jobs import hash_draft_job_payload
from app.domains.wordpress.models import WordPressDraftJob
from tests.page_packages.test_generation import valid_package
from tests.page_packages.test_proposal_routes import (
    BlueprintBridge,
    generated_blueprint_proposal,
    prepare_project,
)
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
    current_version_id: str | None = None,
    provider: str | None = "openai",
    model: str | None = "gpt-4.1-mini",
    prompt_version: str | None = "prompt-v1",
    input_tokens: int = 11,
    output_tokens: int = 7,
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
        current_version_id=current_version_id or proposal_id,
        is_current=is_current,
        generation_mode="full",
        package={"title": f"Versie {version_number}"},
        rendered_html=f"<h1>Versie {version_number}</h1>",
        config_snapshot={"builder": "acf"},
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
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
        proposal_id="proposal-v1",
        state="approved",
        version_number=1,
        is_current=True,
        proposal_group_id="proposal-group-1",
        current_version_id="proposal-v1",
    )
    archived = page_proposal_factory(
        session,
        projects,
        proposal_id="proposal-v0",
        state="draft_created",
        version_number=0,
        is_current=False,
        proposal_group_id="proposal-group-1",
        current_version_id=current.id,
    )
    candidate = PagePackageRegenerationCandidate(
        id="candidate-1",
        proposal_group_id=current.proposal_group_id,
        base_version_id=current.id,
        generation_mode="block",
        target_block_id="faq",
        candidate_package={"title": "Nieuwe versie"},
        candidate_rendered_html="<h1>Nieuwe versie</h1>",
        provider="anthropic",
        model="claude-3-7-sonnet",
        prompt_version="prompt-v2",
        input_tokens=19,
        output_tokens=23,
        status="ready",
    )
    old_draft_job = WordPressDraftJob(
        id="outbound-job-v1",
        project_id=current.project_id,
        proposal_version_id=current.id,
        contract_version="wordpress-draft-job-v1",
        state="queued",
        payload={},
        payload_hash=hash_draft_job_payload({}),
    )
    session.add_all([candidate, old_draft_job])
    session.commit()

    next_version = accept_regeneration_candidate(session, candidate.id, "user-2")

    session.refresh(archived)
    session.refresh(current)
    assert archived.current_version_id == next_version.id
    assert current.current_version_id == next_version.id
    assert current.is_current is False
    assert next_version.current_version_id == next_version.id
    assert next_version.version_number == 2
    assert next_version.parent_version_id == current.id
    assert next_version.state == "proposed"
    assert next_version.provider == "anthropic"
    assert next_version.model == "claude-3-7-sonnet"
    assert next_version.prompt_version == "prompt-v2"
    assert next_version.input_tokens == 19
    assert next_version.output_tokens == 23
    session.refresh(old_draft_job)
    assert old_draft_job.state == "cancelled"


def test_accepting_candidate_rejects_active_delivery_lease(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    current = page_proposal_factory(
        session,
        projects,
        proposal_id="proposal-delivering",
        state="draft_in_progress",
        proposal_group_id="proposal-delivering",
    )
    candidate = PagePackageRegenerationCandidate(
        id="candidate-delivering",
        proposal_group_id=current.proposal_group_id,
        base_version_id=current.id,
        generation_mode="full",
        candidate_package={"title": "Nieuwe versie"},
        candidate_rendered_html="",
        status="ready",
    )
    session.add(candidate)
    session.commit()

    with pytest.raises(ValueError, match="no longer current"):
        accept_regeneration_candidate(session, candidate.id, "user-2")


def test_regenerate_block_creates_candidate_without_mutating_current(
    client,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    proposal = generated_blueprint_proposal(client, projects, opportunity, monkeypatch)
    bridge = BlueprintBridge()
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda current_session, project_id: bridge,
    )
    approved = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal['id']}/approve"
    )
    assert approved.status_code == 200

    class Generator:
        provider = "openrouter"
        model = "model-2"

        def generate_page_package(self, context):
            return {
                "package": proposal["package"],
                "input_tokens": 12,
                "output_tokens": 8,
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda current_session, project: Generator(),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal['id']}/regenerate",
        json={
            "mode": "block",
            "target_block_id": "hero",
            "instruction": "Maak de antwoorden concreter.",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["base_version"]["id"] == proposal["id"]
    assert body["candidate"]["status"] == "generating"

    from app.api.routes.page_packages import _run_page_package_regeneration

    _run_page_package_regeneration(session.get_bind(), body["candidate"]["id"])
    session.expire_all()
    completed = session.get(PagePackageRegenerationCandidate, body["candidate"]["id"])
    assert completed is not None
    assert completed.status == "ready"
    assert completed.candidate_package == proposal["package"]

    stored = session.get(PagePackageProposal, proposal["id"])
    assert stored is not None
    assert stored.is_current is True
    assert stored.state == "approved"


def test_regenerate_normalizes_legacy_page_package_into_blueprint_candidate(
    client,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    proposal = generated_blueprint_proposal(client, projects, opportunity, monkeypatch)
    bridge = BlueprintBridge()
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda current_session, project_id: bridge,
    )
    approved = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal['id']}/approve"
    )
    assert approved.status_code == 200

    legacy_package = valid_package()
    legacy_package["focus_keyword"] = opportunity.keyword
    legacy_package["cta"]["button_url"] = "/contact/"
    legacy_package["internal_links"] = [
        {
            "anchor": "Dienst template",
            "url": "https://member.example/dienst-template/",
        }
    ]

    class Generator:
        provider = "openrouter"
        model = "model-2"

        def generate_page_package(self, context):
            return {
                "package": legacy_package,
                "input_tokens": 12,
                "output_tokens": 8,
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda current_session, project: Generator(),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal['id']}/regenerate",
        json={
            "mode": "full",
            "instruction": "Maak een volledige nieuwe versie.",
        },
    )

    assert response.status_code == 202
    from app.api.routes.page_packages import _run_page_package_regeneration

    _run_page_package_regeneration(
        session.get_bind(),
        response.json()["candidate"]["id"],
    )
    session.expire_all()
    completed = session.get(
        PagePackageRegenerationCandidate, response.json()["candidate"]["id"]
    )
    assert completed is not None
    assert completed.status == "ready", completed.candidate_package
    assert "replacements" in completed.candidate_package
    assert "hero_title" not in completed.candidate_package
    replacement_ids = {
        item["field_id"] for item in completed.candidate_package["replacements"]
    }
    assert {"acf-title", "acf-copy", "acf-cta-url"}.issubset(replacement_ids)
