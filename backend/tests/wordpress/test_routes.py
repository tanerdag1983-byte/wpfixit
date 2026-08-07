from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes import wordpress as wordpress_routes
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_packages.models import (
    PagePackageProposal,
    PagePackageRegenerationCandidate,
)
from app.domains.wordpress.client import WordPressHealth
from app.domains.wordpress.draft_jobs import hash_draft_job_payload
from app.domains.wordpress.models import (
    PageObservedVersion,
    PageRecommendation,
    PageScoreSnapshot,
    PageTimelineEvent,
    WordPressConnection,
    WordPressDraftJob,
    WordPressPage,
)


def _existing_page_proposal(session, projects, page, proposal_id: str, **overrides):
    opportunity = KeywordOpportunity(
        id=f"opportunity-{proposal_id}",
        project_id=projects.member_project.id,
        keyword=f"keyword {proposal_id}",
        location_code=2528,
        language_code="nl",
        search_volume=100,
        target_url=page.url,
        target_classification="existing_page",
        target_score=90,
        target_evidence=["strong_existing_page_match"],
        source="dataforseo",
        raw_payload={},
    )
    job = Job(
        id=f"job-{proposal_id}",
        project_id=projects.member_project.id,
        job_type="page_package_generation",
        state="completed",
        progress=100,
        checkpoint={},
    )
    values = {
        "id": proposal_id,
        "project_id": projects.member_project.id,
        "opportunity_id": opportunity.id,
        "job_id": job.id,
        "state": "proposed",
        "proposal_group_id": proposal_id,
        "current_version_id": proposal_id,
        "source_wordpress_page_id": page.id,
        "package": {"text_replacements": {}},
        "rendered_html": "",
        "config_snapshot": {
            "content_schema": {
                "document_fields": [{
                    "id": "seo:meta_description",
                    "path": "seo.meta_description",
                }],
                "blocks": [],
            }
        },
        "proposed_by": projects.member.id,
    }
    values.update(overrides)
    proposal = PagePackageProposal(**values)
    session.add_all([opportunity, job, proposal])
    session.commit()
    return proposal


def test_sync_pages_records_current_state_monitoring(
    client: TestClient, session, auth_as, projects, monkeypatch
) -> None:
    auth_as(projects.member)
    session.add(
        WordPressConnection(
            id="monitoring-sync-connection",
            project_id=projects.member_project.id,
            site_url="https://member.example",
            encrypted_secret="encrypted",
            health_state="connected",
        )
    )
    session.commit()

    class FakeSyncClient:
        def __init__(self, site_url: str, secret: str) -> None:
            assert site_url == "https://member.example"
            assert secret == "secret"

        def health(self) -> WordPressHealth:
            return WordPressHealth(
                site_url="https://member.example",
                wordpress_version="6.8",
                plugin_version="0.2.1",
                seo_plugin="yoast",
            )

        def inventory(self) -> list[dict]:
            return [
                {
                    "id": 701,
                    "type": "page",
                    "status": "publish",
                    "title": "Transmissie revisie",
                    "slug": "transmissie-revisie",
                    "url": "https://member.example/transmissie-revisie",
                    "modified": "2026-07-30T10:00:00+00:00",
                    "content_hash": "sync-hash",
                }
            ]

        def current_state(self, object_id: int) -> dict:
            assert object_id == 701
            return {
                "content_hash": "sync-hash",
                "values": {
                    "seo_title": "Transmissie revisie",
                    "meta_description": "Deskundige transmissie revisie.",
                    "focus_keyword": "transmissie revisie",
                    "canonical": "https://member.example/transmissie-revisie",
                    "noindex": False,
                    "content": "<h1>Transmissie revisie</h1><p>Heldere uitleg.</p>",
                },
            }

    monkeypatch.setattr(wordpress_routes, "decrypt_text", lambda _: "secret")
    monkeypatch.setattr(wordpress_routes, "WordPressClient", FakeSyncClient)

    response = client.post(f"/projects/{projects.member_project.id}/sync-pages")

    assert response.status_code == 200
    assert session.scalar(select(func.count(PageObservedVersion.id))) == 1
    assert session.scalar(select(func.count(PageScoreSnapshot.id))) == 1


