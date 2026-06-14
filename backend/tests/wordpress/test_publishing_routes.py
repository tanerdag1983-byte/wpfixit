from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import wordpress as wordpress_routes
from app.domains.wordpress.models import WordPressChangeEvent, WordPressPage
from tests.projects.conftest import ProjectFixtures


class FakePublishingClient:
    def __init__(self) -> None:
        self.content_hash = "base-hash"
        self.value = "Oude title"

    def current_state(self, object_id: int) -> dict:
        return {
            "content_hash": self.content_hash,
            "values": {"seo_title": self.value},
        }

    def apply_change(self, object_id: int, payload: dict) -> dict:
        self.value = payload["value"]
        self.content_hash = f"hash-{len(self.value)}"
        return {
            "content_hash": self.content_hash,
            "values": {"seo_title": self.value},
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
