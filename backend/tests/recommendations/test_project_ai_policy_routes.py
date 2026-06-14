from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.projects.models import Organization, OrganizationMember
from tests.recommendations.conftest import ProjectFixtures

ENCRYPTION_KEY = "MDAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="


def create_connection(
    client: TestClient,
    organization_id: str,
    name: str,
    *,
    enabled: bool = True,
) -> dict:
    response = client.post(
        f"/organizations/{organization_id}/ai-connections",
        json={
            "name": name,
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "default_model": "default-model",
            "api_key": "secret",
            "enabled": enabled,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_owner_saves_and_reads_primary_and_fallback_policy(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(get_settings(), "encryption_key", ENCRYPTION_KEY)
    auth_as(projects.member)
    primary = create_connection(client, projects.organization.id, "Primary")
    fallback = create_connection(client, projects.organization.id, "Fallback")

    response = client.put(
        f"/projects/{projects.member_project.id}/ai-policy",
        json={
            "primary_connection_id": primary["id"],
            "primary_model": "primary-model",
            "fallback_connection_id": fallback["id"],
            "fallback_model": "fallback-model",
        },
    )

    assert response.status_code == 200
    assert response.json()["primary"]["name"] == "Primary"
    assert response.json()["fallback"]["model"] == "fallback-model"
    assert (
        client.get(f"/projects/{projects.member_project.id}/ai-policy").json()
        == response.json()
    )


def test_policy_rejects_disabled_or_cross_organization_connection(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(get_settings(), "encryption_key", ENCRYPTION_KEY)
    other_org = Organization(id="org-third", name="Third")
    session.add(other_org)
    session.add(
        OrganizationMember(
            organization_id=other_org.id,
            profile_id=projects.member.id,
            role="owner",
        )
    )
    session.commit()
    auth_as(projects.member)
    disabled = create_connection(
        client, projects.organization.id, "Disabled", enabled=False
    )
    foreign = create_connection(client, other_org.id, "Foreign")

    for connection_id in (disabled["id"], foreign["id"]):
        response = client.put(
            f"/projects/{projects.member_project.id}/ai-policy",
            json={
                "primary_connection_id": connection_id,
                "primary_model": "model",
            },
        )
        assert response.status_code == 422


def test_policy_requires_matching_fallback_fields(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(get_settings(), "encryption_key", ENCRYPTION_KEY)
    auth_as(projects.member)
    primary = create_connection(client, projects.organization.id, "Primary")

    response = client.put(
        f"/projects/{projects.member_project.id}/ai-policy",
        json={
            "primary_connection_id": primary["id"],
            "primary_model": "model",
            "fallback_connection_id": primary["id"],
        },
    )

    assert response.status_code == 422
