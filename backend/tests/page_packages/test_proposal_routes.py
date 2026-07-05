from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_packages.models import ProjectPagePackageSettings
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


class BlueprintBridge:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.wordpress_ids: list[int] = []
        self.version = 2
        self.structure_hash = "hash-v2"

    def blueprint(self, wordpress_blueprint_id: int) -> dict:
        return {
            "status": "ready",
            "version": self.version,
            "structure_hash": self.structure_hash,
        }

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
