from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.page_packages import _import_package_payload
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_packages.models import (
    PagePackageProposal,
    PagePackageRegenerationCandidate,
    PageProposalStage,
    ProjectPagePackageSettings,
)
from app.domains.page_packages.schemas import GeneratedBlueprintPackage
from app.domains.recommendations.models import (
    AiConnection,
    CompanyProfile,
    ProjectAiPolicy,
)
from app.domains.wordpress.models import WordPressPage
from tests.page_packages.test_generation import (
    blueprint_package,
    valid_blueprint_schema,
    valid_package,
)
from tests.recommendations.conftest import ProjectFixtures


def valid_snapshot_schema() -> dict:
    def field(field_id: str, path: str, value_type: str) -> dict:
        return {
            "id": field_id,
            "path": path,
            "label": field_id,
            "value_type": value_type,
            "current_value": "",
            "required": True,
            "max_length": 180,
        }

    return {
        "schema_version": "snapshot-text-v1",
        "document_fields": [
            field("document:title", "post_title", "heading"),
            field("document:slug", "post_name", "plain_text"),
            field("seo:title", "seo.title", "seo_title"),
            field(
                "seo:meta_description",
                "seo.meta_description",
                "meta_description",
            ),
            field("seo:focus_keyword", "seo.focus_keyword", "focus_keyword"),
        ],
        "blocks": valid_blueprint_schema()["blocks"],
    }


def proposal_package() -> dict:
    package = valid_package()
    package["internal_links"] = [
        {
            "anchor": "Dienst template",
            "url": "https://member.example/dienst-template/",
        }
    ]
    return package


def proposal_blueprint_package() -> dict:
    package = blueprint_package().model_dump()
    package["focus_keyword"] = "dsg versnellingsbak reviseren"
    package["replacements"][1]["value"] = "/contact/"
    package["internal_links"] = [
        {
            "anchor": "Dienst template",
            "url": "https://member.example/dienst-template/",
        }
    ]
    return package


def proposal_snapshot_text_package() -> dict:
    return {
        "text_replacements": {
            "document:title": {"value": "<strong>Nieuwe titel</strong>"},
            "document:slug": {"value": "nieuwe-titel"},
            "seo:title": {"value": "Nieuwe SEO-titel"},
            "seo:meta_description": {
                "value": "Nieuwe metabeschrijving voor deze pagina."
            },
            "seo:focus_keyword": {"value": "wordt door opportunity vervangen"},
            "acf-title": {"value": "Nieuwe hero"},
            "acf-cta-url": {"value": "/contact/"},
        }
    }


def test_import_payload_returns_normalized_legacy_package(monkeypatch) -> None:
    normalized = proposal_blueprint_package()
    legacy = {"landing_page": {"title": "Oude titel"}}
    blueprint = SimpleNamespace(
        id="blueprint-service-v2",
        project_id="project-member",
        content_schema=valid_blueprint_schema(),
        name="Dienstpagina",
        page_type="service",
        version=2,
        structure_hash="hash-v2",
        builder="acf",
        seo_plugin="yoast",
        wordpress_blueprint_id=902,
        source_wordpress_page_id="template-page",
    )
    proposal = SimpleNamespace(
        package=legacy,
        blueprint_id=blueprint.id,
        project_id="project-member",
        opportunity_id="opportunity-new",
        config_snapshot={"content_schema": blueprint.content_schema},
        id="proposal-1",
        proposal_group_id="group-1",
        version_number=1,
        blueprint_version=2,
        blueprint_structure_hash="hash-v2",
        state="approved",
    )

    class SessionStub:
        def get(self, model, identifier):
            if model is PageBlueprint:
                return blueprint
            return SimpleNamespace(id=identifier)

    monkeypatch.setattr(
        "app.api.routes.page_packages._generation_context",
        lambda *args: SimpleNamespace(blueprint_schema=valid_blueprint_schema()),
    )
    monkeypatch.setattr(
        "app.api.routes.page_packages.normalize_blueprint_package",
        lambda package, context: GeneratedBlueprintPackage.model_validate(normalized),
    )

    payload = _import_package_payload(SessionStub(), proposal)

    assert payload["package"]["title"] == normalized["title"]
    assert payload["package"] != legacy