def test_sync_links_published_managed_draft_to_proposal_and_source_timeline(
    client: TestClient, session, auth_as, projects, monkeypatch
) -> None:
    auth_as(projects.member)
    source = WordPressPage(
        id="published-source-page",
        project_id=projects.member_project.id,
        wordpress_object_id=710,
        post_type="page",
        status="publish",
        title="Original source",
        slug="original-source",
        url="https://member.example/original-source",
    )
    connection = WordPressConnection(
        id="published-sync-connection",
        project_id=projects.member_project.id,
        site_url="https://member.example",
        encrypted_secret="encrypted",
        health_state="connected",
    )
    session.add_all([source, connection])
    session.commit()
    proposal = _existing_page_proposal(
        session,
        projects,
        source,
        "published-proposal",
        state="draft_created",
        wordpress_object_id=711,
    )
    job_payload = {}
    draft_job = WordPressDraftJob(
        id="published-draft-job",
        project_id=source.project_id,
        proposal_version_id=proposal.id,
        contract_version="wordpress-draft-job-v1",
        state="completed",
        payload=job_payload,
        payload_hash=hash_draft_job_payload(job_payload),
        terminal_claim_token_hash="b" * 64,
        wordpress_object_id=711,
        completed_at=datetime(2026, 8, 4, 9, tzinfo=UTC),
    )
    session.add(draft_job)
    session.commit()

    class PublishedClient:
        def __init__(self, _site_url: str, _secret: str) -> None:
            pass

        def health(self) -> WordPressHealth:
            return WordPressHealth(
                site_url="https://member.example",
                wordpress_version="6.8",
                plugin_version="0.2.1",
                seo_plugin="yoast",
            )

        def inventory(self) -> list[dict]:
            return [{
                "id": 711,
                "type": "page",
                "status": "publish",
                "title": "Improved page",
                "slug": "improved-page",
                "url": "https://member.example/improved-page",
                "modified": "2026-08-05T10:00:00+00:00",
                "content_hash": "published-content-hash",
            }]

        def current_state(self, _object_id: int) -> dict:
            return {
                "content_hash": "published-content-hash",
                "values": {"title": "Improved page", "content": "<h1>Improved</h1>"},
            }

    monkeypatch.setattr(wordpress_routes, "decrypt_text", lambda _: "secret")
    monkeypatch.setattr(wordpress_routes, "WordPressClient", PublishedClient)

    response = client.post(f"/projects/{source.project_id}/sync-pages")

    assert response.status_code == 200
    published_page = session.scalar(
        select(WordPressPage).where(WordPressPage.wordpress_object_id == 711)
    )
    assert published_page is not None
    version = session.scalar(
        select(PageObservedVersion).where(
            PageObservedVersion.wordpress_page_id == published_page.id
        )
    )
    assert version is not None
    assert version.proposal_version_id == proposal.id
    assert version.draft_job_id == draft_job.id
    assert version.published_at is not None
    publication = session.scalar(
        select(PageTimelineEvent).where(
            PageTimelineEvent.wordpress_page_id == source.id,
            PageTimelineEvent.event_type == "published",
        )
    )
    assert publication is not None
    assert publication.page_version_id == version.id


