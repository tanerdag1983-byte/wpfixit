import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.service import set_default_blueprint
from app.domains.page_packages import generation
from app.domains.page_packages.models import PagePackageProposal
from app.domains.page_packages.service import (
    accept_regeneration_candidate,
    create_regeneration_candidate,
    issue_page_package_handoff,
    lock_active_default_blueprint,
)
from app.domains.recommendations.models import (
    AiConnection,
    CompanyProfile,
    ProjectAiPolicy,
)
from app.domains.wordpress.draft_jobs import (
    create_or_get_draft_job,
    hash_project_key,
)
from app.domains.wordpress.models import (
    PageObservedVersion,
    PageScoreSnapshot,
    WordPressOutboundCredential,
    WordPressPage,
)
from app.domains.wordpress.snapshot_jobs import (
    claim_next_snapshot_job,
    complete_snapshot_job,
    create_or_get_snapshot_job,
)
from tests.recommendations.conftest import ProjectFixtures
from tests.wordpress.test_snapshot_job_service import snapshot_result


def _generated_snapshot_package() -> dict:
    return {
        "text_replacements": {
            "document:title": {"value": "Improved current service page"},
            "document:slug": {"value": "improved-current-service"},
            "seo:title": {"value": "Improved current service page"},
            "seo:meta_description": {
                "value": "A clearer description of the improved current service page."
            },
            "seo:focus_keyword": {"value": "ignored provider keyword"},
            "acf-title": {"value": "Improved service"},
            "acf-cta-url": {"value": "/contact/"},
        }
    }


def _normal_default_blueprint(
    session: Session,
    source: WordPressPage,
) -> PageBlueprint:
    result = snapshot_result(snapshot_id=902, structure_hash="default-structure-hash")
    blueprint = PageBlueprint(
        id="normal-new-page-default",
        project_id=source.project_id,
        name="Normal new-page default",
        page_type="service",
        source_wordpress_page_id=source.id,
        wordpress_blueprint_id=902,
        wordpress_snapshot_id=902,
        snapshot_version=1,
        schema_version="snapshot-text-v1",
        adapter_version="wp-fixpilot-bridge-test",
        capture_state="ready",
        migration_state="native",
        verified_at=datetime.fromisoformat(result["captured_at"]),
        builder="acf",
        seo_plugin="yoast",
        version=1,
        structure_hash=result["structure_hash"],
        content_schema=result["schema"],
        state="ready",
        is_default_for_page_type=True,
    )
    session.add(blueprint)
    session.commit()
    return blueprint


@pytest.fixture
def captured_existing_page(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
):
    auth_as(projects.member)
    project = projects.member_project
    source = WordPressPage(
        id="captured-existing-source",
        project_id=project.id,
        wordpress_object_id=701,
        post_type="page",
        status="publish",
        title="Current service page",
        slug="monitoring-page",
        url="https://member.example/monitoring-page",
        content_hash="source-content-hash",
    )
    opportunity = KeywordOpportunity(
        id="captured-existing-opportunity",
        project_id=project.id,
        keyword="improve current service",
        location_code=2528,
        language_code="nl",
        search_volume=320,
        target_url=source.url,
        target_classification="existing_page",
        target_score=91,
        target_evidence=["strong_existing_page_match", "missing_meta_description"],
        recommended_action="Improve the matching page.",
        source="dataforseo",
        raw_payload={},
    )
    observed = PageObservedVersion(
        id="captured-existing-version",
        project_id=project.id,
        wordpress_page_id=source.id,
        content_hash=source.content_hash,
        source="sync",
        snapshot_payload={
            "content_hash": source.content_hash,
            "values": {"title": source.title, "meta_description": ""},
        },
    )
    score = PageScoreSnapshot(
        id="captured-existing-score",
        page_version_id=observed.id,
        overall_score=61,
        factors=[
            {
                "key": "meta_description",
                "value": "",
                "points": 0,
                "max_points": 10,
                "explanation": "Meta description needs attention.",
                "suggested_action": "Add a meta description.",
                "evidence": {"value": ""},
            }
        ],
    )
    session.add_all(
        [
            source,
            opportunity,
            CompanyProfile(
                project_id=project.id,
                company_name="Member Company",
                description="Specialist",
                audience="Customers",
                services=["Current service"],
                tone_of_voice="Clear",
                custom_prompt="Use verifiable claims.",
            ),
            AiConnection(
                id="existing-page-ai",
                organization_id=projects.organization.id,
                name="OpenRouter",
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                default_model="model-1",
                encrypted_api_key="encrypted",
                enabled=True,
            ),
            ProjectAiPolicy(
                project_id=project.id,
                organization_id=projects.organization.id,
                primary_connection_id="existing-page-ai",
                primary_model="model-1",
            ),
            WordPressOutboundCredential(
                id="existing-page-credential",
                project_id=project.id,
                key_hash=hash_project_key("wpfx_existing_page"),
                site_url="https://member.example",
            ),
        ]
    )
    session.commit()
    session.add(observed)
    session.commit()
    session.add(score)
    session.commit()

    snapshot_job = create_or_get_snapshot_job(session, source)
    session.commit()
    claimed = claim_next_snapshot_job(session, project.id, "https://member.example")
    assert claimed is not None
    complete_snapshot_job(
        session,
        claimed.job.id,
        claimed.claim_token,
        snapshot_result(),
    )
    session.commit()

    contexts = []

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            contexts.append(context)
            return {"package": _generated_snapshot_package()}

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )
    return SimpleNamespace(
        route=(
            f"/projects/{project.id}/keyword-opportunities/"
            f"{opportunity.id}/page-proposal"
        ),
        source=source,
        opportunity=opportunity,
        contexts=contexts,
        snapshot_job_id=snapshot_job.id,
    )