class BlueprintBridge:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.wordpress_ids: list[int] = []
        self.version = 2
        self.structure_hash = "hash-v2"
        self.current_overrides: dict = {}

    def blueprint(self, wordpress_blueprint_id: int) -> dict:
        current = {
            "status": "ready",
            "wordpress_blueprint_id": wordpress_blueprint_id,
            "wordpress_snapshot_id": wordpress_blueprint_id,
            "post_type": "wpfixpilot_snapshot",
            "adapter_version": "acf-v1",
            "schema_version": "snapshot-text-v1",
            "builder": "acf",
            "seo_plugin": "yoast",
            "version": self.version,
            "snapshot_version": self.version,
            "structure_hash": self.structure_hash,
        }
        current.update(self.current_overrides)
        return current

    def create_blueprint_draft(
        self, wordpress_blueprint_id: int, payload: dict
    ) -> dict:
        self.wordpress_ids.append(wordpress_blueprint_id)
        self.payloads.append(payload)
        return {
            "wordpress_object_id": 987,
            "edit_url": "https://member.example/wp-admin/post.php?post=987",
            "status": "draft",
            "content_hash": "draft-hash",
        }


def prepare_project(session: Session, projects: ProjectFixtures) -> KeywordOpportunity:
    page = WordPressPage(
        id="template-page",
        project_id=projects.member_project.id,
        wordpress_object_id=701,
        post_type="page",
        status="publish",
        title="Dienst template",
        slug="dienst-template",
        url="https://member.example/dienst-template/",
    )
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
    session.add_all([page, opportunity])
    session.commit()
    session.add_all(
        [
            PageBlueprint(
                id="blueprint-service-v2",
                project_id=projects.member_project.id,
                name="Dienstpagina",
                page_type="service",
                source_wordpress_page_id=page.id,
                wordpress_blueprint_id=902,
                builder="acf",
                seo_plugin="yoast",
                version=2,
                structure_hash="hash-v2",
                content_schema=valid_blueprint_schema(),
                state="ready",
                is_default_for_page_type=True,
            ),
            ProjectPagePackageSettings(
                project_id=projects.member_project.id,
                builder="elementor",
                template_wordpress_page_id=page.id,
                seo_plugin="yoast",
                slot_mapping={
                    "hero_title": "hero.title",
                    "introduction": "intro.text",
                    "main_content": "main.text",
                    "faq": "faq.items",
                    "cta_title": "cta.title",
                    "cta_text": "cta.text",
                },
                template_content_hash="template-hash",
                validation_state="valid",
            ),
            CompanyProfile(
                project_id=projects.member_project.id,
                company_name="SHM Transmissie",
                description="Transmissiespecialist",
                audience="Autobezitters",
                services=["DSG revisie"],
                tone_of_voice="Duidelijk",
                custom_prompt="Noem alleen controleerbare garanties.",
            ),
            AiConnection(
                id="ai-primary",
                organization_id=projects.organization.id,
                name="OpenRouter",
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                default_model="model-1",
                encrypted_api_key="encrypted",
                enabled=True,
            ),
            ProjectAiPolicy(
                project_id=projects.member_project.id,
                organization_id=projects.organization.id,
                primary_connection_id="ai-primary",
                primary_model="model-1",
            ),
        ]
    )
    session.commit()
    return opportunity


def make_native_snapshot(session: Session) -> PageBlueprint:
    blueprint = session.get(PageBlueprint, "blueprint-service-v2")
    assert blueprint is not None
    blueprint.wordpress_snapshot_id = 902
    blueprint.snapshot_version = 2
    blueprint.schema_version = "snapshot-text-v1"
    blueprint.adapter_version = "acf-v1"
    blueprint.capture_state = "ready"
    blueprint.migration_state = "native"
    blueprint.verified_at = datetime.now(UTC)
    blueprint.content_schema = valid_snapshot_schema()
    session.commit()
    return blueprint


