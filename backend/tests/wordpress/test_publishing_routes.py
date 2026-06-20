from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import wordpress as wordpress_routes
from app.domains.audits.models import SeoRecommendation
from app.domains.wordpress.models import (
    WordPressChangeEvent,
    WordPressChangeProposal,
    WordPressConnection,
    WordPressPage,
)
from tests.projects.conftest import ProjectFixtures


class FakePublishingClient:
    def __init__(self) -> None:
        self.content_hash = "base-hash"
        self.value = "Oude title"

    def current_state(self, object_id: int) -> dict:
        return {
            "content_hash": self.content_hash,
            "values": {"seo_title": self.value, "content": self.value},
        }

    def apply_change(self, object_id: int, payload: dict) -> dict:
        self.value = payload["value"]
        self.content_hash = f"hash-{len(self.value)}"
        return {
            "content_hash": self.content_hash,
            "values": {"seo_title": self.value},
        }


def test_wordpress_connection_status_returns_existing_connection(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    session.add(
        WordPressConnection(
            id="wp-connection",
            project_id=projects.member_project.id,
            site_url="https://member.example",
            encrypted_secret="encrypted",
            plugin_version="0.1.0",
            seo_plugin="yoast",
            health_state="connected",
        )
    )
    session.commit()

    response = client.get(
        f"/projects/{projects.member_project.id}/wordpress-connection"
    )

    assert response.status_code == 200
    assert response.json() == {
        "project_id": projects.member_project.id,
        "site_url": "https://member.example",
        "plugin_version": "0.1.0",
        "seo_plugin": "yoast",
        "health_state": "connected",
    }


def test_approved_publish_and_confirmed_rollback_are_audited(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="wp-publish",
        project_id=projects.member_project.id,
        wordpress_object_id=42,
        post_type="page",
        status="publish",
        title="Revisie",
        slug="revisie",
        url="https://member.example/revisie",
        content_hash="base-hash",
    )
    session.add(page)
    session.commit()
    fake = FakePublishingClient()
    monkeypatch.setattr(
        wordpress_routes,
        "_connection_client",
        lambda session, project_id: fake,
    )

    created = client.post(
        f"/projects/{projects.member_project.id}/change-proposals",
        json={
            "wordpress_page_id": page.id,
            "change_type": "seo_title",
            "before_value": "Oude title",
            "after_value": "Nieuwe title",
        },
    )
    proposal_id = created.json()["id"]

    assert created.status_code == 201
    assert (
        client.post(
            f"/projects/{projects.member_project.id}/change-proposals/"
            f"{proposal_id}/publish"
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/projects/{projects.member_project.id}/change-proposals/"
            f"{proposal_id}/approve"
        ).status_code
        == 200
    )
    published = client.post(
        f"/projects/{projects.member_project.id}/change-proposals/{proposal_id}/publish"
    )
    rolled_back = client.post(
        f"/projects/{projects.member_project.id}/change-proposals/"
        f"{proposal_id}/rollback",
        json={"confirmed": True},
    )

    assert published.status_code == 200
    assert published.json()["proposal"]["approval_state"] == "published"
    assert rolled_back.status_code == 200
    assert rolled_back.json()["proposal"]["approval_state"] == "rolled_back"
    assert session.scalar(select(func.count(WordPressChangeEvent.id))) == 2


def test_proposed_change_can_be_edited_but_approved_change_is_locked(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="wp-edit",
        project_id=projects.member_project.id,
        wordpress_object_id=84,
        post_type="page",
        status="publish",
        title="Revisie",
        slug="revisie",
        url="https://member.example/revisie",
        content_hash="base-hash",
    )
    session.add(page)
    session.commit()
    created = client.post(
        f"/projects/{projects.member_project.id}/change-proposals",
        json={
            "wordpress_page_id": page.id,
            "change_type": "seo_title",
            "before_value": "Oude title",
            "after_value": "Eerste voorstel",
        },
    ).json()

    edited = client.put(
        f"/projects/{projects.member_project.id}/change-proposals/{created['id']}",
        json={"after_value": "Verbeterd voorstel"},
    )
    client.post(
        f"/projects/{projects.member_project.id}/change-proposals/"
        f"{created['id']}/approve"
    )
    locked = client.put(
        f"/projects/{projects.member_project.id}/change-proposals/{created['id']}",
        json={"after_value": "Te laat gewijzigd"},
    )

    assert edited.status_code == 200
    assert edited.json()["after_value"] == "Verbeterd voorstel"
    assert locked.status_code == 409


def test_recommendation_proposal_uses_current_wordpress_value(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="wp-recommendation-proposal",
        project_id=projects.member_project.id,
        wordpress_object_id=99,
        post_type="page",
        status="publish",
        title="Bedankpagina",
        slug="bedankpagina",
        url="https://member.example/bedankpagina",
        content_hash="stale-hash",
    )
    recommendation = SeoRecommendation(
        id="recommendation-technical",
        project_id=projects.member_project.id,
        wordpress_page_id=page.id,
        action_type="technical_seo",
        priority="high",
        recommendation="Verbeter de technische SEO.",
        approval_state="proposed",
        evidence={},
        provider="rules",
    )
    session.add_all([page, recommendation])
    session.commit()
    fake = FakePublishingClient()
    fake.content_hash = "live-hash"
    fake.value = "Live WordPress tekst"
    monkeypatch.setattr(
        wordpress_routes,
        "_connection_client",
        lambda session, project_id: fake,
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/recommendations/"
        f"{recommendation.id}/change-proposal"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["change_type"] == "content"
    assert body["before_value"] == "Live WordPress tekst"
    assert body["after_value"] == "Verbeter de technische SEO."
    assert body["base_content_hash"] == "live-hash"


def test_conflict_proposal_can_be_refreshed_from_wordpress(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="wp-refresh",
        project_id=projects.member_project.id,
        wordpress_object_id=123,
        post_type="page",
        status="publish",
        title="Refresh",
        slug="refresh",
        url="https://member.example/refresh",
        content_hash="old-hash",
    )
    proposal = WordPressChangeProposal(
        id="proposal-refresh",
        project_id=projects.member_project.id,
        wordpress_page_id=page.id,
        change_type="seo_title",
        before_value="Oude title",
        after_value="Nieuwe title",
        base_content_hash="old-hash",
        proposed_by=projects.member.id,
        approved_by=projects.member.id,
        approval_state="conflict",
    )
    session.add_all([page, proposal])
    session.commit()
    fake = FakePublishingClient()
    fake.content_hash = "new-live-hash"
    fake.value = "Nieuwe live title"
    monkeypatch.setattr(
        wordpress_routes,
        "_connection_client",
        lambda session, project_id: fake,
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/change-proposals/"
        f"{proposal.id}/refresh"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_state"] == "proposed"
    assert body["before_value"] == "Nieuwe live title"
    assert body["base_content_hash"] == "new-live-hash"