def test_retry_after_capture_binds_one_proposal_to_the_snapshot(
    client: TestClient,
    session: Session,
    captured_existing_page,
) -> None:
    captured = captured_existing_page
    source_page_was_locked = False

    def observe_source_page_lock(execute_state) -> None:
        nonlocal source_page_was_locked
        statement = execute_state.statement
        if (
            execute_state.is_select
            and statement._for_update_arg is not None
            and any(
                description.get("entity") is WordPressPage
                for description in statement.column_descriptions
            )
        ):
            source_page_was_locked = True

    event.listen(session, "do_orm_execute", observe_source_page_lock)
    try:
        created = client.post(captured.route, json={"page_type": "service"})
    finally:
        event.remove(session, "do_orm_execute", observe_source_page_lock)

    assert created.status_code == 202
    assert source_page_was_locked
    proposal = session.get(PagePackageProposal, created.json()["id"])
    assert proposal is not None
    blueprint = session.get(PageBlueprint, proposal.blueprint_id)

    retry = client.post(captured.route, json={"page_type": "service"})

    assert retry.status_code == 202
    assert retry.json()["id"] == proposal.id
    assert proposal.source_wordpress_page_id == captured.source.id
    assert proposal.config_snapshot["snapshot_job_id"] == captured.snapshot_job_id
    assert proposal.config_snapshot["source_content_hash"] == "source-content-hash"
    assert blueprint is not None
    assert blueprint.wordpress_snapshot_id == 901
    assert session.scalar(select(func.count(PagePackageProposal.id))) == 1


