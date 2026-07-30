from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.domains.wordpress.draft_jobs import hash_project_key
from app.domains.wordpress.models import (
    WordPressOutboundCredential,
    WordPressSnapshotCaptureJob,
)
from app.domains.wordpress.snapshot_jobs import create_or_get_snapshot_job
from tests.recommendations.conftest import ProjectFixtures
from tests.wordpress.test_page_monitoring_models import (
    wordpress_page as _wordpress_page,
)
from tests.wordpress.test_snapshot_job_service import snapshot_result


@pytest.fixture
def wordpress_page(session, projects):
    page = _wordpress_page.__wrapped__(session, projects)
    page.content_hash = "source-content-hash"
    session.add(
        WordPressOutboundCredential(
            id="snapshot-route-credential",
            project_id=page.project_id,
            key_hash=hash_project_key("wpfx_snapshot_test"),
            site_url="https://member.example",
        )
    )
    session.commit()
    return page


def plugin_headers(**overrides) -> dict[str, str]:
    return {
        "Authorization": "Bearer wpfx_snapshot_test",
        "X-WP-FixPilot-Site": "https://member.example",
    } | overrides


def test_plugin_claims_and_completes_snapshot_job(
    client: TestClient,
    session,
    projects: ProjectFixtures,
    wordpress_page,
) -> None:
    job = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-snapshot-jobs"
    )

    claimed = client.post(f"{endpoint}/claim", headers=plugin_headers())

    assert claimed.status_code == 200
    assert claimed.json()["job"] == {
        "id": job.id,
        "project_id": wordpress_page.project_id,
        "wordpress_page_id": wordpress_page.id,
        "source_post_id": 701,
        "source_url": "https://member.example/monitoring-page",
        "source_content_hash": "source-content-hash",
    }
    result = client.post(
        f"{endpoint}/{job.id}/complete",
        headers=plugin_headers(),
        json={
            "claim_token": claimed.json()["claim_token"],
            "result": snapshot_result(),
        },
    )

    assert result.status_code == 200
    assert result.json()["state"] == "completed"
    session.expire_all()
    stored = session.get(WordPressSnapshotCaptureJob, job.id)
    assert stored is not None
    assert stored.snapshot_result == snapshot_result()


def test_snapshot_routes_reuse_project_key_and_site_binding(
    client: TestClient,
    session,
    projects: ProjectFixtures,
    wordpress_page,
) -> None:
    create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-snapshot-jobs/claim"
    )

    missing = client.post(endpoint)
    wrong_key = client.post(
        endpoint,
        headers=plugin_headers(Authorization="Bearer wrong"),
    )
    wrong_site = client.post(
        endpoint,
        headers=plugin_headers(**{"X-WP-FixPilot-Site": "https://other.example"}),
    )

    assert missing.status_code == 401
    assert wrong_key.status_code == 401
    assert wrong_site.status_code == 403


def test_snapshot_claim_returns_204_when_queue_is_empty(
    client: TestClient,
    projects: ProjectFixtures,
    wordpress_page,
) -> None:
    response = client.post(
        f"/projects/{projects.member_project.id}/wordpress-snapshot-jobs/claim",
        headers=plugin_headers(),
    )

    assert response.status_code == 204


def test_snapshot_failure_is_safe_and_idempotent(
    client: TestClient,
    session,
    projects: ProjectFixtures,
    wordpress_page,
) -> None:
    job = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-snapshot-jobs"
    )
    claimed = client.post(f"{endpoint}/claim", headers=plugin_headers()).json()
    payload = {
        "claim_token": claimed["claim_token"],
        "error_code": "wordpress_error",
        "error_message": "Sensitive details are not echoed",
    }

    failed = client.post(
        f"{endpoint}/{job.id}/fail",
        headers=plugin_headers(),
        json=payload,
    )
    replay = client.post(
        f"{endpoint}/{job.id}/fail",
        headers=plugin_headers(),
        json=payload,
    )

    assert failed.status_code == 200
    assert replay.status_code == 200
    assert failed.json()["state"] == "failed"
    assert "error_message" not in failed.json()


def test_completion_rejects_result_for_another_source(
    client: TestClient,
    session,
    projects: ProjectFixtures,
    wordpress_page,
) -> None:
    job = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-snapshot-jobs"
    )
    claimed = client.post(f"{endpoint}/claim", headers=plugin_headers()).json()

    response = client.post(
        f"{endpoint}/{job.id}/complete",
        headers=plugin_headers(),
        json={
            "claim_token": claimed["claim_token"],
            "result": snapshot_result(source_post_id=999),
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "snapshot_conflict"


def test_completion_rejects_claim_time_source_identity_drift(
    client: TestClient,
    session,
    projects: ProjectFixtures,
    wordpress_page,
) -> None:
    job = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-snapshot-jobs"
    )
    claimed = client.post(f"{endpoint}/claim", headers=plugin_headers()).json()
    wordpress_page.url = "https://member.example/renamed"
    wordpress_page.content_hash = "builder-metadata-changed"
    session.commit()

    response = client.post(
        f"{endpoint}/{job.id}/complete",
        headers=plugin_headers(),
        json={
            "claim_token": claimed["claim_token"],
            "result": snapshot_result(),
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "snapshot_conflict"


def test_expired_completion_returns_retryable_conflict_and_reclaims(
    client: TestClient,
    session,
    projects: ProjectFixtures,
    wordpress_page,
) -> None:
    job = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-snapshot-jobs"
    )
    first_claim = client.post(
        f"{endpoint}/claim",
        headers=plugin_headers(),
    ).json()
    stored = session.get(WordPressSnapshotCaptureJob, job.id)
    assert stored is not None
    stored.claim_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()

    expired = client.post(
        f"{endpoint}/{job.id}/complete",
        headers=plugin_headers(),
        json={
            "claim_token": first_claim["claim_token"],
            "result": snapshot_result(),
        },
    )

    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "snapshot_claim_invalid"

    second_claim = client.post(
        f"{endpoint}/claim",
        headers=plugin_headers(),
    )
    assert second_claim.status_code == 200
    assert second_claim.json()["job"]["id"] == job.id
    assert second_claim.json()["claim_token"] != first_claim["claim_token"]

    completed = client.post(
        f"{endpoint}/{job.id}/complete",
        headers=plugin_headers(),
        json={
            "claim_token": second_claim.json()["claim_token"],
            "result": snapshot_result(),
        },
    )
    assert completed.status_code == 200
    assert completed.json()["state"] == "completed"


def test_completion_rejects_coerced_result_fields(
    client: TestClient,
    session,
    projects: ProjectFixtures,
    wordpress_page,
) -> None:
    job = create_or_get_snapshot_job(session, wordpress_page)
    session.commit()
    endpoint = (
        f"/projects/{projects.member_project.id}/wordpress-snapshot-jobs"
    )
    claimed = client.post(f"{endpoint}/claim", headers=plugin_headers()).json()
    malformed = snapshot_result(snapshot_id="901")

    response = client.post(
        f"{endpoint}/{job.id}/complete",
        headers=plugin_headers(),
        json={"claim_token": claimed["claim_token"], "result": malformed},
    )

    assert response.status_code == 422
