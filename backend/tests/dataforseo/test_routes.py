from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text
from app.domains.dataforseo.models import DataForSeoConnection, KeywordOpportunity
from tests.recommendations.conftest import ProjectFixtures

ENCRYPTION_KEY = "MDAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="


def test_owner_saves_reads_and_tests_dataforseo_connection(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(get_settings(), "encryption_key", ENCRYPTION_KEY)
    auth_as(projects.member)

    response = client.put(
        f"/organizations/{projects.organization.id}/dataforseo-connection",
        json={"login": "data-login", "password": "data-password", "enabled": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "login": "data-login",
        "enabled": True,
        "last_tested_at": None,
        "last_test_status": None,
        "last_test_message": None,
    }
    assert "data-password" not in response.text
    stored = session.get(DataForSeoConnection, projects.organization.id)
    assert stored is not None
    assert decrypt_text(stored.encrypted_password) == "data-password"

    get_response = client.get(
        f"/organizations/{projects.organization.id}/dataforseo-connection"
    )
    assert get_response.status_code == 200
    assert get_response.json()["configured"] is True

    class Provider:
        def __init__(self, login: str, password: str) -> None:
            assert login == "data-login"
            assert password == "data-password"

        def test_connection(self) -> None:
            return None

    monkeypatch.setattr("app.api.routes.dataforseo.DataForSeoProvider", Provider)

    test_response = client.post(
        f"/organizations/{projects.organization.id}/dataforseo-connection/test"
    )

    assert test_response.status_code == 200
    assert test_response.json()["last_test_status"] == "connected"
    assert test_response.json()["last_test_message"] == "Connection successful"


def test_failed_dataforseo_connection_test_is_safe(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(get_settings(), "encryption_key", ENCRYPTION_KEY)
    auth_as(projects.member)
    client.put(
        f"/organizations/{projects.organization.id}/dataforseo-connection",
        json={"login": "data-login", "password": "secret-password", "enabled": True},
    )

    class Provider:
        def __init__(self, login: str, password: str) -> None:
            pass

        def test_connection(self) -> None:
            raise RuntimeError("Invalid password secret-password")

    monkeypatch.setattr("app.api.routes.dataforseo.DataForSeoProvider", Provider)

    response = client.post(
        f"/organizations/{projects.organization.id}/dataforseo-connection/test"
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "DataForSEO connection failed: Invalid password [redacted]"
    }
    assert "secret-password" not in response.text


def test_project_syncs_keyword_opportunities_idempotently(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(get_settings(), "encryption_key", ENCRYPTION_KEY)
    auth_as(projects.member)
    client.put(
        f"/organizations/{projects.organization.id}/dataforseo-connection",
        json={"login": "data-login", "password": "data-password", "enabled": True},
    )

    class Provider:
        def __init__(self, login: str, password: str) -> None:
            pass

        def keyword_ideas(self, seeds: list[str]) -> list[dict]:
            assert "member.example" in seeds
            return [
                {
                    "keyword": "automatische transmissie revisie",
                    "location_code": 2528,
                    "language_code": "nl",
                    "search_volume": 320,
                    "cpc": 4.25,
                    "competition": 0.42,
                    "competition_level": "medium",
                    "keyword_difficulty": 38,
                    "intent": "commercial",
                }
            ]

    monkeypatch.setattr("app.api.routes.dataforseo.DataForSeoProvider", Provider)

    first = client.post(
        f"/projects/{projects.member_project.id}/sync-keyword-opportunities"
    )
    second = client.post(
        f"/projects/{projects.member_project.id}/sync-keyword-opportunities"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["synced"] == 1
    opportunities = session.scalars(select(KeywordOpportunity)).all()
    assert len(opportunities) == 1
    assert opportunities[0].keyword == "automatische transmissie revisie"
    assert opportunities[0].cpc == Decimal("4.2500")

    list_response = client.get(
        f"/projects/{projects.member_project.id}/keyword-opportunities"
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["keyword"] == (
        "automatische transmissie revisie"
    )
    assert list_response.json()["items"][0]["recommended_action"]


def test_outsider_cannot_read_project_keyword_opportunities(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.outsider)

    response = client.get(
        f"/projects/{projects.member_project.id}/keyword-opportunities"
    )

    assert response.status_code == 404