def generated_blueprint_proposal(
    client: TestClient,
    projects: ProjectFixtures,
    opportunity: KeywordOpportunity,
    monkeypatch,
) -> dict:
    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            if context.blueprint_schema.schema_version == "snapshot-text-v1":
                return {"package": proposal_snapshot_text_package()}
            return {"package": proposal_blueprint_package()}

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )
    queued = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    ).json()
    return client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{queued['id']}"
    ).json()


def test_proposal_uses_requested_page_type_default_blueprint(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            assert context.blueprint_schema is not None
            return {"package": proposal_blueprint_package()}

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )
    response = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )

    assert response.status_code == 202
    proposal = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{response.json()['id']}"
    ).json()
    assert proposal["blueprint"]["name"] == "Dienstpagina"
    assert proposal["blueprint"]["version"] == 2
    assert proposal["config_snapshot"]["structure_hash"] == "hash-v2"
    assert proposal["config_snapshot"]["content_schema"] == valid_blueprint_schema()


def test_proposal_reselects_default_after_migration_transfer_while_locking(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    legacy = session.get(PageBlueprint, "blueprint-service-v2")
    successor = PageBlueprint(
        id="blueprint-service-v3",
        project_id=legacy.project_id,
        name="Snapshot dienstpagina",
        page_type=legacy.page_type,
        source_wordpress_page_id=legacy.source_wordpress_page_id,
        wordpress_blueprint_id=903,
        wordpress_snapshot_id=903,
        snapshot_version=3,
        schema_version="snapshot-text-v1",
        adapter_version="acf-v1",
        capture_state="ready",
        migration_state="native",
        verified_at=datetime.now(UTC),
        builder="acf",
        seo_plugin="yoast",
        version=3,
        structure_hash="hash-v3",
        content_schema=valid_snapshot_schema(),
        state="ready",
        is_default_for_page_type=True,
        supersedes_id=legacy.id,
    )
    original_scalar = session.scalar
    default_transferred = False

    def transfer_default_after_initial_selection(statement, *args, **kwargs):
        nonlocal default_transferred
        result = original_scalar(statement, *args, **kwargs)
        sql = str(statement)
        if (
            not default_transferred
            and "page_blueprints.is_default_for_page_type IS true" in sql
        ):
            legacy.is_default_for_page_type = False
            session.add(successor)
            session.flush()
            default_transferred = True
        return result

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            return {"package": proposal_blueprint_package()}

    monkeypatch.setattr(session, "scalar", transfer_default_after_initial_selection)
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )

    assert response.status_code == 202, response.text
    proposal = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{response.json()['id']}"
    ).json()
    assert proposal["blueprint"]["id"] == successor.id
    assert proposal["config_snapshot"]["structure_hash"] == "hash-v3"
    assert (
        proposal["config_snapshot"]["content_schema"]["schema_version"]
        == "snapshot-text-v1"
    )


def test_creates_persistent_reviewable_page_proposal(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            assert context.keyword == opportunity.keyword
            assert "SHM Transmissie" in context.company_context
            return {
                "package": proposal_blueprint_package(),
                "input_tokens": 100,
                "output_tokens": 200,
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )

    assert response.status_code == 202
    assert response.json()["state"] == "generating"
    assert response.json()["job"]["state"] == "queued"
    proposal_id = response.json()["id"]
    loaded = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}"
    )
    assert loaded.status_code == 200
    assert loaded.json()["state"] == "proposed"
    assert loaded.json()["package"]["focus_keyword"] == opportunity.keyword
    assert loaded.json()["job"]["state"] == "completed"
    assert loaded.json()["stages"] == []
    assert loaded.json()["field_errors"] == {}