def test_existing_page_snapshot_does_not_change_new_page_default(
    client: TestClient,
    session: Session,
    captured_existing_page,
) -> None:
    captured = captured_existing_page
    default = _normal_default_blueprint(session, captured.source)
    new_opportunity = KeywordOpportunity(
        id="new-page-control-opportunity",
        project_id=captured.source.project_id,
        keyword="new service page",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=["no_reliable_page_match"],
        source="dataforseo",
        raw_payload={},
    )
    session.add(new_opportunity)
    session.commit()

    existing = client.post(captured.route, json={"page_type": "service"})
    assert existing.status_code == 202
    existing_proposal = session.get(PagePackageProposal, existing.json()["id"])
    assert existing_proposal is not None
    optimization_blueprint = session.get(
        PageBlueprint,
        existing_proposal.blueprint_id,
    )
    new_page = client.post(
        f"/projects/{captured.source.project_id}/keyword-opportunities/"
        f"{new_opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )

    assert optimization_blueprint is not None
    assert optimization_blueprint.adapter_version == "optimization-source-v1"
    assert new_page.status_code == 202
    assert new_page.json()["blueprint"]["id"] == default.id


def test_optimization_source_cannot_be_selected_as_a_default(
    client: TestClient,
    session: Session,
    captured_existing_page,
) -> None:
    captured = captured_existing_page
    created = client.post(captured.route, json={"page_type": "service"})
    proposal = session.get(PagePackageProposal, created.json()["id"])
    assert proposal is not None
    optimization_blueprint = session.get(PageBlueprint, proposal.blueprint_id)
    assert optimization_blueprint is not None

    with pytest.raises(ValueError, match="optimization source"):
        set_default_blueprint(session, optimization_blueprint)

    optimization_blueprint.is_default_for_page_type = True
    session.commit()
    selected, selection_changed = lock_active_default_blueprint(
        session,
        captured.source.project_id,
        "service",
    )

    assert selected is None
    assert selection_changed is False


def test_source_change_after_capture_does_not_change_generation_context(
    client: TestClient,
    session: Session,
    captured_existing_page,
) -> None:
    captured = captured_existing_page
    created = client.post(captured.route, json={"page_type": "service"})

    assert created.status_code == 202
    proposal = session.get(PagePackageProposal, created.json()["id"])
    assert proposal is not None
    context = generation.build_context(session, proposal)
    captured.source.title = "Changed live title"
    captured.opportunity.target_evidence = ["changed_live_evidence"]

    rebuilt = generation.build_context(session, proposal)
    prompt = json.loads(generation.page_package_user_prompt(context))
    current_values = {
        field["id"]: field["current_value"] for field in prompt["field_definitions"]
    }

    assert rebuilt == context
    assert captured.contexts == [context]
    assert current_values["document:title"] == "Diensttemplate"
    assert '"target_url": "https://member.example/monitoring-page"' in (
        context.company_context
    )
    assert '"prior_score": 61' in context.company_context
    assert "missing_meta_description" in context.company_context


def test_approved_existing_page_uses_only_the_outbound_snapshot_draft_path(
    client: TestClient,
    session: Session,
    captured_existing_page,
    projects: ProjectFixtures,
) -> None:
    captured = captured_existing_page
    created = client.post(captured.route, json={"page_type": "service"})
    assert created.status_code == 202
    proposal = session.get(PagePackageProposal, created.json()["id"])
    assert proposal is not None

    approved = client.post(
        f"/projects/{proposal.project_id}/page-proposals/{proposal.id}/approve"
    )
    retried = client.post(captured.route, json={"page_type": "service"})
    direct = client.post(
        f"/projects/{proposal.project_id}/page-proposals/{proposal.id}/create-draft"
    )
    session.refresh(proposal)
    with pytest.raises(ValueError, match="outbound draft-job path"):
        issue_page_package_handoff(session, proposal, projects.member.id)
    draft_job = create_or_get_draft_job(session, proposal)

    assert approved.status_code == 200
    assert retried.json()["id"] == proposal.id
    assert session.scalar(select(func.count(PagePackageProposal.id))) == 1
    assert direct.status_code == 409
    assert "outbound draft-job path" in direct.json()["detail"]
    assert draft_job.contract_version == "wordpress-snapshot-draft-job-v1"
    assert draft_job.payload["snapshot_id"] == 901
    assert proposal.source_wordpress_page_id == captured.source.id


def test_proposed_existing_page_can_save_edits_before_exact_approval(
    client: TestClient,
    session: Session,
    captured_existing_page,
) -> None:
    captured = captured_existing_page
    created = client.post(captured.route, json={"page_type": "service"})
    proposal = session.get(PagePackageProposal, created.json()["id"])
    assert proposal is not None
    assert proposal.state == "proposed"
    replacements = {
        field_id: {"value": value}
        for field_id, value in proposal.package["text_replacements"].items()
    }
    replacements["seo:meta_description"] = {
        "value": "Handmatig aangescherpte meta description voor deze pagina."
    }

    saved = client.put(
        f"/projects/{proposal.project_id}/page-proposals/{proposal.id}",
        json={"package": {"text_replacements": replacements}},
    )
    approved = client.post(
        f"/projects/{proposal.project_id}/page-proposals/{proposal.id}/approve"
    )

    assert saved.status_code == 200, saved.text
    assert approved.status_code == 200, approved.text
    assert approved.json()["package"]["text_replacements"][
        "seo:meta_description"
    ] == replacements["seo:meta_description"]["value"]


def test_regeneration_version_preserves_existing_page_source_and_context(
    client: TestClient,
    session: Session,
    captured_existing_page,
    projects: ProjectFixtures,
) -> None:
    captured = captured_existing_page
    created = client.post(captured.route, json={"page_type": "service"})
    assert created.status_code == 202
    proposal = session.get(PagePackageProposal, created.json()["id"])
    assert proposal is not None
    proposal.state = "approved"
    proposal.approved_by = projects.member.id
    session.commit()
    candidate = create_regeneration_candidate(
        session,
        proposal,
        mode="full",
        target_block_id=None,
        instruction="Improve clarity.",
        candidate_package={
            "text_replacements": proposal.package["text_replacements"],
            "approved_urls": ["/contact/"],
        },
        candidate_rendered_html="",
        provider=proposal.provider,
        model=proposal.model,
        prompt_version=proposal.prompt_version,
        status="ready",
    )

    next_version = accept_regeneration_candidate(
        session,
        candidate.id,
        projects.member.id,
    )

    assert next_version.source_wordpress_page_id == captured.source.id
    assert (
        next_version.config_snapshot["generation_context"]
        == proposal.config_snapshot["generation_context"]
    )
