from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.wordpress.draft_jobs import hash_project_key
from app.domains.wordpress.models import (
    WordPressOutboundCredential,
    WordPressPage,
    WordPressSnapshotCaptureJob,
)
from app.domains.wordpress.snapshot_jobs import claim_next_snapshot_job
from tests.recommendations.conftest import ProjectFixtures


def _existing_opportunity(
    session: Session,
    projects: ProjectFixtures,
) -> KeywordOpportunity:
    page = WordPressPage(
        id="existing-route-page",
        project_id=projects.member_project.id,
        wordpress_object_id=701,
        post_type="page",
        status="publish",
        title="Current service page",
        slug="current-service",
        url="https://member.example/current-service/",
        content_hash="existing-route-hash",
    )
    opportunity = KeywordOpportunity(
        id="existing-route-opportunity",
        project_id=projects.member_project.id,
        keyword="improve current service",
        location_code=2528,
        language_code="nl",
        target_url=page.url,
        target_classification="existing_page",
        target_score=88,
        target_evidence=["strong_title_match"],
        source="dataforseo",
        raw_payload={},
    )
    session.add_all([page, opportunity])
    session.commit()
    return opportunity


def test_existing_page_opportunity_queues_one_snapshot_capture(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    opportunity = _existing_opportunity(session, projects)
    route = (
        f"/projects/{opportunity.project_id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal"
    )

    first = client.post(route, json={"page_type": "service"})
    second = client.post(route, json={"page_type": "service"})

    assert first.status_code == 202
    assert first.json()["stage"] == "waiting_for_wordpress_snapshot"
    assert first.json()["snapshot_job_id"] == second.json()["snapshot_job_id"]


def test_review_opportunity_still_requires_target_assignment(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    opportunity = _existing_opportunity(session, projects)
    opportunity.target_classification = "review"
    session.commit()

    response = client.post(
        f"/projects/{opportunity.project_id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal",
        json={"page_type": "service"},
    )

    assert response.status_code == 409


def test_existing_page_source_drift_replaces_the_frozen_capture_job(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    opportunity = _existing_opportunity(session, projects)
    session.add(
        WordPressOutboundCredential(
            id="existing-route-credential",
            project_id=opportunity.project_id,
            key_hash=hash_project_key("wpfx_existing_route"),
            site_url="https://member.example",
        )
    )
    session.commit()
    route = (
        f"/projects/{opportunity.project_id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal"
    )
    first = client.post(route, json={"page_type": "service"})
    claimed = claim_next_snapshot_job(
        session,
        opportunity.project_id,
        "https://member.example",
    )
    assert claimed is not None
    source = session.get(WordPressPage, "existing-route-page")
    assert source is not None
    source.content_hash = "existing-route-drifted-hash"
    session.commit()

    retried = client.post(route, json={"page_type": "service"})
    stale = session.get(WordPressSnapshotCaptureJob, first.json()["snapshot_job_id"])
    fresh = session.get(WordPressSnapshotCaptureJob, retried.json()["snapshot_job_id"])

    assert retried.status_code == 202
    assert retried.json()["snapshot_job_id"] != first.json()["snapshot_job_id"]
    assert stale is not None
    assert stale.state == "failed"
    assert fresh is not None
    assert fresh.state == "queued"


def test_existing_page_waits_for_a_synced_hash_before_replacing_drifted_job(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    opportunity = _existing_opportunity(session, projects)
    session.add(
        WordPressOutboundCredential(
            id="existing-null-hash-credential",
            project_id=opportunity.project_id,
            key_hash=hash_project_key("wpfx_existing_null_hash"),
            site_url="https://member.example",
        )
    )
    session.commit()
    route = (
        f"/projects/{opportunity.project_id}/keyword-opportunities/"
        f"{opportunity.id}/page-proposal"
    )
    first = client.post(route, json={"page_type": "service"})
    claimed = claim_next_snapshot_job(
        session,
        opportunity.project_id,
        "https://member.example",
    )
    assert claimed is not None
    source = session.get(WordPressPage, "existing-route-page")
    assert source is not None
    source.content_hash = None
    session.commit()

    waiting_for_sync = client.post(route, json={"page_type": "service"})

    assert waiting_for_sync.status_code == 409
    assert waiting_for_sync.json()["detail"] == (
        "snapshot job source content hash missing"
    )
    stale = session.get(
        WordPressSnapshotCaptureJob,
        first.json()["snapshot_job_id"],
    )
    assert stale is not None
    assert stale.state == "failed"
    assert (
        session.query(WordPressSnapshotCaptureJob)
        .filter(
            WordPressSnapshotCaptureJob.wordpress_page_id == source.id,
            WordPressSnapshotCaptureJob.state.in_(("queued", "claimed")),
        )
        .count()
        == 0
    )

    source.content_hash = "existing-route-resynced-hash"
    session.commit()
    recovered = client.post(route, json={"page_type": "service"})
    fresh = session.get(
        WordPressSnapshotCaptureJob,
        recovered.json()["snapshot_job_id"],
    )

    assert recovered.status_code == 202
    assert recovered.json()["snapshot_job_id"] != first.json()["snapshot_job_id"]
    assert fresh is not None
    assert fresh.state == "queued"
    claimed_fresh = claim_next_snapshot_job(
        session,
        opportunity.project_id,
        "https://member.example",
    )
    assert claimed_fresh is not None
    assert claimed_fresh.job.id == fresh.id
