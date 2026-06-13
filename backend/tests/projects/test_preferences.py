from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.projects.conftest import ProjectFixtures


def test_profile_preferences_are_saved(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)

    response = client.patch(
        "/profile/preferences",
        json={"dashboard_view": "action", "locale": "en"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "dashboard_view": "action",
        "locale": "en",
    }
    session.refresh(projects.member)
    assert projects.member.dashboard_view == "action"
    assert projects.member.locale == "en"


def test_owner_can_update_organization_branding(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)

    response = client.patch(
        f"/organizations/{projects.organization.id}/branding",
        json={
            "brand_name": "SearchPilot",
            "primary_color": "#102f26",
            "accent_color": "#c8ff4d",
        },
    )

    assert response.status_code == 200
    assert response.json()["brand_name"] == "SearchPilot"
    session.refresh(projects.organization)
    assert projects.organization.brand_name == "SearchPilot"
