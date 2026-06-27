from sqlalchemy.orm import Session

from app.domains.dataforseo.relevance import (
    build_keyword_context,
    classify_target,
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
            WordPressPage(
                id="page-alfa",
                project_id=project.id,
                wordpress_object_id=103,
                post_type="page",
                status="publish",
                title="Alfa Romeo reviseren versnellingsbak",
                slug="alfa-romeo-reviseren-versnellingsbak",
                url=f"{project.domain}/alfa-romeo-reviseren-versnellingsbak/",
            ),
            WordPressPage(
                id="page-cupra",
                project_id=project.id,
                wordpress_object_id=104,
                post_type="page",
                status="publish",
                title="Cupra versnellingsbak problemen oplossingen",
                slug="cupra-versnellingsbak-problemen-oplossingen",
                url=(
                    f"{project.domain}/cupra-versnellingsbak-problemen-oplossingen/"
                ),
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


def test_target_classification_does_not_cross_brand_or_force_generic_query(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    context = _transmission_context(session, projects)

    vw = classify_target("vw dsg versnellingsbak reviseren", context)
    generic = classify_target("problemen automatische versnellingsbak", context)

    assert vw.classification == "new_page"
    assert vw.url is None
    assert generic.classification == "new_page"
    assert generic.url is None


def test_target_classification_uses_distinctive_entity_or_shared_phrase(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    context = _transmission_context(session, projects)

    cupra = classify_target("cupra automatische versnellingsbak problemen", context)
    alfa = classify_target("alfa romeo versnellingsbak revisie", context)
    clutch = classify_target("koppeling vervangen prijs", context)

    assert cupra.classification == "existing_page"
    assert cupra.url.endswith("/cupra-versnellingsbak-problemen-oplossingen/")
    assert alfa.classification == "existing_page"
    assert alfa.url.endswith("/alfa-romeo-reviseren-versnellingsbak/")
    assert clutch.classification == "existing_page"
    assert clutch.url.endswith("/koppeling-vervangen-kosten/")


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
