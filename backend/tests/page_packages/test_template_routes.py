import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.domains.page_blueprints.models  # noqa: F401
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


def test_validation_rejects_duplicate_non_acf_mapping_paths(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    _save_settings(client, session, projects)
    duplicate_mapping = {
        **REQUIRED_MAPPING,
        "introduction": REQUIRED_MAPPING["hero_title"],
    }
    saved = client.put(
        f"/projects/{projects.member_project.id}/page-package-settings",
        json={
            "builder": "elementor",
            "template_wordpress_page_id": "template-page",
            "seo_plugin": "yoast",
            "slot_mapping": duplicate_mapping,
        },
    )
    assert saved.status_code == 200

    class Bridge:
        def template_slots(self, object_id: int, builder: str) -> dict:
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

    response = client.post(
        f"/projects/{projects.member_project.id}/page-package-settings/validate"
    )

    assert response.status_code == 409


def test_validation_allows_optional_cta_slots_for_global_content(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="template-page",
        project_id=projects.member_project.id,
        wordpress_object_id=701,
        post_type="page",
        status="publish",
        title="ACF template",
        slug="acf-template",
        url="https://member.example/acf-template/",
        content_hash="inventory-hash",
    )
    session.add(page)
    session.commit()
    duplicate_mapping = {
        "hero_title": "acf-block:field_page_blocks:0",
        "introduction": "acf-block:field_page_blocks:0",
        "main_content": "acf:field_summary",
        "faq": "acf-block:field_page_blocks:2",
    }
    response = client.put(
        f"/projects/{projects.member_project.id}/page-package-settings",
        json={
            "builder": "acf",
            "template_wordpress_page_id": page.id,
            "seo_plugin": "yoast",
            "slot_mapping": duplicate_mapping,
        },
    )
    assert response.status_code == 200

    class Bridge:
        def template_slots(self, object_id: int, builder: str) -> dict:
            assert object_id == 701
            assert builder == "acf"
            return {
                "builder": "acf",
                "seo_plugin": "yoast",
                "template_hash": "live-template-hash",
                "slots": [
                    {
                        "path": "acf-block:field_page_blocks:0",
                        "label": "Paginablokken · Hero",
                        "value_type": "html",
                    },
                    {
                        "path": "acf:field_summary",
                        "label": "Samenvatting",
                        "value_type": "html",
                    },
                    {
                        "path": "acf-block:field_page_blocks:2",
                        "label": "Paginablokken · FAQ",
                        "value_type": "html",
                    },
                ],
            }

    monkeypatch.setattr(
        "app.api.routes.page_packages._page_package_client",
        lambda session, project_id: Bridge(),
    )

    validated = client.post(
        f"/projects/{projects.member_project.id}/page-package-settings/validate"
    )

    assert validated.status_code == 200
    assert validated.json()["validation_state"] == "valid"


@pytest.mark.parametrize(
    "cta_path",
    ["element.missing.cta", REQUIRED_MAPPING["hero_title"]],
)
def test_validation_rejects_invalid_optional_cta_mapping(
    cta_path: str,
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    _save_settings(client, session, projects)
    mapping = {**REQUIRED_MAPPING, "cta_title": cta_path}
    saved = client.put(
        f"/projects/{projects.member_project.id}/page-package-settings",
        json={
            "builder": "elementor",
            "template_wordpress_page_id": "template-page",
            "seo_plugin": "yoast",
            "slot_mapping": mapping,
        },
    )
    assert saved.status_code == 200

    class Bridge:
        def template_slots(self, object_id: int, builder: str) -> dict:
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

    response = client.post(
        f"/projects/{projects.member_project.id}/page-package-settings/validate"
    )

    assert response.status_code == 409
