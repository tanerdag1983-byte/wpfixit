from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import priorities
from app.domains.audits.models import PageAudit, SeoRecommendation
from app.domains.ga4.models import Ga4PagePerformance
from app.domains.gsc.models import GscPagePerformance
from app.domains.jobs.models import Job
from app.domains.recommendations.models import CompanyProfile, ProjectAiPolicy
from app.domains.recommendations.schemas import EvidenceItem, PageFacts
from app.domains.recommendations.service import (
    RuleBasedRecommendationGenerator,
    persist_recommendation,
)
from app.domains.wordpress.models import WordPressPage
from tests.projects.conftest import ProjectFixtures


def test_priority_endpoint_combines_wordpress_gsc_and_ga4(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="wp-priority",
        project_id=projects.member_project.id,
        wordpress_object_id=42,
        post_type="page",
        status="publish",
        title="Transmissie revisie",
        slug="revisie",
        url="https://member.example/revisie",
    )
    session.add(page)
    session.flush()
    session.add(
        PageAudit(
            id="audit-priority",
            project_id=projects.member_project.id,
            wordpress_page_id=page.id,
            score=48,
            page_type_label="service",
            facts={"importance": 0.9},
        )
    )
    today = date.today()
    for offset, clicks, sessions, conversions in (
        (30, 180, 1_800, 18),
        (5, 80, 1_100, 3),
    ):
        row_date = today - timedelta(days=offset)
        session.add_all(
            [
                GscPagePerformance(
                    id=f"gsc-{offset}",
                    project_id=projects.member_project.id,
                    property_uri="sc-domain:member.example",
                    date=row_date,
                    page_url=page.url,
                    clicks=clicks,
                    impressions=10_000,
                    ctr=clicks / 10_000,
                    average_position=4.8,
                ),
                Ga4PagePerformance(
                    id=f"ga4-{offset}",
                    project_id=projects.member_project.id,
                    property_id="123",
                    date=row_date,
                    page_path="/revisie",
                    sessions=sessions,
                    active_users=sessions - 100,
                    engagement_rate=0.58,
                    key_events=conversions,
                    revenue=None,
                ),
            ]
        )
    session.commit()

    response = client.get(f"/projects/{projects.member_project.id}/seo-priority-score")

    assert response.status_code == 200
    result = response.json()["items"][0]
    assert result["url"] == page.url
    assert result["seo_score"] == 48
    assert result["clicks"] == 260
    assert result["impressions"] == 20_000
    assert result["sessions"] == 2_900
    assert result["conversions"] == 21
    assert result["priority_score"] > 50
    assert result["action"]
    assert result["evidence"]

    first = client.post(
        f"/projects/{projects.member_project.id}/recommendations/generate",
        params={"limit": 1},
    )
    second = client.post(
        f"/projects/{projects.member_project.id}/recommendations/generate",
        params={"limit": 1},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    for response in (first, second):
        job = session.get(Job, response.json()["job"]["id"])
        assert job is not None
        priorities._generate_recommendations_for_job(
            session,
            job,
            projects.member_project,
            1,
        )
    assert session.scalar(select(func.count(SeoRecommendation.id))) == 1

    saved = client.get(
        f"/projects/{projects.member_project.id}/recommendations",
        params={"limit": 10},
    )

    assert saved.status_code == 200
    recommendation = saved.json()["items"][0]
    assert recommendation["approval_state"] == "proposed"
    assert recommendation["provider"] == "rules"
    assert recommendation["prompt_version"] is None
    assert recommendation["url"] == page.url


def test_changed_company_prompt_creates_a_new_recommendation_version(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    page = WordPressPage(
        id="wp-prompt-version",
        project_id=projects.member_project.id,
        wordpress_object_id=84,
        post_type="page",
        status="publish",
        title="Automaatbak onderhoud",
        slug="onderhoud",
        url="https://member.example/onderhoud",
    )
    session.add(page)
    session.commit()
    facts = PageFacts(
        url=page.url,
        title=page.title,
        priority_score=72,
        components={"audit": 22.0},
        evidence=[
            EvidenceItem(
                id="audit:prompt-version",
                source="audit",
                excerpt="De title ontbreekt.",
            )
        ],
    )

    first = persist_recommendation(
        session,
        projects.member_project,
        page,
        facts,
        RuleBasedRecommendationGenerator(),
        prompt_version="prompt-v1",
    )
    second = persist_recommendation(
        session,
        projects.member_project,
        page,
        facts,
        RuleBasedRecommendationGenerator(),
        prompt_version="prompt-v2",
    )

    assert first.id != second.id
    assert second.prompt_version == "prompt-v2"
    assert session.scalar(select(func.count(SeoRecommendation.id))) == 2


def test_changed_recommendation_engine_version_creates_new_recommendation(
    session: Session,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    from app.domains.recommendations import service

    page = WordPressPage(
        id="wp-engine-version",
        project_id=projects.member_project.id,
        wordpress_object_id=85,
        post_type="page",
        status="publish",
        title="Transmissie diagnose",
        slug="diagnose",
        url="https://member.example/diagnose",
    )
    session.add(page)
    session.commit()
    facts = PageFacts(
        url=page.url,
        title=page.title,
        priority_score=68,
        components={"audit": 18.0},
        evidence=[
            EvidenceItem(
                id="audit:engine-version",
                source="audit",
                excerpt="De pagina mist concrete uitleg.",
            )
        ],
    )

    first = persist_recommendation(
        session,
        projects.member_project,
        page,
        facts,
        RuleBasedRecommendationGenerator(),
    )
    monkeypatch.setattr(service, "RECOMMENDATION_ENGINE_VERSION", "rules-v-next")
    second = persist_recommendation(
        session,
        projects.member_project,
        page,
        facts,
        RuleBasedRecommendationGenerator(),
    )

    assert first.id != second.id
    assert session.scalar(select(func.count(SeoRecommendation.id))) == 2


def test_company_profile_prompt_version_is_stable_and_content_sensitive() -> None:
    from app.api.routes.priorities import _prompt_version

    profile = CompanyProfile(
        project_id="project-prompt",
        company_name="SHM Transmissie",
        description="Specialist",
        audience="Autobezitters",
        services=["Diagnose", "Revisie"],
        tone_of_voice="Deskundig",
        custom_prompt="Gebruik alleen aantoonbare claims.",
    )
    policy = ProjectAiPolicy(
        project_id="project-prompt",
        organization_id="org-prompt",
        primary_connection_id="openai-main",
        primary_model="gpt-5.4-mini",
        fallback_connection_id=None,
        fallback_model=None,
    )

    first = _prompt_version(profile, policy)
    second = _prompt_version(profile, policy)
    profile.custom_prompt = "Leg iedere aanbeveling kort uit."

    assert first == second
    assert first != _prompt_version(profile, policy)


def test_ai_policy_is_part_of_prompt_version() -> None:
    from app.api.routes.priorities import _prompt_version

    profile = CompanyProfile(
        project_id="project-policy-version",
        company_name="SHM Transmissie",
        description="Specialist",
        audience="Autobezitters",
        services=["Diagnose"],
        tone_of_voice="Deskundig",
        custom_prompt="Gebruik bewijs.",
    )
    policy = ProjectAiPolicy(
        project_id="project-policy-version",
        organization_id="org-policy-version",
        primary_connection_id="openai-main",
        primary_model="gpt-5.4-mini",
        fallback_connection_id=None,
        fallback_model=None,
    )

    first = _prompt_version(profile, policy)
    policy.primary_model = "gpt-5.5"
    changed_model = _prompt_version(profile, policy)
    policy.primary_connection_id = "gemini-main"
    changed_connection = _prompt_version(profile, policy)

    assert first != changed_model
    assert changed_model != changed_connection
