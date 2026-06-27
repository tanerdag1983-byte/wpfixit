from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.wordpress.models import WordPressPage
from tests.recommendations.conftest import ProjectFixtures

REQUIRED_MAPPING = {
    "hero_title": "element.hero.settings.title",
    "introduction": "element.intro.settings.editor",
    "main_content": "element.main.settings.editor",
    "faq": "element.faq.settings.editor",
    "cta_title": "element.cta.settings.title",
    "cta_text": "element.cta.settings.editor",
}


def _save_settings(
    client: TestClient,
    session: Session,
    projects: ProjectFixtures,
) -> None:
    page = WordPressPage(
        id="template-page",
        project_id=projects.member_project.id,
        wordpress_object_id=701,
        post_type="page",
        status="publish",
        title="Elementor template",
        slug="elementor-template",
        url="https://member.example/elementor-template/",
        content_hash="inventory-hash",
    )
    session.add(page)
    session.commit()
    response = client.put(
        f"/projects/{projects.member_project.id}/page-package-settings",
        json={
            "builder": "elementor",
            "template_wordpress_page_id": page.id,
            "seo_plugin": "yoast",
            "slot_mapping": REQUIRED_MAPPING,
        },
    )
    assert response.status_code == 200


def test_inspects_and_validates_template_mapping(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    _save_settings(client, session, projects)

    class Bridge:
        def builders(self) -> dict:
            return {"builders": ["gutenberg", "elementor"], "seo_plugin": "yoast"}

        def template_slots(self, object_id: int, builder: str) -> dict:
            assert object_id == 701
            assert builder == "elementor"
            return {
                "builder": "elementor",
                "seo_plugin": "yoast",
                "template_hash": "live-template-hash",
                "slots": [
                    {"path": path, "label": slot, "value_type": "html"}
                    for slot, path in REQUIRED_MAPPING.items()
                ],
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: Bridge(),
    )

    inspected = client.post(
        f"/projects/{projects.member_project.id}/page-package-settings/inspect-template"
    )
    validated = client.post(
        f"/projects/{projects.member_project.id}/page-package-settings/validate"
    )
    options = client.get(
        f"/projects/{projects.member_project.id}/page-package-settings/options"
    )

    assert inspected.status_code == 200
    assert len(inspected.json()["slots"]) == 6
    assert validated.status_code == 200
    assert validated.json()["validation_state"] == "valid"
    assert validated.json()["template_content_hash"] == "live-template-hash"
    assert options.json() == {
        "builders": ["gutenberg", "elementor"],
        "seo_plugin": "yoast",
    }


def test_validation_rejects_stale_or_missing_slot_mapping(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    _save_settings(client, session, projects)

    class Bridge:
        def template_slots(self, object_id: int, builder: str) -> dict:
            return {
                "builder": "elementor",
                "seo_plugin": "yoast",
                "template_hash": "changed-hash",
                "slots": [
                    {
                        "path": "element.hero.settings.title",
                        "label": "Hero",
                        "value_type": "text",
                    }
                ],
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: Bridge(),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/page-package-settings/validate"
    )

    assert response.status_code == 409
    assert "mapped slots" in response.json()["detail"]