def test_snapshot_proposal_persists_ordered_template_text_validation_stages(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    make_native_snapshot(session)

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            return {
                "package": proposal_snapshot_text_package(),
                "input_tokens": 13,
                "output_tokens": 21,
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
    loaded = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{queued.json()['id']}"
    )

    assert queued.status_code == 202
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["state"] == "proposed"
    assert [stage["name"] for stage in body["stages"]] == [
        "template",
        "text",
        "validation",
    ]
    assert [stage["state"] for stage in body["stages"]] == [
        "ready",
        "ready",
        "ready",
    ]
    assert body["stages"][0]["result"] == {
        "wordpress_snapshot_id": 902,
        "snapshot_version": 2,
        "schema_version": "snapshot-text-v1",
        "structure_hash": "hash-v2",
    }
    assert body["stages"][1]["result"] == proposal_snapshot_text_package()
    assert body["stages"][2]["result"]["approved_urls"] == [
        "/contact/",
        "https://member.example/dienst-template/",
    ]
    assert body["package"]["text_replacements"]["document:title"] == "Nieuwe titel"
    assert body["package"]["text_replacements"]["seo:focus_keyword"] == (
        opportunity.keyword
    )
    assert body["field_errors"] == {}


def test_validation_attention_keeps_text_and_retry_does_not_call_provider(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    make_native_snapshot(session)
    package = proposal_snapshot_text_package()
    del package["text_replacements"]["document:title"]
    provider_calls = 0

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            nonlocal provider_calls
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
    proposal_id = queued.json()["id"]
    before = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}"
    ).json()

    retried = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}/"
        "stages/validation/retry"
    )
    after = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}"
    ).json()

    assert before["state"] == "needs_attention"
    assert before["field_errors"] == {"document:title": "required"}
    assert retried.status_code == 202
    assert after["state"] == "needs_attention"
    assert provider_calls == 1
    before_text = next(stage for stage in before["stages"] if stage["name"] == "text")
    after_text = next(stage for stage in after["stages"] if stage["name"] == "text")
    validation = next(
        stage for stage in after["stages"] if stage["name"] == "validation"
    )
    assert before_text["state"] == "ready"
    assert before_text["result"] == package
    assert after_text == before_text
    assert validation["state"] == "attention"
    assert validation["retry_count"] == 1
    assert validation["errors"] == {"document:title": "required"}


def test_attention_snapshot_accepts_manual_correction_without_rerunning_provider(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    make_native_snapshot(session)
    package = proposal_snapshot_text_package()
    del package["text_replacements"]["document:title"]
    provider_calls = 0

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            nonlocal provider_calls
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
    proposal_id = queued.json()["id"]
    before = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}"
    ).json()
    corrected_text = next(
        stage for stage in before["stages"] if stage["name"] == "text"
    )["result"]
    corrected_text["text_replacements"]["document:title"] = {
        "value": "Handmatig aangevulde titel"
    }

    updated = client.put(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}",
        json={"package": corrected_text},
    )

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["state"] == "proposed"
    assert body["field_errors"] == {}
    assert provider_calls == 1
    text = next(stage for stage in body["stages"] if stage["name"] == "text")
    validation = next(
        stage for stage in body["stages"] if stage["name"] == "validation"
    )
    assert "document:title" not in text["result"]["text_replacements"]
    assert validation["state"] == "ready"
    assert validation["retry_count"] == 1
    assert body["package"]["text_replacements"]["document:title"] == (
        "Handmatig aangevulde titel"
    )


def test_snapshot_worker_reclaims_only_a_stale_running_text_stage(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    make_native_snapshot(session)
    provider_calls = 0

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            nonlocal provider_calls
            provider_calls += 1
            return {"package": proposal_snapshot_text_package()}

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
    proposal = session.get(PagePackageProposal, proposal_id)
    assert proposal is not None
    text_stage = session.scalar(
        select(PageProposalStage).where(
            PageProposalStage.proposal_version_id == proposal_id,
            PageProposalStage.name == "text",
        )
    )
    validation_stage = session.scalar(
        select(PageProposalStage).where(
            PageProposalStage.proposal_version_id == proposal_id,
            PageProposalStage.name == "validation",
        )
    )
    assert text_stage is not None and validation_stage is not None
    text_stage.state = "running"
    text_stage.started_at = datetime.now(UTC) - timedelta(minutes=6)
    text_stage.completed_at = None
    text_stage.result = {}
    validation_stage.state = "pending"
    validation_stage.result = {}
    validation_stage.errors = {}
    proposal.state = "generating"
    session.get(Job, proposal.job_id).state = "queued"
    session.commit()

    from app.api.routes.page_packages import _run_page_package_generation

    _run_page_package_generation(session.get_bind(), proposal_id)
    session.expire_all()
    recovered = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}"
    ).json()
    recovered_text = next(
        stage for stage in recovered["stages"] if stage["name"] == "text"
    )

    assert provider_calls == 2
    assert recovered["state"] == "proposed"
    assert recovered_text["state"] == "ready"
    assert recovered_text["retry_count"] == 1


