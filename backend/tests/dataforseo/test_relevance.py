from sqlalchemy.orm import Session

from app.domains.dataforseo.relevance import (
    build_keyword_context,
    is_relevant,
    target_url,
)
from app.domains.recommendations.models import CompanyProfile
from app.domains.wordpress.models import WordPressPage
from tests.recommendations.conftest import ProjectFixtures


def _transmission_context(
    session: Session,
    projects: ProjectFixtures,
):
    project = projects.member_project
    session.add(
        CompanyProfile(
            project_id=project.id,
            company_name="SHM Transmissie",
            description=(
                "Specialist in transmissierevisie, koppelingen en automatische "
                "versnellingsbakken."
            ),
            audience="Autobezitters met schakelklachten",
            services=[
                "transmissie revisie",
                "koppeling vervangen",
                "DSG automaat revisie",
            ],
            tone_of_voice="Technisch en duidelijk",
            custom_prompt="",
        )
    )
    session.add_all(
        [
            WordPressPage(
                id="page-clutch",
                project_id=project.id,
                wordpress_object_id=101,
                post_type="page",
                status="publish",
                title="Koppeling vervangen kosten",
                slug="koppeling-vervangen-kosten",
                url=f"{project.domain}/koppeling-vervangen-kosten/",
            ),
            WordPressPage(
                id="page-dsg",
                project_id=project.id,
                wordpress_object_id=102,
                post_type="page",
                status="publish",
                title="DSG automaat reviseren",
                slug="dsg-automaat-reviseren",
                url=f"{project.domain}/dsg-automaat-reviseren/",
            ),
        ]
    )
    session.commit()
    return build_keyword_context(session, project)


def test_context_prefers_services_and_relevant_page_phrases(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    context = _transmission_context(session, projects)

    assert "transmissie revisie" in context.seeds
    assert "koppeling vervangen" in context.seeds
    assert "dsg automaat revisie" in context.seeds
    assert "koppeling vervangen kosten" in context.seeds
    assert "member.example" not in context.seeds
    assert "kosten" not in context.seeds
    assert len(context.seeds) <= 20


def test_relevance_rejects_other_automotive_topics_and_matches_service_pages(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    context = _transmission_context(session, projects)

    assert not is_relevant("autosleutel bijmaken", context)
    assert not is_relevant("krassen auto verwijderen kosten", context)
    assert is_relevant("koppeling vervangen kosten", context)
    assert is_relevant("dsg automaat reviseren", context)
    assert target_url("koppeling vervangen kosten", context).endswith(
        "/koppeling-vervangen-kosten/"
    )
    assert target_url("dsg automaat reviseren", context).endswith(
        "/dsg-automaat-reviseren/"
    )


def test_wordpress_pages_provide_fallback_context_without_company_profile(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    project = projects.member_project
    session.add(
        WordPressPage(
            id="page-transmission",
            project_id=project.id,
            wordpress_object_id=103,
            post_type="page",
            status="publish",
            title="Automatische transmissie revisie",
            slug="automatische-transmissie-revisie",
            url=f"{project.domain}/automatische-transmissie-revisie/",
        )
    )
    session.commit()

    context = build_keyword_context(session, project)

    assert "automatische transmissie revisie" in context.seeds
    assert is_relevant("transmissie laten reviseren", context)