def test_manual_check_reuses_unchanged_page_version(
    client: TestClient, session, auth_as, projects, monkeypatch
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="manual-check-page",
        project_id=projects.member_project.id,
        wordpress_object_id=702,
        post_type="page",
        status="publish",
        title="DSG revisie",
        slug="dsg-revisie",
        url="https://member.example/dsg-revisie",
        content_hash="manual-hash",
    )
    session.add(page)
    session.commit()

    class FakeClient:
        def current_state(self, object_id: int) -> dict:
            assert object_id == 702
            return {
                "content_hash": "manual-hash",
                "values": {
                    "title": "DSG revisie",
                    "meta_description": "",
                    "content": "<h1>DSG revisie</h1>",
                },
            }

    monkeypatch.setattr(
        wordpress_routes,
        "_connection_client",
        lambda _session, project_id: FakeClient(),
    )

    first = client.post(
        f"/projects/{projects.member_project.id}/wordpress-pages/{page.id}/checks"
    )
    recommendation_count = session.scalar(select(func.count(PageRecommendation.id)))
    second = client.post(
        f"/projects/{projects.member_project.id}/wordpress-pages/{page.id}/checks"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["version_id"] == second.json()["version_id"]
    assert first.json()["version_created"] is True
    assert second.json()["version_created"] is False
    assert session.scalar(select(func.count(PageObservedVersion.id))) == 1
    assert second.json()["recommendations_created"] == 0
    assert (
        session.scalar(select(func.count(PageRecommendation.id)))
        == recommendation_count
    )
    checked_events = list(
        session.scalars(
            select(PageTimelineEvent).where(
                PageTimelineEvent.wordpress_page_id == page.id,
                PageTimelineEvent.event_type == "page_checked",
            )
        )
    )
    assert len(checked_events) == 2


def test_page_monitoring_returns_ordered_history_and_schedule(
    client: TestClient, session, auth_as, projects, monkeypatch
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="monitoring-history-page",
        project_id=projects.member_project.id,
        wordpress_object_id=703,
        post_type="page",
        status="publish",
        title="Transmissie revisie",
        slug="transmissie-revisie",
        url="https://member.example/transmissie-revisie",
        content_hash="history-hash",
    )
    session.add(page)
    session.commit()

    class FakeClient:
        def current_state(self, _object_id: int) -> dict:
            return {
                "content_hash": "history-hash",
                "values": {
                    "title": "Transmissie revisie",
                    "meta_description": "",
                    "content": "<h1>Transmissie revisie</h1>",
                },
            }

    monkeypatch.setattr(
        wordpress_routes,
        "_connection_client",
        lambda _session, _project_id: FakeClient(),
    )
    checked = client.post(
        f"/projects/{projects.member_project.id}/wordpress-pages/{page.id}/checks"
    )
    assert checked.status_code == 200

    response = client.get(
        f"/projects/{projects.member_project.id}/wordpress-pages/{page.id}/monitoring"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"]["status"] == "needs_attention"
    assert payload["latest_sync_at"] is not None
    assert payload["next_check_at"] > payload["latest_sync_at"]
    assert [version["id"] for version in payload["versions"]] == [
        checked.json()["version_id"]
    ]
    assert payload["scores"][0]["overall_score"] == checked.json()["overall_score"]
    assert payload["recommendations"][0]["state"] == "open"
    assert payload["latest_sync_at"] == checked.json()["checked_at"]
    assert "page_checked" in [event["event_type"] for event in payload["events"]]


def test_page_monitoring_hides_pages_from_other_projects(
    client: TestClient, session, auth_as, projects
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="other-project-monitoring-page",
        project_id=projects.other_project.id,
        wordpress_object_id=704,
        post_type="page",
        status="publish",
        title="Other",
        slug="other",
        url="https://other.example/other",
    )
    session.add(page)
    session.commit()

    response = client.get(
        f"/projects/{projects.member_project.id}/wordpress-pages/{page.id}/monitoring"
    )

    assert response.status_code == 404


def test_page_monitoring_binds_projection_to_captured_version_when_live_changed(
    client: TestClient, session, auth_as, projects
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="proposal-scope-page",
        project_id=projects.member_project.id,
        wordpress_object_id=705,
        post_type="page",
        status="publish",
        title="DSG revisie",
        slug="dsg-revisie",
        url="https://member.example/dsg-revisie",
    )
    session.add(page)
    session.commit()
    proposal = _existing_page_proposal(
        session,
        projects,
        page,
        "captured-proposal",
        package={
            "text_replacements": {
                "seo:meta_description": (
                    "Deskundige DSG revisie door ervaren specialisten met heldere "
                    "diagnose en persoonlijk advies."
                )
            }
        },
        config_snapshot={
            "source_content_hash": "captured-hash",
            "content_schema": {
                "document_fields": [{
                    "id": "seo:meta_description",
                    "path": "seo.meta_description",
                }],
                "blocks": [],
            },
        },
    )
    captured = PageObservedVersion(
        id="captured-version",
        project_id=page.project_id,
        wordpress_page_id=page.id,
        content_hash="captured-hash",
        source="sync",
        snapshot_payload={
            "content_hash": "captured-hash",
            "values": {"title": page.title, "meta_description": ""},
        },
        observed_at=datetime(2026, 8, 1, 10, tzinfo=UTC),
    )
    live = PageObservedVersion(
        id="live-version",
        project_id=page.project_id,
        wordpress_page_id=page.id,
        content_hash="live-hash",
        source="manual",
        snapshot_payload={
            "content_hash": "live-hash",
            "values": {
                "title": page.title,
                "meta_description": (
                    "Deze live tekst mag niet als voorstelbasis dienen."
                ),
            },
        },
        observed_at=datetime(2026, 8, 2, 10, tzinfo=UTC),
    )
    session.add_all([
        captured,
        live,
        PageScoreSnapshot(
            id="captured-score",
            page_version_id=captured.id,
            overall_score=31,
            factors=[{
                "key": "meta_description",
                "value": "",
                "points": 0,
                "max_points": 10,
                "explanation": "Captured explanation.",
                "suggested_action": "Add a meta description.",
                "evidence": {"value": ""},
            }],
            created_at=datetime(2026, 8, 1, 10, tzinfo=UTC),
        ),
        PageScoreSnapshot(
            id="live-score",
            page_version_id=live.id,
            overall_score=92,
            factors=[],
            created_at=datetime(2026, 8, 2, 10, tzinfo=UTC),
        ),
    ])
    session.commit()

    response = client.get(
        f"/projects/{page.project_id}/wordpress-pages/{page.id}/monitoring",
        params={"proposal_id": proposal.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["captured_version"]["id"] == captured.id
    assert payload["captured_score"]["id"] == "captured-score"
    assert payload["live_changed_since_capture"] is True
    meta = next(
        factor
        for factor in payload["projected_score"]["factors"]
        if factor["key"] == "meta_description"
    )
    assert meta["points"] == 10


def test_page_monitoring_does_not_fallback_when_captured_version_is_missing(
    client: TestClient, session, auth_as, projects
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="missing-capture-page",
        project_id=projects.member_project.id,
        wordpress_object_id=708,
        post_type="page",
        status="publish",
        title="Missing capture",
        slug="missing-capture",
        url="https://member.example/missing-capture",
    )
    session.add(page)
    session.commit()
    proposal = _existing_page_proposal(
        session,
        projects,
        page,
        "missing-capture-proposal",
        config_snapshot={
            "source_content_hash": "not-observed",
            "content_schema": {"document_fields": [], "blocks": []},
        },
    )
    session.add(
        PageObservedVersion(
            id="unrelated-live-version",
            project_id=page.project_id,
            wordpress_page_id=page.id,
            content_hash="newest-live-hash",
            source="sync",
            snapshot_payload={"content_hash": "newest-live-hash", "values": {}},
        )
    )
    session.commit()

    response = client.get(
        f"/projects/{page.project_id}/wordpress-pages/{page.id}/monitoring",
        params={"proposal_id": proposal.id},
    )

    assert response.status_code == 200
    assert response.json()["captured_version"] is None
    assert response.json()["captured_score"] is None
    assert response.json()["projected_score"] is None


def test_page_monitoring_uses_only_durable_lifecycle_states_and_events(
    client: TestClient, session, auth_as, projects
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="lifecycle-page",
        project_id=projects.member_project.id,
        wordpress_object_id=706,
        post_type="page",
        status="publish",
        title="Automaat revisie",
        slug="automaat-revisie",
        url="https://member.example/automaat-revisie",
    )
    session.add(page)
    session.commit()
    approved_at = datetime(2026, 8, 2, 10, tzinfo=UTC)
    proposal = _existing_page_proposal(
        session,
        projects,
        page,
        "lifecycle-proposal",
        state="draft_created",
        approved_by=projects.member.id,
        approved_at=approved_at,
        created_at=datetime(2026, 8, 1, 10, tzinfo=UTC),
    )
    payload = {}
    draft_job = WordPressDraftJob(
        id="lifecycle-draft-job",
        project_id=page.project_id,
        proposal_version_id=proposal.id,
        contract_version="wordpress-draft-job-v1",
        state="completed",
        payload=payload,
        payload_hash=hash_draft_job_payload(payload),
        terminal_claim_token_hash="a" * 64,
        completed_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
    )
    published = PageObservedVersion(
        id="lifecycle-version",
        project_id=page.project_id,
        wordpress_page_id=page.id,
        content_hash="lifecycle-hash",
        source="publication_check",
        snapshot_payload={"content_hash": "lifecycle-hash", "values": {}},
        proposal_version_id=proposal.id,
        draft_job_id=draft_job.id,
        published_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
    )
    accepted = PagePackageRegenerationCandidate(
        id="accepted-candidate",
        proposal_group_id=proposal.proposal_group_id,
        base_version_id=proposal.id,
        generation_mode="full",
        candidate_package={},
        candidate_rendered_html="",
        status="accepted",
        created_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        updated_at=datetime(2026, 8, 2, 12, tzinfo=UTC),
    )
    discarded = PagePackageRegenerationCandidate(
        id="discarded-candidate",
        proposal_group_id=proposal.proposal_group_id,
        base_version_id=proposal.id,
        generation_mode="full",
        candidate_package={},
        candidate_rendered_html="",
        status="discarded",
        created_at=datetime(2026, 8, 2, 13, tzinfo=UTC),
        updated_at=datetime(2026, 8, 2, 14, tzinfo=UTC),
    )
    recommendation_event = PageTimelineEvent(
        id="recommendation-event",
        project_id=page.project_id,
        wordpress_page_id=page.id,
        page_version_id=published.id,
        event_type="recommendation_created",
        payload={"recommendation_id": "recommendation-1"},
        created_at=datetime(2026, 8, 4, 11, tzinfo=UTC),
    )
    session.add_all([
        draft_job,
        published,
        accepted,
        discarded,
        recommendation_event,
    ])
    session.commit()

    response = client.get(
        f"/projects/{page.project_id}/wordpress-pages/{page.id}/monitoring",
        params={"proposal_id": proposal.id},
    )

    assert response.status_code == 200
    event_types = {event["event_type"] for event in response.json()["events"]}
    assert {
        "proposal_version_created",
        "proposal_approved",
        "candidate_created",
        "candidate_accepted",
        "candidate_discarded",
        "recommendation_created",
        "draft_created",
    } <= event_types
    assert "published" not in event_types


def test_projected_score_uses_proposed_snapshot_values() -> None:
    projected = wordpress_routes._projected_score(
        {
            "content_hash": "projection-hash",
            "values": {
                "title": "DSG revisie",
                "meta_description": "",
                "content": "<h1>DSG revisie</h1>",
            },
        },
        {
            "content_schema": {
                "schema_version": "snapshot-text-v1",
                "document_fields": [
                    {
                        "id": "seo:meta_description",
                        "path": "seo.meta_description",
                        "value_type": "meta_description",
                    }
                ],
                "blocks": [],
            }
        },
        {
            "text_replacements": {
                "seo:meta_description": (
                    "Deskundige DSG revisie door een ervaren specialist in "
                    "automatische transmissies."
                ),
            }
        },
        "<h1>DSG revisie</h1>",
    )

    factor = next(
        item for item in projected["factors"] if item["key"] == "meta_description"
    )
    assert factor["points"] == 10
    assert projected["overall_score"] > 0


def test_failed_draft_job_does_not_report_draft_ready() -> None:
    status = wordpress_routes._monitoring_status(
        SimpleNamespace(state="approved"),
        SimpleNamespace(state="failed"),
        [],
        [],
    )

    assert status == "proposal_ready"


def test_open_deduplicated_recommendation_keeps_page_attention_status() -> None:
    status = wordpress_routes._monitoring_status(
        None,
        None,
        [
            SimpleNamespace(overall_score=60, page_version_id="new"),
            SimpleNamespace(overall_score=60, page_version_id="old"),
        ],
        [SimpleNamespace(state="open", page_version_id="old")],
    )

    assert status == "needs_attention"


def test_failed_manual_fetch_does_not_advance_latest_check(
    client: TestClient, session, auth_as, projects, monkeypatch
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id="failed-check-page",
        project_id=projects.member_project.id,
        wordpress_object_id=709,
        post_type="page",
        status="publish",
        title="Failed check",
        slug="failed-check",
        url="https://member.example/failed-check",
        last_synced_at=datetime.now(UTC) + timedelta(days=30),
    )
    session.add(page)
    session.commit()

    class WorkingClient:
        def current_state(self, _object_id: int) -> dict:
            return {"content_hash": "working-hash", "values": {}}

    monkeypatch.setattr(
        wordpress_routes,
        "_connection_client",
        lambda _session, _project_id: WorkingClient(),
    )
    succeeded = client.post(
        f"/projects/{page.project_id}/wordpress-pages/{page.id}/checks"
    )
    before = client.get(
        f"/projects/{page.project_id}/wordpress-pages/{page.id}/monitoring"
    ).json()["latest_sync_at"]

    class FailingClient:
        def current_state(self, _object_id: int) -> dict:
            raise RuntimeError("WordPress unavailable")

    monkeypatch.setattr(
        wordpress_routes,
        "_connection_client",
        lambda _session, _project_id: FailingClient(),
    )
    failed = client.post(
        f"/projects/{page.project_id}/wordpress-pages/{page.id}/checks"
    )
    after = client.get(
        f"/projects/{page.project_id}/wordpress-pages/{page.id}/monitoring"
    ).json()["latest_sync_at"]

    assert succeeded.status_code == 200
    assert failed.status_code == 400
    assert before == succeeded.json()["checked_at"]
    assert after == before