def test_reclaimed_validation_attempt_fences_late_proposal_and_job_writes(
    session: Session,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    from app.api.routes.page_packages import (
        _apply_snapshot_validation,
        _fail_snapshot_generation,
    )
    from app.domains.page_packages.stages import reclaim_stale_running_stage

    opportunity = prepare_project(session, projects)
    proposal = PagePackageProposal(
        id="proposal-fenced-attempt",
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id="job-fenced-attempt",
        state="generating",
        proposal_group_id="proposal-fenced-attempt",
        current_version_id="proposal-fenced-attempt",
        package={"original": True},
        rendered_html="",
        config_snapshot={},
        proposed_by=projects.member.id,
    )
    job = Job(
        id=proposal.job_id,
        project_id=proposal.project_id,
        job_type="page_package_generation",
        state="running",
        progress=80,
    )
    stage = PageProposalStage(
        proposal_version_id=proposal.id,
        name="validation",
        state="running",
        result={},
        errors={},
        started_at=datetime.now(UTC) - timedelta(minutes=6),
    )
    session.add_all([job, proposal, stage])
    session.commit()
    previous_token = stage.attempt_token
    current = reclaim_stale_running_stage(
        session,
        proposal.id,
        "validation",
    )
    session.commit()

    monkeypatch.setattr(
        "app.api.routes.page_packages.normalize_snapshot_text_package",
        lambda raw, context: SimpleNamespace(
            replacements={"document:title": "late"},
            field_errors={},
            blocking_field_ids=[],
            ignored_field_ids=[],
            missing_required_field_ids=[],
            ready=True,
        ),
    )
    with pytest.raises(ValueError, match="stale_stage_attempt"):
        _apply_snapshot_validation(
            session,
            proposal,
            job,
            SimpleNamespace(),
            {},
            previous_token,
        )
    _fail_snapshot_generation(
        session,
        proposal,
        job,
        "validation",
        RuntimeError("late failure"),
        previous_token,
    )

    session.expire_all()
    stored_proposal = session.get(PagePackageProposal, proposal.id)
    stored_job = session.get(Job, job.id)
    stored_stage = session.get(PageProposalStage, stage.id)
    assert stored_proposal.state == "generating"
    assert stored_proposal.package == {"original": True}
    assert stored_job.state == "running"
    assert stored_job.progress == 80
    assert stored_stage.state == "running"
    assert stored_stage.attempt_token == current.attempt_token
    assert stored_stage.result == {}
    assert stored_stage.errors == {}

    _apply_snapshot_validation(
        session,
        stored_proposal,
        stored_job,
        SimpleNamespace(),
        {},
        current.attempt_token,
    )
    session.commit()
    _fail_snapshot_generation(
        session,
        stored_proposal,
        stored_job,
        "validation",
        RuntimeError("late failure after replacement completed"),
        previous_token,
    )

    session.expire_all()
    assert session.get(PagePackageProposal, proposal.id).state == "proposed"
    assert session.get(Job, job.id).state == "completed"
    assert session.get(PageProposalStage, stage.id).state == "ready"


def test_late_worker_refreshes_fencing_token_from_database(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    from app.api.routes.page_packages import _fail_snapshot_generation

    opportunity = prepare_project(session, projects)
    proposal = PagePackageProposal(
        id="proposal-stale-identity-map",
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id="job-stale-identity-map",
        state="generating",
        proposal_group_id="proposal-stale-identity-map",
        current_version_id="proposal-stale-identity-map",
        package={},
        rendered_html="",
        config_snapshot={},
        proposed_by=projects.member.id,
    )
    job = Job(
        id=proposal.job_id,
        project_id=proposal.project_id,
        job_type="page_package_generation",
        state="running",
        progress=80,
    )
    stage = PageProposalStage(
        proposal_version_id=proposal.id,
        name="validation",
        state="running",
        result={},
        errors={},
        started_at=datetime.now(UTC),
    )
    session.add_all([job, proposal, stage])
    session.commit()
    previous_token = stage.attempt_token

    with Session(session.get_bind(), expire_on_commit=False) as replacement:
        replacement_stage = replacement.get(PageProposalStage, stage.id)
        replacement_proposal = replacement.get(PagePackageProposal, proposal.id)
        replacement_job = replacement.get(Job, job.id)
        replacement_stage.attempt_token = "replacement-attempt"
        replacement_stage.state = "ready"
        replacement_stage.result = {"winner": "replacement"}
        replacement_proposal.state = "proposed"
        replacement_job.state = "completed"
        replacement_job.progress = 100
        replacement.commit()

    assert stage.attempt_token == previous_token
    _fail_snapshot_generation(
        session,
        proposal,
        job,
        "validation",
        RuntimeError("late stale-session failure"),
        previous_token,
    )

    session.expire_all()
    assert session.get(PageProposalStage, stage.id).attempt_token == (
        "replacement-attempt"
    )
    assert session.get(PageProposalStage, stage.id).state == "ready"
    assert session.get(PagePackageProposal, proposal.id).state == "proposed"
    assert session.get(Job, job.id).state == "completed"


def test_stage_response_field_errors_are_ordered(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    proposal = PagePackageProposal(
        id="proposal-ordered-errors",
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id="job-ordered-errors",
        state="needs_attention",
        proposal_group_id="proposal-ordered-errors",
        current_version_id="proposal-ordered-errors",
        package={},
        rendered_html="",
        config_snapshot={
            "content_schema": {
                "schema_version": "snapshot-text-v1",
                "document_fields": [{"id": "document:title"}],
                "blocks": [],
            }
        },
        proposed_by=projects.member.id,
    )
    from app.domains.jobs.models import Job

    session.add(
        Job(
            id="job-ordered-errors",
            project_id=projects.member_project.id,
            job_type="page_package_generation",
        )
    )
    session.add(proposal)
    session.flush()
    session.add_all(
        [
            PageProposalStage(
                proposal_version_id=proposal.id,
                name="validation",
                state="attention",
                result={},
                errors={
                    "document:title": "required",
                    "message": "validation worker failed",
                    "provider": "unavailable",
                    "unknown:field": "unsafe_html",
                },
            ),
            PageProposalStage(
                proposal_version_id=proposal.id,
                name="template",
                state="ready",
                result={},
                errors={},
            ),
            PageProposalStage(
                proposal_version_id=proposal.id,
                name="text",
                state="ready",
                result={},
                errors={},
            ),
        ]
    )
    session.commit()

    response = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal.id}"
    )

    assert response.status_code == 200
    assert [stage["name"] for stage in response.json()["stages"]] == [
        "template",
        "text",
        "validation",
    ]
    assert response.json()["field_errors"] == {"document:title": "required"}


def test_legacy_proposal_response_keeps_empty_field_errors(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    proposal = PagePackageProposal(
        id="proposal-legacy-stage-errors",
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id="job-legacy-stage-errors",
        state="needs_attention",
        proposal_group_id="proposal-legacy-stage-errors",
        current_version_id="proposal-legacy-stage-errors",
        package={},
        rendered_html="",
        config_snapshot={},
        proposed_by=projects.member.id,
    )
    from app.domains.jobs.models import Job

    session.add(
        Job(
            id="job-legacy-stage-errors",
            project_id=projects.member_project.id,
            job_type="page_package_generation",
        )
    )
    session.add(proposal)
    session.flush()
    session.add(
        PageProposalStage(
            proposal_version_id=proposal.id,
            name="validation",
            state="failed",
            result={"field_errors": {"document:title": "required"}},
            errors={"message": "provider unavailable"},
        )
    )
    session.commit()

    response = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal.id}"
    )

    assert response.status_code == 200
    assert response.json()["field_errors"] == {}


