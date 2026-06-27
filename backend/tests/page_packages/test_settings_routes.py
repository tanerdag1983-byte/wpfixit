from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.wordpress.models import WordPressPage
from tests.recommendations.conftest import ProjectFixtures


def _template_page(
    session: Session,
    project_id: str,
    *,
    page_id: str = "template-page",
    object_id: int = 501,
) -> WordPressPage:
    page = WordPressPage(
        id=page_id,
        project_id=project_id,
        wordpress_object_id=object_id,
        post_type="page",
        status="publish",
        title="Dienst template",
        slug="dienst-template",
        url=f"https://template.example/{page_id}/",
        content_hash="template-hash",
    )
    session.add(page)
    session.commit()
    return page


def test_owner_saves_project_specific_page_package_settings(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    page = _template_page(session, projects.member_project.id)

    response = client.put(
        f"/projects/{projects.member_project.id}/page-package-settings",
        json={
            "builder": "elementor",
            "template_wordpress_page_id": page.id,
            "seo_plugin": "yoast",
            "slot_mapping": {
                "hero_title": "element.hero.settings.title",
                "introduction": "element.intro.settings.editor",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["builder"] == "elementor"
    assert response.json()["template_wordpress_page_id"] == page.id
    assert response.json()["validation_state"] == "unvalidated"

    loaded = client.get(
        f"/projects/{projects.member_project.id}/page-package-settings"
    )
    assert loaded.status_code == 200
    assert loaded.json()["slot_mapping"]["hero_title"].startswith("element.")


def test_page_package_settings_reject_template_from_another_project(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    foreign_page = _template_page(
        session,
        projects.other_project.id,
        page_id="foreign-template",
        object_id=502,
    )

    response = client.put(
        f"/projects/{projects.member_project.id}/page-package-settings",
        json={
            "builder": "gutenberg",
            "template_wordpress_page_id": foreign_page.id,
            "seo_plugin": "rank_math",
            "slot_mapping": {},
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Template page not found"


def test_page_package_settings_validate_supported_builder(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    page = _template_page(session, projects.member_project.id)

    response = client.put(
        f"/projects/{projects.member_project.id}/page-package-settings",
        json={
            "builder": "unknown-builder",
            "template_wordpress_page_id": page.id,
            "seo_plugin": "yoast",
            "slot_mapping": {},
        },
    )

    assert response.status_code == 422
