from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_packages.models import (
    PagePackageProposal,
    PagePackageRegenerationCandidate,
    PageProposalStage,
)
from app.domains.page_packages.service import accept_regeneration_candidate
from app.domains.wordpress.draft_jobs import hash_draft_job_payload
from app.domains.wordpress.models import WordPressDraftJob
from tests.page_packages.test_generation import valid_package
from tests.page_packages.test_proposal_routes import (
    BlueprintBridge,
    generated_blueprint_proposal,
    make_native_snapshot,
    prepare_project,
    proposal_snapshot_text_package,
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
    legacy_package["focus_keyword"] = "andere zoekterm"
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
    assert completed.candidate_package["focus_keyword"] == opportunity.keyword
    replacement_ids = {
        item["field_id"] for item in completed.candidate_package["replacements"]
    }
    assert {"acf-title", "acf-copy", "acf-cta-url"}.issubset(replacement_ids)


def test_snapshot_regeneration_candidate_can_be_accepted_and_approved(
    client,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    make_native_snapshot(session)
    bridge = BlueprintBridge()
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda current_session, project_id: bridge,
    )

    class Generator:
        provider = "openrouter"
        model = "model-2"

        def generate_page_package(self, context):
            return {
                "package": proposal_snapshot_text_package(),
                "input_tokens": 12,
                "output_tokens": 8,
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda current_session, project: Generator(),
    )
    queued = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )
    proposal_id = queued.json()["id"]
    approved = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}/approve"
    )
    assert approved.status_code == 200, approved.text

    regenerated = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}/regenerate",
        json={"mode": "full", "instruction": "Maak de tekst concreter."},
    )
    assert regenerated.status_code == 202, regenerated.text
    from app.api.routes.page_packages import _run_page_package_regeneration

    candidate_id = regenerated.json()["candidate"]["id"]
    _run_page_package_regeneration(session.get_bind(), candidate_id)
    session.expire_all()
    candidate = session.get(PagePackageRegenerationCandidate, candidate_id)
    assert candidate is not None
    assert candidate.status == "ready", candidate.candidate_package
    assert set(candidate.candidate_package) == {"text_replacements"}

    accepted = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"candidates/{candidate_id}/accept"
    )
    assert accepted.status_code == 200, accepted.text
    current = accepted.json()["current_version"]
    assert current["state"] == "proposed"
    assert [stage["state"] for stage in current["stages"]] == [
        "ready",
        "ready",
        "ready",
    ]

    reapproved = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{current['id']}/approve"
    )
    assert reapproved.status_code == 200, reapproved.text


def test_text_retry_creates_new_immutable_version_and_explicitly_calls_provider(
    client,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    make_native_snapshot(session)
    invalid = proposal_snapshot_text_package()
    del invalid["text_replacements"]["document:title"]
    valid = proposal_snapshot_text_package()
    generated = [invalid, valid]
    provider_calls = 0

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            nonlocal provider_calls
            package = generated[provider_calls]
            provider_calls += 1
            return {"package": package}

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda current_session, project: Generator(),
    )
    queued = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )
    original_id = queued.json()["id"]
    original_before = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{original_id}"
    ).json()
    assert original_before["state"] == "needs_attention"
    assert provider_calls == 1

    retried = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{original_id}/"
        "stages/text/retry"
    )
    assert retried.status_code == 202
    new_id = retried.json()["id"]
    current = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{new_id}"
    ).json()
    original_after = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{original_id}"
    ).json()

    assert new_id != original_id
    assert provider_calls == 2
    assert current["state"] == "proposed"
    assert current["version_number"] == original_before["version_number"] + 1
    assert current["parent_version_id"] == original_id
    assert current["is_current"] is True
    assert original_after["is_current"] is False
    assert original_after["current_version_id"] == new_id
    assert original_after["package"] == original_before["package"]
    assert original_after["stages"] == original_before["stages"]
    assert current["package"]["text_replacements"]["document:title"] == "Nieuwe titel"

    corrected_text = deepcopy(original_after["stages"][1]["result"])
    corrected_text["text_replacements"]["document:title"] = {
        "value": "Historische wijziging"
    }
    blocked_update = client.put(
        f"/projects/{projects.member_project.id}/page-proposals/{original_id}",
        json={"package": corrected_text},
    )
    original_after_update = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{original_id}"
    ).json()

    assert blocked_update.status_code == 409
    assert original_after_update == original_after

    historical = session.get(PagePackageProposal, original_id)
    validation = session.scalar(
        select(PageProposalStage).where(
            PageProposalStage.proposal_version_id == original_id,
            PageProposalStage.name == "validation",
        )
    )
    assert historical is not None and validation is not None
    historical.state = "proposed"
    validation.state = "ready"
    validation.errors = {}
    session.commit()
    before_approve = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{original_id}"
    ).json()
    bridge = BlueprintBridge()
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda current_session, project_id: bridge,
    )

    blocked_approve = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{original_id}/approve"
    )
    after_approve = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{original_id}"
    ).json()

    assert blocked_approve.status_code == 409
    assert after_approve == before_approve


def test_create_returns_current_attention_version_after_failed_text_retry(
    client,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    make_native_snapshot(session)
    invalid = proposal_snapshot_text_package()
    del invalid["text_replacements"]["document:title"]

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            return {"package": invalid}

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda current_session, project: Generator(),
    )
    first = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    ).json()
    retried = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{first['id']}/"
        "stages/text/retry"
    )
    assert retried.status_code == 202
    current_id = retried.json()["id"]
    historical = session.get(PagePackageProposal, first["id"])
    assert historical is not None
    historical.created_at = datetime.now(UTC) + timedelta(minutes=1)
    session.commit()

    created = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )

    assert created.status_code == 202
    assert created.json()["id"] == current_id