def test_page_proposal_preserves_opportunity_focus_keyword(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    generated_package = proposal_blueprint_package()
    generated_package["focus_keyword"] = "andere zoekterm"

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            return {"package": generated_package}

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )

    assert response.status_code == 202
    loaded = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{response.json()['id']}"
    )
    assert loaded.status_code == 200
    assert loaded.json()["state"] == "proposed"
    assert loaded.json()["package"]["focus_keyword"] == opportunity.keyword


def test_rejects_existing_page_target_and_missing_default_blueprint(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    opportunity.target_classification = "existing_page"
    session.commit()

    existing = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )
    assert existing.status_code == 409

    opportunity.target_classification = "new_page"
    session.get(PageBlueprint, "blueprint-service-v2").is_default_for_page_type = False
    session.commit()
    invalid = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )
    assert invalid.status_code == 422


def test_get_proposal_includes_active_candidate(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    proposal = generated_blueprint_proposal(
        client, projects, opportunity, monkeypatch
    )
    session.add(
        PagePackageRegenerationCandidate(
            id="candidate-1",
            proposal_group_id=proposal["proposal_group_id"],
            base_version_id=proposal["id"],
            generation_mode="block",
            target_block_id="hero",
            instruction="Maak de intro scherper.",
            candidate_package=proposal["package"],
            candidate_rendered_html="<section><h2>Nieuwe versie</h2></section>",
            provider="openrouter",
            model="model-2",
            status="ready",
        )
    )
    session.commit()

    loaded = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal['id']}"
    )

    assert loaded.status_code == 200
    assert loaded.json()["active_candidate"]["id"] == "candidate-1"
    assert loaded.json()["active_candidate"]["candidate_package"]["title"] == (
        proposal["package"]["title"]
    )
    assert loaded.json()["active_candidate"]["candidate_rendered_html"] == (
        "<section><h2>Nieuwe versie</h2></section>"
    )


