from fastapi.testclient import TestClient

from tests.recommendations.conftest import ProjectFixtures


def test_legacy_organization_ai_settings_routes_are_removed(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)

    get_response = client.get(f"/organizations/{projects.organization.id}/ai-settings")
    put_response = client.put(
        f"/organizations/{projects.organization.id}/ai-settings",
        json={},
    )
    test_response = client.post(
        f"/organizations/{projects.organization.id}/ai-settings/test"
    )

    assert get_response.status_code == 404
    assert put_response.status_code == 404
    assert test_response.status_code == 404


def test_project_company_profile_and_prompt_are_saved(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)

    response = client.put(
        f"/projects/{projects.member_project.id}/company-profile",
        json={
            "company_name": "Member Transmissie",
            "description": "Specialist in automatische transmissies.",
            "audience": "Autobezitters in Nederland",
            "services": ["Revisie", "Diagnose"],
            "tone_of_voice": "Deskundig en helder",
            "custom_prompt": "Benadruk vakmanschap en vermijd overdreven claims.",
        },
    )

    assert response.status_code == 200
    assert response.json()["company_name"] == "Member Transmissie"
    assert "vakmanschap" in response.json()["custom_prompt"]

    get_response = client.get(f"/projects/{projects.member_project.id}/company-profile")
    assert get_response.status_code == 200
    assert get_response.json() == response.json()
