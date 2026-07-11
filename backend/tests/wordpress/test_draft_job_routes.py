import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.wordpress.models import WordPressDraftJob
from tests.recommendations.conftest import ProjectFixtures
from tests.wordpress.test_draft_job_service import (
    approved_blueprint_proposal as _approved_blueprint_proposal,
)


@pytest.fixture
def approved_blueprint_proposal(session, projects):
    return _approved_blueprint_proposal.__wrapped__(session, projects)


def test_owner_creates_key_once_and_read_never_repeats_it(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-outbound-credential"
    )

    created = client.post(endpoint, json={"site_url": "https://member.example:443/"})
    read = client.get(endpoint)
    repeated = client.post(endpoint, json={"site_url": "https://member.example"})

    assert created.status_code == 201
    assert created.json()["key"].startswith("wpfx_")
    assert created.json()["site_url"] == "https://member.example"
    assert read.status_code == 200
    assert "key" not in read.json()
    assert repeated.status_code == 409


def test_outsider_cannot_create_or_read_project_key(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.outsider)
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-outbound-credential"
    )

    create = client.post(endpoint, json={"site_url": "https://member.example"})
    assert create.status_code == 404
    assert client.get(endpoint).status_code == 404


def test_rotation_invalidates_the_old_key(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-outbound-credential"
    )
    original = client.post(endpoint, json={"site_url": "https://member.example"}).json()
    rotated = client.post(f"{endpoint}/rotate").json()
    verify_endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-draft-jobs/verify"
    )

    old = client.post(
        verify_endpoint,
        headers={
            "Authorization": f"Bearer {original['key']}",
            "X-WP-FixPilot-Site": "https://member.example",
        },
    )
    new = client.post(
        verify_endpoint,
        headers={
            "Authorization": f"Bearer {rotated['key']}",
            "X-WP-FixPilot-Site": "https://member.example",
        },
    )

    assert old.status_code == 401
    assert new.status_code == 200
    assert new.json()["connected"] is True


def test_dashboard_creates_job_and_plugin_claims_completes_it(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    approved_blueprint_proposal,
) -> None:
    auth_as(projects.member)
    create_endpoint = (
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{approved_blueprint_proposal.id}/draft-job"
    )
    created = client.post(create_endpoint)
    repeated = client.post(create_endpoint)

    assert created.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["id"] == created.json()["id"]
    assert created.json()["state"] == "queued"
    proposal_read = client.get(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{approved_blueprint_proposal.id}"
    )
    assert proposal_read.json()["draft_job"]["id"] == created.json()["id"]

    direct_while_queued = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{approved_blueprint_proposal.id}/create-draft"
    )
    handoff_while_queued = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{approved_blueprint_proposal.id}/handoffs"
    )
    assert direct_while_queued.status_code == 409
    assert handoff_while_queued.status_code == 409

    plugin_headers = {
        "Authorization": "Bearer wpfx_test",
        "X-WP-FixPilot-Site": "https://member.example:443",
    }
    claim_endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-draft-jobs/claim"
    )
    claimed = client.post(claim_endpoint, headers=plugin_headers)

    assert claimed.status_code == 200
    assert claimed.json()["job"]["contract_version"] == "wordpress-draft-job-v1"
    assert claimed.json()["job"]["payload"]["wordpress_blueprint_id"] == 902
    assert claimed.json()["claim_token"]
    session.expire_all()
    assert approved_blueprint_proposal.state == "draft_in_progress"

    complete_endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-draft-jobs/"
        f"{created.json()['id']}/complete"
    )
    invalid_edit_url = client.post(
        complete_endpoint,
        headers=plugin_headers,
        json={
            "claim_token": claimed.json()["claim_token"],
            "wordpress_object_id": 987,
            "wordpress_edit_url": (
                "https://outside.example/wp-admin/post.php?post=987&action=edit"
            ),
        },
    )
    result = client.post(
        complete_endpoint,
        headers=plugin_headers,
        json={
            "claim_token": claimed.json()["claim_token"],
            "wordpress_object_id": 987,
            "wordpress_edit_url": (
                "https://member.example/wp-admin/post.php?post=987&action=edit"
            ),
        },
    )
    replay = client.post(
        complete_endpoint,
        headers=plugin_headers,
        json={
            "claim_token": claimed.json()["claim_token"],
            "wordpress_object_id": 987,
            "wordpress_edit_url": (
                "https://member.example/wp-admin/post.php?post=987&action=edit"
            ),
        },
    )

    assert invalid_edit_url.status_code == 422
    assert result.status_code == 200
    assert replay.status_code == 200
    wrong_token_replay = client.post(
        complete_endpoint,
        headers=plugin_headers,
        json={
            "claim_token": "different-claim-token-with-valid-length",
            "wordpress_object_id": 987,
            "wordpress_edit_url": (
                "https://member.example/wp-admin/post.php?post=987&action=edit"
            ),
        },
    )
    assert wrong_token_replay.status_code == 409
    assert result.json()["state"] == "completed"
    direct_fallback = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{approved_blueprint_proposal.id}/create-draft"
    )
    handoff_fallback = client.post(
        f"/projects/{projects.member_project.id}/page-proposals/"
        f"{approved_blueprint_proposal.id}/handoffs"
    )
    assert direct_fallback.status_code == 200
    assert direct_fallback.json()["wordpress_object_id"] == 987
    assert handoff_fallback.status_code == 409
    session.expire_all()
    stored = session.get(WordPressDraftJob, created.json()["id"])
    assert stored is not None
    assert stored.wordpress_object_id == 987


def test_plugin_auth_is_project_and_site_scoped(
    client: TestClient,
    projects: ProjectFixtures,
    approved_blueprint_proposal,
) -> None:
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-draft-jobs/claim"
    )
    wrong_key = client.post(
        endpoint,
        headers={
            "Authorization": "Bearer wrong",
            "X-WP-FixPilot-Site": "https://member.example",
        },
    )
    wrong_site = client.post(
        endpoint,
        headers={
            "Authorization": "Bearer wpfx_test",
            "X-WP-FixPilot-Site": "https://other.example",
        },
    )

    assert wrong_key.status_code == 401
    assert wrong_site.status_code == 403


def test_plugin_route_without_credentials_returns_401(
    client: TestClient,
    projects: ProjectFixtures,
) -> None:
    response = client.post(
        f"/projects/{projects.member_project.id}/wordpress-draft-jobs/verify"
    )

    assert response.status_code == 401


def test_claim_returns_204_when_no_job_is_available(
    client: TestClient,
    projects: ProjectFixtures,
    approved_blueprint_proposal,
) -> None:
    response = client.post(
        f"/projects/{projects.member_project.id}/wordpress-draft-jobs/claim",
        headers={
            "Authorization": "Bearer wpfx_test",
            "X-WP-FixPilot-Site": "https://member.example",
        },
    )

    assert response.status_code == 204