def test_failed_page_generation_preserves_provider_error_detail(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)

    class Generator:
        provider = "openai"
        model = "gpt-test"

        def generate_page_package(self, context):
            raise RuntimeError("response_format json_schema is not supported")

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )

    queued = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )

    assert queued.status_code == 202
    proposal = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{queued.json()['id']}"
    )
    assert proposal.status_code == 200
    assert proposal.json()["state"] == "failed"
    assert proposal.json()["job"]["error_message"] == (
        "response_format json_schema is not supported"
    )


def test_updates_and_approves_proposal_before_wordpress(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            return {
                "package": proposal_blueprint_package(),
                "input_tokens": 0,
                "output_tokens": 0,
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )
    queued = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    ).json()
    created = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{queued['id']}"
    ).json()
    package = created["package"]
    package["title"] = "Aangepaste DSG revisiepagina"

    updated = client.put(
        f"/projects/{projects.member_project.id}/page-proposals/{created['id']}",
        json={"package": package},
    )
    bridge = BlueprintBridge()
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: bridge,
    )
    approved = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/{created['id']}/approve"
    )

    assert updated.status_code == 200
    assert updated.json()["package"]["title"] == "Aangepaste DSG revisiepagina"
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"
    assert approved.json()["approved_by"] == projects.member.id


def test_creates_one_wordpress_draft_only_after_approval(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)

    class Generator:
        provider = "openrouter"
        model = "model-1"

        def generate_page_package(self, context):
            return {"package": proposal_blueprint_package()}

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )
    proposal = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    ).json()
    endpoint = (
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{proposal['id']}/create-draft"
    )
    assert client.post(endpoint).status_code == 409

    bridge = BlueprintBridge()

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: bridge,
    )
    client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{proposal['id']}/approve"
    )
    created = client.post(endpoint)
    repeated = client.post(endpoint)

    assert created.status_code == 200
    assert created.json()["state"] == "draft_created"
    assert created.json()["wordpress_object_id"] == 987
    assert repeated.status_code == 200
    assert bridge.wordpress_ids == [902]
    assert len(bridge.payloads) == 1
    assert bridge.payloads[0]["idempotency_key"] == proposal["id"]
    assert bridge.payloads[0]["expected_version"] == 2
    assert bridge.payloads[0]["expected_structure_hash"] == "hash-v2"
    assert bridge.payloads[0]["replacements"]["acf-title"] == "DSG revisie Schiedam"
    assert bridge.payloads[0]["approved_urls"] == [
        "/contact/",
        "https://member.example/dienst-template/",
    ]
    assert bridge.payloads[0]["seo"]["keyword"] == "dsg versnellingsbak reviseren"
    assert "package" not in bridge.payloads[0]


