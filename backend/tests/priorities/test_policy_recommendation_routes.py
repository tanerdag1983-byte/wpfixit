from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import priorities
from app.domains.audits.models import PageAudit
from app.domains.recommendations.models import (
    AiConnection,
    CompanyProfile,
    ProjectAiPolicy,
)
from app.domains.recommendations.provider import ProviderGenerationError
from app.domains.recommendations.schemas import (
    EvidenceItem,
    PageFacts,
    RecommendationResult,
)
from app.domains.wordpress.models import WordPressPage
from tests.projects.conftest import ProjectFixtures


class Generator:
    def __init__(
        self,
        provider: str,
        model: str,
        *,
        fail: bool = False,
    ) -> None:
        self.provider = provider
        self.model = model
        self.fail = fail

    def generate(self, facts: PageFacts) -> RecommendationResult:
        if self.fail:
            raise ProviderGenerationError("provider unavailable")
        return RecommendationResult(
            action_type="content",
            priority="high",
            action_title="Verbeter de inhoud van de servicepagina",
            explanation=(
                "De audit toont dat bezoekers meer concrete informatie nodig hebben."
            ),
            recommendation="Werk de pagina bij met aantoonbare informatie.",
            rationale="De audit toont een inhoudelijke kans.",
            evidence=[facts.evidence[0].id],
            provider=self.provider,
            model=self.model,
        )


class CaptureGenerator:
    def __init__(self) -> None:
        self.facts: PageFacts | None = None

    def generate(self, facts: PageFacts) -> RecommendationResult:
        self.facts = facts
        return RecommendationResult(
            action_type="meta_description",
            priority="high",
            action_title="Maak de meta description concreter",
            explanation="De huidige snippet mist een duidelijke propositie.",
            recommendation="Specialist in transmissierevisie met snelle diagnose.",
            rationale="De huidige snippet mist concrete propositie.",
            evidence=[facts.evidence[0].id],
            provider="gemini",
            model="gemini-2.5-flash",
        )


