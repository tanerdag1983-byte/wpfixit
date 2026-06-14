from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text
from app.domains.projects.models import OrganizationMember
from app.domains.recommendations.models import AiConnection, ProjectAiPolicy
from tests.recommendations.conftest import ProjectFixtures

ENCRYPTION_KEY = "MDAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "encryption_key", ENCRYPTION_KEY)


def connection_payload(**overrides) -> dict:
    payload = {
        "name": "OpenAI production",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-5.4-mini",
        "api_key": "secret-key",
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def create_connection(
    client: TestClient,
    projects: ProjectFixtures,
    **overrides,
) -> dict:
    response = client.post(
        f"/organizations/{projects.organization.id}/ai-connections",
        json=connection_payload(**overrides),
    )
    assert response.status_code == 201
    return response.json()


def set_member_role(
    session: Session,
    projects: ProjectFixtures,
    role: str,
) -> None:
    membership = session.get(
        OrganizationMember,
        (projects.organization.id, projects.member.id),
    )
    assert membership is not None
    membership.role = role
    session.commit()


def test_connection_routes_have_explicit_credential_free_response_models(
    auth_as,
) -> None:
    expected_fields = {
        "id",
        "name",
        "provider",
        "base_url",
        "default_model",
        "enabled",
        "last_tested_at",
        "last_test_status",
        "last_test_message",
        "configured",
    }
    routes = {
        (route.path, next(iter(route.methods))): route
        for route in auth_as.app.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/organizations/{organization_id}/ai-connections")
    }

    item_routes = [
        routes[("/organizations/{organization_id}/ai-connections", "POST")],
        routes[
            (
                "/organizations/{organization_id}/ai-connections/{connection_id}",
                "PUT",
            )
        ],
    ]
    list_route = routes[("/organizations/{organization_id}/ai-connections", "GET")]
    test_route = routes[
        (
            "/organizations/{organization_id}/ai-connections/{connection_id}/test",
            "POST",
        )
    ]

    for route in item_routes:
        assert route.response_model is not None
        assert set(route.response_model.model_fields) == expected_fields
    assert list_route.response_model is not None
    assert set(list_route.response_model.model_fields) == {"items"}
    assert (
        set(
            list_route.response_model.model_fields["items"]
            .annotation.__args__[0]
            .model_fields
        )
        == expected_fields
    )
    assert test_route.response_model is not None
    assert set(test_route.response_model.model_fields) == expected_fields


def test_owner_can_create_list_update_and_delete_connection(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)

    created = create_connection(client, projects)

    assert UUID(created["id"]).version == 4
    assert created == {
        "id": created["id"],
        "name": "OpenAI production",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-5.4-mini",
        "enabled": True,
        "last_tested_at": None,
        "last_test_status": None,
        "last_test_message": None,
        "configured": True,
    }
    assert "secret-key" not in str(created)
    assert "api_key" not in created
    assert "encrypted_api_key" not in created

    list_response = client.get(
        f"/organizations/{projects.organization.id}/ai-connections"
    )
    assert list_response.status_code == 200
    assert list_response.json() == {"items": [created]}

    update_payload = connection_payload(
        name="OpenAI primary",
        provider="openai_compatible",
        base_url="https://gateway.example/v1/",
        default_model=None,
        enabled=False,
    )
    update_payload.pop("api_key")
    update_response = client.put(
        (f"/organizations/{projects.organization.id}/ai-connections/{created['id']}"),
        json=update_payload,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "OpenAI primary"
    assert update_response.json()["provider"] == "openai_compatible"
    assert update_response.json()["base_url"] == "https://gateway.example/v1"
    assert update_response.json()["default_model"] is None
    assert update_response.json()["enabled"] is False

    stored = session.get(AiConnection, created["id"])
    assert stored is not None
    assert decrypt_text(stored.encrypted_api_key) == "secret-key"

    delete_response = client.delete(
        f"/organizations/{projects.organization.id}/ai-connections/{created['id']}"
    )
    assert delete_response.status_code == 204
    assert session.get(AiConnection, created["id"]) is None


def test_create_requires_api_key(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    payload = connection_payload()
    payload.pop("api_key")

    response = client.post(
        f"/organizations/{projects.organization.id}/ai-connections",
        json=payload,
    )

    assert response.status_code == 422


def test_member_can_list_but_cannot_manage_connections(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    set_member_role(session, projects, "member")
    auth_as(projects.member)

    list_response = client.get(
        f"/organizations/{projects.organization.id}/ai-connections"
    )
    create_response = client.post(
        f"/organizations/{projects.organization.id}/ai-connections",
        json=connection_payload(),
    )

    assert list_response.status_code == 200
    assert list_response.json() == {"items": []}
    assert create_response.status_code == 404


@pytest.mark.parametrize("operation", ["update", "delete", "test"])
def test_member_cannot_update_delete_or_test_connection(
    operation: str,
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    connection = create_connection(client, projects)
    set_member_role(session, projects, "member")
    endpoint = (
        f"/organizations/{projects.organization.id}/ai-connections/{connection['id']}"
    )

    if operation == "update":
        response = client.put(endpoint, json=connection_payload())
    elif operation == "delete":
        response = client.delete(endpoint)
    else:
        response = client.post(f"{endpoint}/test", json={})

    assert response.status_code == 404


def test_duplicate_connection_name_returns_conflict(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    create_connection(client, projects)

    response = client.post(
        f"/organizations/{projects.organization.id}/ai-connections",
        json=connection_payload(provider="anthropic"),
    )

    assert response.status_code == 409


def test_update_to_duplicate_connection_name_returns_conflict(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    create_connection(client, projects)
    second = create_connection(client, projects, name="Second connection")

    response = client.put(
        (f"/organizations/{projects.organization.id}/ai-connections/{second['id']}"),
        json=connection_payload(),
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "policy_field",
    ["primary_connection_id", "fallback_connection_id"],
)
def test_connection_in_project_policy_cannot_be_deleted(
    policy_field: str,
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    target = create_connection(client, projects)
    other = create_connection(client, projects, name="Other connection")
    primary_id = (
        target["id"] if policy_field == "primary_connection_id" else other["id"]
    )
    fallback_id = target["id"] if policy_field == "fallback_connection_id" else None
    session.add(
        ProjectAiPolicy(
            project_id=projects.member_project.id,
            organization_id=projects.organization.id,
            primary_connection_id=primary_id,
            primary_model="primary-model",
            fallback_connection_id=fallback_id,
            fallback_model="fallback-model" if fallback_id else None,
        )
    )
    session.commit()

    response = client.delete(
        f"/organizations/{projects.organization.id}/ai-connections/{target['id']}"
    )

    assert response.status_code == 409
    assert session.get(AiConnection, target["id"]) is not None


@pytest.mark.parametrize(
    ("provider", "base_url", "expected_url", "expected_headers", "expected_json"),
    [
        (
            "openai",
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/responses",
            {"Authorization": "Bearer secret-key"},
            {
                "model": "test-model",
                "input": "Reply with OK",
                "max_output_tokens": 8,
            },
        ),
        (
            "anthropic",
            "https://api.anthropic.com/v1",
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": "secret-key",
                "anthropic-version": "2023-06-01",
            },
            {
                "model": "test-model",
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "Reply with OK"}],
            },
        ),
        (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta",
            (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "test-model:generateContent"
            ),
            {"x-goog-api-key": "secret-key"},
            {"contents": [{"parts": [{"text": "Reply with OK"}]}]},
        ),
        (
            "openai_compatible",
            "https://gateway.example/v1",
            "https://gateway.example/v1/chat/completions",
            {"Authorization": "Bearer secret-key"},
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 8,
            },
        ),
    ],
)
def test_connection_uses_provider_specific_test_request(
    provider: str,
    base_url: str,
    expected_url: str,
    expected_headers: dict,
    expected_json: dict,
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    connection = create_connection(
        client,
        projects,
        provider=provider,
        base_url=base_url,
        default_model=None,
    )

    class ProviderResponse:
        status_code = 200

    def provider_post(
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: int,
        allow_redirects: bool,
    ):
        assert url == expected_url
        assert headers == expected_headers
        assert json == expected_json
        assert timeout == 15
        assert allow_redirects is False
        return ProviderResponse()

    monkeypatch.setattr("app.api.routes.ai_settings.requests.post", provider_post)

    response = client.post(
        (
            f"/organizations/{projects.organization.id}/ai-connections/"
            f"{connection['id']}/test"
        ),
        json={"model": "test-model"},
    )

    assert response.status_code == 200
    assert response.json()["last_test_status"] == "connected"
    assert response.json()["last_test_message"] == "Connection successful"
    assert response.json()["last_tested_at"] is not None
    session.refresh(session.get(AiConnection, connection["id"]))


def test_connection_test_requires_body_or_default_model(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    connection = create_connection(client, projects, default_model=None)

    response = client.post(
        (
            f"/organizations/{projects.organization.id}/ai-connections/"
            f"{connection['id']}/test"
        ),
        json={},
    )

    assert response.status_code == 422


def test_connection_test_uses_default_model_when_body_has_no_model(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    connection = create_connection(
        client,
        projects,
        default_model="saved-default-model",
    )

    class ProviderResponse:
        status_code = 204

    def provider_post(
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: int,
        allow_redirects: bool,
    ):
        assert url == "https://api.openai.com/v1/responses"
        assert headers == {"Authorization": "Bearer secret-key"}
        assert json == {
            "model": "saved-default-model",
            "input": "Reply with OK",
            "max_output_tokens": 8,
        }
        assert timeout == 15
        assert allow_redirects is False
        return ProviderResponse()

    monkeypatch.setattr("app.api.routes.ai_settings.requests.post", provider_post)

    response = client.post(
        (
            f"/organizations/{projects.organization.id}/ai-connections/"
            f"{connection['id']}/test"
        ),
        json={},
    )

    assert response.status_code == 200
    assert response.json()["last_test_status"] == "connected"


def test_failed_connection_test_is_safe_and_persisted(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    connection = create_connection(client, projects)

    class ProviderResponse:
        status_code = 401
        text = "provider-secret-body secret-key"

    monkeypatch.setattr(
        "app.api.routes.ai_settings.requests.post",
        lambda *args, **kwargs: ProviderResponse(),
    )

    response = client.post(
        (
            f"/organizations/{projects.organization.id}/ai-connections/"
            f"{connection['id']}/test"
        ),
        json={},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "AI provider connection failed"}
    assert "provider-secret-body" not in response.text
    assert "secret-key" not in response.text
    stored = session.scalar(
        select(AiConnection).where(AiConnection.id == connection["id"])
    )
    assert stored is not None
    assert stored.last_test_status == "failed"
    assert stored.last_test_message == "Connection failed"
    assert stored.last_tested_at is not None