def test_approval_marks_blueprint_stale_when_wordpress_hash_changed(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    proposal = generated_blueprint_proposal(
        client, projects, opportunity, monkeypatch
    )
    bridge = BlueprintBridge()
    bridge.structure_hash = "changed-hash"
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: bridge,
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{proposal['id']}/approve"
    )

    assert response.status_code == 409
    blueprint = session.get(PageBlueprint, "blueprint-service-v2")
    session.refresh(blueprint)
    assert blueprint.state == "stale"
    assert blueprint.is_default_for_page_type is False


@pytest.mark.parametrize(
    "current_overrides",
    [
        {"wordpress_snapshot_id": 999},
        {"wordpress_blueprint_id": 999},
        {"post_type": "page"},
        {"adapter_version": "acf-v2"},
        {"schema_version": "blueprint-v1"},
        {"builder": "elementor"},
        {"seo_plugin": "rank_math"},
        {"version": 3},
        {"snapshot_version": 3},
        {"structure_hash": "changed-hash"},
    ],
    ids=[
        "snapshot-id",
        "compatibility-snapshot-id",
        "post-type",
        "adapter-version",
        "schema-version",
        "builder",
        "seo-plugin",
        "version",
        "snapshot-version",
        "structure-hash",
    ],
)
def test_native_approval_rejects_snapshot_trust_mismatch(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
    current_overrides,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    blueprint = session.get(PageBlueprint, "blueprint-service-v2")
    blueprint.wordpress_snapshot_id = 902
    blueprint.snapshot_version = 2
    blueprint.schema_version = "snapshot-text-v1"
    blueprint.adapter_version = "acf-v1"
    blueprint.capture_state = "ready"
    blueprint.migration_state = "native"
    blueprint.verified_at = datetime.now(UTC)
    blueprint.content_schema = valid_snapshot_schema()
    session.commit()
    proposal = generated_blueprint_proposal(
        client,
        projects,
        opportunity,
        monkeypatch,
    )
    bridge = BlueprintBridge()
    bridge.current_overrides = current_overrides
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: bridge,
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{proposal['id']}/approve"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Blueprint structure changed; generate a new proposal"
    )
    session.refresh(blueprint)
    assert blueprint.state == "stale"
    assert blueprint.is_default_for_page_type is False


def test_draft_rechecks_wordpress_blueprint_after_approval(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    proposal = generated_blueprint_proposal(
        client, projects, opportunity, monkeypatch
    )
    bridge = BlueprintBridge()
    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: bridge,
    )
    approve = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{proposal['id']}/approve"
    )
    assert approve.status_code == 200
    bridge.version = 3

    response = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{proposal['id']}/create-draft"
    )

    assert response.status_code == 409
    assert bridge.payloads == []


def test_approval_rejects_changed_blueprint_schema_snapshot(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    opportunity = prepare_project(session, projects)
    proposal = generated_blueprint_proposal(
        client, projects, opportunity, monkeypatch
    )
    blueprint = session.get(PageBlueprint, "blueprint-service-v2")
    changed_schema = dict(blueprint.content_schema)
    changed_schema["blocks"] = [dict(changed_schema["blocks"][0])]
    changed_schema["blocks"][0]["semantic_role"] = "introduction"
    blueprint.content_schema = changed_schema
    session.commit()

    response = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{proposal['id']}/approve"
    )

    assert response.status_code == 409
    assert "generate a new proposal" in response.json()["detail"]