def test_project_policy_builds_primary_and_fallback_with_company_context(
    session: Session,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    primary = AiConnection(
        id="primary-ai",
        organization_id=projects.organization.id,
        name="Primary",
        provider="openai",
        base_url="https://api.openai.com/v1",
        encrypted_api_key="encrypted",
        enabled=True,
    )
    fallback = AiConnection(
        id="fallback-ai",
        organization_id=projects.organization.id,
        name="Fallback",
        provider="anthropic",
        base_url="https://api.anthropic.com/v1",
        encrypted_api_key="encrypted",
        enabled=True,
    )
    session.add_all(
        [
            primary,
            fallback,
            ProjectAiPolicy(
                project_id=projects.member_project.id,
                organization_id=projects.organization.id,
                primary_connection_id=primary.id,
                primary_model="primary-model",
                fallback_connection_id=fallback.id,
                fallback_model="fallback-model",
            ),
            CompanyProfile(
                project_id=projects.member_project.id,
                company_name="SHM Transmissie",
                description="Transmissiespecialist",
                audience="Autobezitters",
                services=["Diagnose"],
                tone_of_voice="Deskundig",
                custom_prompt="Gebruik alleen aantoonbare claims.",
            ),
        ]
    )
    session.commit()
    calls: list[tuple[str, str, str]] = []

    def build(connection, model, company_context):
        calls.append((connection.id, model, company_context))
        return Generator(
            connection.provider,
            model,
            fail=connection.id == primary.id,
        )

    monkeypatch.setattr(priorities, "build_generator", build)
    generator = priorities._recommendation_generator(
        session,
        projects.member_project,
    )
    result = generator.generate(
        PageFacts(
            url="https://member.example/revisie",
            title="Revisie",
            priority_score=80,
            components={"audit": 20.0},
            evidence=[
                EvidenceItem(
                    id="audit:policy",
                    source="audit",
                    excerpt="De pagina mist inhoud.",
                )
            ],
        )
    )

    assert result.provider == "anthropic"
    assert result.model == "fallback-model"
    assert [call[:2] for call in calls] == [
        ("primary-ai", "primary-model"),
        ("fallback-ai", "fallback-model"),
    ]
    assert "SHM Transmissie" in calls[0][2]
    assert "Gebruik alleen aantoonbare claims." in calls[0][2]


def test_generation_endpoint_records_provider_model_prompt_and_proposal_state(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="wp-policy-route",
        project_id=projects.member_project.id,
        wordpress_object_id=142,
        post_type="page",
        status="publish",
        title="Transmissie revisie",
        slug="revisie",
        url="https://member.example/revisie",
    )
    session.add_all(
        [
            page,
            CompanyProfile(
                project_id=projects.member_project.id,
                company_name="SHM Transmissie",
                description="Transmissiespecialist",
                audience="Autobezitters",
                services=["Revisie"],
                tone_of_voice="Deskundig",
                custom_prompt="Schrijf concreet.",
            ),
        ]
    )
    session.flush()
    session.add(
        PageAudit(
            id="audit-policy-route",
            project_id=projects.member_project.id,
            wordpress_page_id=page.id,
            score=45,
            page_type_label="service",
            facts={"importance": 0.8},
        )
    )
    session.commit()
    monkeypatch.setattr(
        priorities,
        "_recommendation_generator",
        lambda *_: Generator("gemini", "gemini-2.5-flash"),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/recommendations/generate",
        params={"limit": 1},
    )

    assert response.status_code == 200
    recommendation = response.json()["items"][0]
    assert recommendation["wordpress_page_id"] == page.id
    assert recommendation["provider"] == "gemini"
    assert recommendation["model"] == "gemini-2.5-flash"
    assert recommendation["approval_state"] == "proposed"
    assert recommendation["action_title"] == "Verbeter de inhoud van de servicepagina"
    assert (
        recommendation["explanation"]
        == "De audit toont dat bezoekers meer concrete informatie nodig hebben."
    )
    assert (
        recommendation["recommendation"]
        == "Werk de pagina bij met aantoonbare informatie."
    )
    assert len(recommendation["prompt_version"]) == 64

    listed = client.get(
        f"/projects/{projects.member_project.id}/recommendations",
        params={"limit": 1},
    )

    assert listed.status_code == 200
    listed_recommendation = listed.json()["items"][0]
    assert (
        listed_recommendation["action_title"]
        == "Verbeter de inhoud van de servicepagina"
    )
    assert (
        listed_recommendation["explanation"]
        == "De audit toont dat bezoekers meer concrete informatie nodig hebben."
    )


def test_generation_endpoint_sends_current_wordpress_context_to_generator(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="wp-context-route",
        project_id=projects.member_project.id,
        wordpress_object_id=188,
        post_type="page",
        status="publish",
        title="Automaatbak revisie",
        slug="automaatbak-revisie",
        url="https://member.example/automaatbak-revisie",
    )
    session.add(page)
    session.flush()
    session.add(
        PageAudit(
            id="audit-context-route",
            project_id=projects.member_project.id,
            wordpress_page_id=page.id,
            score=52,
            page_type_label="service",
            facts={"importance": 0.7},
        )
    )
    session.commit()
    generator = CaptureGenerator()
    monkeypatch.setattr(priorities, "_recommendation_generator", lambda *_: generator)
    monkeypatch.setattr(
        priorities,
        "_wordpress_context",
        lambda *_: {
            "seo_plugin": "yoast",
            "current_values": {
                "seo_title": "Oude SEO title",
                "meta_description": "Oude meta description",
                "content": "<p>Huidige WordPress content</p>",
            },
        },
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/recommendations/generate",
        params={"limit": 1},
    )

    assert response.status_code == 200
    assert generator.facts is not None
    assert generator.facts.wordpress_object_id == 188
    assert generator.facts.post_type == "page"
    assert generator.facts.status == "publish"
    assert generator.facts.seo_plugin == "yoast"
    assert generator.facts.current_values["content"] == (
        "<p>Huidige WordPress content</p>"
    )
