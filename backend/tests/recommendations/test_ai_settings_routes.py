from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from tests.projects.conftest import ProjectFixtures


def test_owner_configures_ai_model_without_returning_api_key(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        get_settings(),
        "encryption_key",
        "MDAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA=",
    )
    auth_as(projects.member)

    response = client.put(
        f"/organizations/{projects.organization.id}/ai-settings",
        json={
            "provider": "openai_compatible",
            "base_url": "https://api.example.ai/v1",
            "model": "company-seo-model",
            "api_key": "secret-key",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai_compatible",
        "base_url": "https://api.example.ai/v1",
        "model": "company-seo-model",
        "configured": True,
    }
    assert "secret-key" not in response.text


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


def test_owner_can_test_saved_ai_provider_connection(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        get_settings(),
        "encryption_key",
        "MDAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA=",
    )
    auth_as(projects.member)
    client.put(
        f"/organizations/{projects.organization.id}/ai-settings",
        json={
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.4-mini",
            "api_key": "secret-key",
        },
    )

    class ProviderResponse:
        def raise_for_status(self) -> None:
            return None

    def provider_get(url: str, *, headers: dict, timeout: int):
        assert url == "https://api.openai.com/v1/models"
        assert headers["Authorization"] == "Bearer secret-key"
        assert timeout == 15
        return ProviderResponse()

    monkeypatch.setattr("app.api.routes.ai_settings.requests.get", provider_get)

    response = client.post(
        f"/organizations/{projects.organization.id}/ai-settings/test",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "connected",
        "model": "gpt-5.4-mini",
    }


def test_owner_updates_model_without_replacing_saved_api_key(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        get_settings(),
        "encryption_key",
        "MDAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA=",
    )
    auth_as(projects.member)
    endpoint = f"/organizations/{projects.organization.id}/ai-settings"
    client.put(
        endpoint,
        json={
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.4-mini",
            "api_key": "secret-key",
        },
    )

    response = client.put(
        endpoint,
        json={
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.4",
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "gpt-5.4"
