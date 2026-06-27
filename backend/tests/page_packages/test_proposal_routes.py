from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.page_packages.models import ProjectPagePackageSettings
from app.domains.recommendations.models import (
    AiConnection,
    CompanyProfile,
    ProjectAiPolicy,
)
from app.domains.wordpress.models import WordPressPage
from tests.page_packages.test_generation import valid_package
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
                "package": proposal_package(),
                "input_tokens": 100,
                "output_tokens": 200,
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal"
    )

    assert response.status_code == 202
    proposal_id = response.json()["id"]
    loaded = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/{proposal_id}"
    )
    assert loaded.status_code == 200
    assert loaded.json()["state"] == "proposed"
    assert loaded.json()["package"]["focus_keyword"] == opportunity.keyword
    assert loaded.json()["job"]["state"] == "completed"


def test_rejects_existing_page_target_and_unvalidated_configuration(
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
        f"{opportunity.id}/page-proposal"
    )
    assert existing.status_code == 409

    opportunity.target_classification = "new_page"
    session.get(
        ProjectPagePackageSettings, projects.member_project.id
    ).validation_state = "invalid"
    session.commit()
    invalid = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal"
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
                "package": proposal_package(),
                "input_tokens": 0,
                "output_tokens": 0,
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )
    created = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal"
    ).json()
    package = created["package"]
    package["title"] = "Aangepaste DSG revisiepagina"

    updated = client.put(
        f"/projects/{projects.member_project.id}/page-proposals/{created['id']}",
        json={"package": package},
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
            return {"package": proposal_package()}

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_generator",
        lambda session, project: Generator(),
    )
    proposal = client.post(
        f"/projects/{projects.member_project.id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal"
    ).json()
    endpoint = (
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{proposal['id']}/create-draft"
    )
    assert client.post(endpoint).status_code == 409

    calls = []

    class Bridge:
        def create_draft(self, payload):
            calls.append(payload)
            assert payload["idempotency_key"] == proposal["id"]
            assert payload["expected_template_hash"] == "template-hash"
            return {
                "wordpress_object_id": 987,
                "edit_url": "https://member.example/wp-admin/post.php?post=987",
                "status": "draft",
                "content_hash": "draft-hash",
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: Bridge(),
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
    assert len(calls) == 1
