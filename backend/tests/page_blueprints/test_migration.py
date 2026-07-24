from datetime import UTC, datetime

import pytest
import requests
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes import page_blueprints, page_packages
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.service import legacy_blueprint_candidates
from app.domains.page_packages.models import (
    PagePackageProposal,
    PageProposalStage,
    ProjectPagePackageSettings,
)
from app.domains.wordpress.draft_jobs import create_or_get_draft_job


def legacy_blueprint(
    *,
    blueprint_id: str,
    project_id: str,
    wordpress_id: int,
) -> PageBlueprint:
    return PageBlueprint(
        id=blueprint_id,
        project_id=project_id,
        name=f"Legacy {blueprint_id}",
        page_type="service",
        source_wordpress_page_id="source-page",
        wordpress_blueprint_id=wordpress_id,
        builder="acf",
        seo_plugin="yoast",
        version=1,
        structure_hash=f"legacy-hash-{blueprint_id}",
        content_schema={
            "schema_version": "blueprint-v1",
            "blocks": [
                {
                    "id": "block-hero",
                    "layout": "hero",
                    "label": "Hero",
                    "semantic_role": "hero",
                    "fields": [
                        {
                            "id": "acf-title",
                            "path": "page_blocks/0/title",
                            "label": "Titel",
                            "value_type": "heading",
                            "current_value": "Legacy title",
                            "required": True,
                            "max_length": 180,
                        }
                    ],
                }
            ],
        },
        state="ready",
        is_default_for_page_type=False,
    )


class MigrationBridge:
    def __init__(
        self,
        captures: list[dict | Exception],
        *,
        on_capture=None,
        delete_results: list[None | Exception] | None = None,
    ) -> None:
        self.captures = captures
        self.capture_payloads: list[dict] = []
        self.deleted: list[int] = []
        self.inspections: dict[int, dict] = {}
        self.on_capture = on_capture
        self.delete_results = delete_results or []

    def capture_blueprint(self, payload: dict) -> dict:
        self.capture_payloads.append(payload)
        if self.on_capture is not None:
            self.on_capture(payload)
        result = self.captures.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def blueprint(self, wordpress_blueprint_id: int) -> dict:
        return self.inspections[wordpress_blueprint_id]

    def delete_blueprint(self, wordpress_blueprint_id: int) -> dict:
        self.deleted.append(wordpress_blueprint_id)
        if self.delete_results:
            result = self.delete_results.pop(0)
            if isinstance(result, Exception):
                raise result
        return {"deleted": True}


def proposal_for_blueprint(
    session: Session,
    *,
    proposal_id: str,
    blueprint: PageBlueprint,
    proposed_by: str,
    state: str = "proposed",
    approved: bool = False,
) -> PagePackageProposal:
    keyword = f"keyword {proposal_id}"
    opportunity = KeywordOpportunity(
        id=f"opportunity-{proposal_id}",
        project_id=blueprint.project_id,
        keyword=keyword,
        location_code=2528,
        language_code="nl",
        search_volume=100,
        target_classification="new_page",
        target_score=50,
        target_evidence=["test"],
        source="test",
        raw_payload={},
    )
    job = Job(
        id=f"job-{proposal_id}",
        project_id=blueprint.project_id,
        job_type="page_package_generation",
        state="completed",
        progress=100,
        checkpoint={},
    )
    proposal = PagePackageProposal(
        id=proposal_id,
        project_id=blueprint.project_id,
        opportunity_id=opportunity.id,
        job_id=job.id,
        state=state,
        proposal_group_id=f"group-{proposal_id}",
        current_version_id=proposal_id,
        is_current=True,
        blueprint_id=blueprint.id,
        blueprint_version=blueprint.version,
        blueprint_structure_hash=blueprint.structure_hash,
        package={
            "title": "Migrated transmission service page",
            "slug": "migrated-transmission-service",
            "seo_title": "Migrated transmission service specialist",
            "meta_description": (
                "A complete migrated transmission service proposal with enough "
                "detail for the existing approval validation contract."
            ),
            "focus_keyword": keyword,
            "replacements": [
                {"field_id": "acf-title", "value": "Migrated service"}
            ],
            "internal_links": [],
        },
        rendered_html="<h1>New</h1>",
        config_snapshot={
            "source": "migration-test",
            "blueprint_id": blueprint.id,
            "page_type": blueprint.page_type,
            "version": blueprint.version,
            "structure_hash": blueprint.structure_hash,
            "builder": blueprint.builder,
            "seo_plugin": blueprint.seo_plugin,
            "content_schema": blueprint.content_schema,
        },
        proposed_by=proposed_by,
        approved_by=proposed_by if approved else None,
    )
    session.add_all([opportunity, job, proposal])
    return proposal


def test_legacy_page_package_becomes_capture_required_candidate(
    session: Session, projects
) -> None:
    legacy_settings = ProjectPagePackageSettings(
        project_id=projects.member_project.id,
        builder="acf",
        template_wordpress_page_id="source-page",
        seo_plugin="yoast",
        slot_mapping={"hero_title": "acf-block:hero/title"},
        template_content_hash="legacy-hash",
        validation_state="valid",
    )
    session.add(legacy_settings)
    session.commit()

    candidates = legacy_blueprint_candidates(session, legacy_settings.project_id)

    assert len(candidates) == 1
    assert (
        candidates[0].source_wordpress_page_id
        == legacy_settings.template_wordpress_page_id
    )
    assert candidates[0].state == "capture_required"
    assert legacy_settings.validation_state == "valid"
    assert session.scalar(select(func.count()).select_from(PageBlueprint)) == 0


def test_invalid_legacy_settings_do_not_create_candidate(
    session: Session, projects
) -> None:
    session.add(
        ProjectPagePackageSettings(
            project_id=projects.member_project.id,
            builder="acf",
            template_wordpress_page_id="source-page",
            seo_plugin="yoast",
            slot_mapping={},
            validation_state="invalid",
        )
    )
    session.commit()

    assert legacy_blueprint_candidates(session, projects.member_project.id) == []


def test_migration_is_per_blueprint_and_preserves_failed_legacy_registration(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    good = legacy_blueprint(
        blueprint_id="legacy-a-good",
        project_id=project_id,
        wordpress_id=701,
    )
    bad = legacy_blueprint(
        blueprint_id="legacy-b-bad",
        project_id=project_id,
        wordpress_id=702,
    )
    session.add_all([good, bad])
    session.commit()

    expected_migrating_ids = iter([good.id, bad.id])

    def assert_migrating(payload):
        blueprint_id = next(expected_migrating_ids)
        job = session.scalar(
            select(Job).where(
                Job.job_type == "page_blueprint_snapshot_migration",
                Job.checkpoint["blueprint_id"].as_string() == blueprint_id,
            )
        )
        assert job is not None
        assert job.state == "migrating"
        assert job.checkpoint["transitions"] == ["pending", "migrating"]

    bridge = MigrationBridge(
        [
            snapshot_capture(wordpress_id=801, version=2),
            RuntimeError("capture failed"),
        ],
        on_capture=assert_migrating,
    )
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    auth_as(projects.owner)

    response = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"blueprint_id": good.id, "state": "migrated"},
        {
            "blueprint_id": bad.id,
            "state": "failed",
            "action": "recapture",
        },
    ]
    session.expire_all()
    assert (
        session.scalar(
            select(PageBlueprint).where(PageBlueprint.supersedes_id == good.id)
        )
        is not None
    )
    assert session.get(PageBlueprint, bad.id).wordpress_blueprint_id == 702
    assert session.get(PageBlueprint, bad.id).wordpress_snapshot_id is None
    migration_jobs = {
        job.checkpoint["blueprint_id"]: job
        for job in session.scalars(
            select(Job).where(Job.job_type == "page_blueprint_snapshot_migration")
        )
    }
    assert migration_jobs[good.id].state == "migrated"
    assert migration_jobs[good.id].checkpoint["transitions"] == [
        "pending",
        "migrating",
        "migrated",
    ]
    assert migration_jobs[bad.id].state == "failed"
    assert migration_jobs[bad.id].checkpoint["transitions"] == [
        "pending",
        "migrating",
        "failed",
    ]


def test_migration_versions_compatible_proposal_for_approval_and_preserves_approved(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-proposals",
        project_id=project_id,
        wordpress_id=703,
    )
    session.add(legacy)
    compatible = proposal_for_blueprint(
        session,
        proposal_id="proposal-compatible",
        blueprint=legacy,
        proposed_by=projects.owner.id,
    )
    approved = proposal_for_blueprint(
        session,
        proposal_id="proposal-approved",
        blueprint=legacy,
        proposed_by=projects.owner.id,
        state="approved",
        approved=True,
    )
    session.commit()
    bridge = MigrationBridge([snapshot_capture(wordpress_id=803, version=2)])
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    monkeypatch.setattr(
        page_packages,
        "_page_package_client",
        lambda session, project_id: bridge,
    )
    auth_as(projects.owner)

    response = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"blueprint_id": legacy.id, "state": "migrated"}
    ]
    session.expire_all()
    successor = session.scalar(
        select(PageBlueprint).where(PageBlueprint.supersedes_id == legacy.id)
    )
    assert successor is not None
    old_compatible = session.get(PagePackageProposal, compatible.id)
    assert old_compatible is not None
    assert old_compatible.blueprint_id == legacy.id
    assert old_compatible.is_current is False
    migrated_proposal = session.scalar(
        select(PagePackageProposal).where(
            PagePackageProposal.parent_version_id == compatible.id
        )
    )
    assert migrated_proposal is not None
    assert migrated_proposal.blueprint_id == successor.id
    assert migrated_proposal.is_current is True
    assert migrated_proposal.config_snapshot == {
        "source": "migration-test",
        "blueprint_id": successor.id,
        "page_type": successor.page_type,
        "version": successor.version,
        "structure_hash": successor.structure_hash,
        "builder": successor.builder,
        "seo_plugin": successor.seo_plugin,
        "content_schema": successor.content_schema,
        "wordpress_snapshot_id": successor.wordpress_snapshot_id,
        "snapshot_version": successor.snapshot_version,
        "schema_version": successor.schema_version,
        "adapter_version": successor.adapter_version,
        "capture_state": successor.capture_state,
        "migration_state": successor.migration_state,
    }
    stored_approved = session.get(PagePackageProposal, approved.id)
    assert stored_approved is not None
    assert stored_approved.blueprint_id == legacy.id
    assert stored_approved.current_version_id == approved.id
    assert stored_approved.is_current is True

    bridge.inspections[successor.wordpress_snapshot_id] = snapshot_capture(
        wordpress_id=successor.wordpress_snapshot_id,
        version=successor.snapshot_version,
        created=False,
    )

    approval = client.post(
        f"/projects/{project_id}/page-proposals/{migrated_proposal.id}/approve"
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["state"] == "approved"
    session.expire_all()
    validation = session.scalar(
        select(PageProposalStage).where(
            PageProposalStage.proposal_version_id == migrated_proposal.id,
            PageProposalStage.name == "validation",
        )
    )
    assert validation is not None
    assert validation.state == "ready"
    assert validation.result["text_replacements"]["document:title"]
    assert "approved_urls" in validation.result

    draft_job = create_or_get_draft_job(session, migrated_proposal)
    assert draft_job.contract_version == "wordpress-snapshot-draft-job-v1"


def test_incompatible_unapproved_proposal_requires_generation(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    snapshot_schema,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-incompatible",
        project_id=project_id,
        wordpress_id=704,
    )
    session.add(legacy)
    proposal = proposal_for_blueprint(
        session,
        proposal_id="proposal-incompatible",
        blueprint=legacy,
        proposed_by=projects.owner.id,
    )
    session.commit()
    incompatible_schema = {
        **snapshot_schema,
        "blocks": [
            {
                **snapshot_schema["blocks"][0],
                "fields": [
                    {
                        **snapshot_schema["blocks"][0]["fields"][0],
                        "value_type": "url",
                    }
                ],
            }
        ],
    }
    bridge = MigrationBridge(
        [
            snapshot_capture(
                wordpress_id=804,
                version=2,
                schema=incompatible_schema,
            )
        ]
    )
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    auth_as(projects.owner)

    response = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "blueprint_id": legacy.id,
            "state": "incompatible",
            "action": "new_proposal",
        }
    ]
    session.expire_all()
    stored = session.get(PagePackageProposal, proposal.id)
    assert stored is not None
    assert stored.state == "failed"
    assert stored.blueprint_id == legacy.id
    assert session.get(Job, stored.job_id).error_code == (
        "snapshot_migration_requires_generation"
    )
    migration_job = session.scalar(
        select(Job).where(
            Job.job_type == "page_blueprint_snapshot_migration",
            Job.checkpoint["blueprint_id"].as_string() == legacy.id,
        )
    )
    assert migration_job is not None
    assert migration_job.state == "incompatible"
    assert migration_job.checkpoint["transitions"][-1] == "incompatible"


def test_failed_unfinished_proposal_requires_generation_without_successor_version(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-failed-proposal",
        project_id=project_id,
        wordpress_id=711,
    )
    session.add(legacy)
    failed = proposal_for_blueprint(
        session,
        proposal_id="proposal-failed-unfinished",
        blueprint=legacy,
        proposed_by=projects.owner.id,
        state="failed",
    )
    failed.package = {}
    session.commit()
    bridge = MigrationBridge([snapshot_capture(wordpress_id=812, version=2)])
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    auth_as(projects.owner)

    response = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "blueprint_id": legacy.id,
            "state": "incompatible",
            "action": "new_proposal",
        }
    ]
    session.expire_all()
    stored = session.get(PagePackageProposal, failed.id)
    assert stored is not None
    assert stored.state == "failed"
    assert stored.is_current is True
    assert stored.current_version_id == failed.id
    assert stored.blueprint_id == legacy.id
    assert (
        session.scalar(
            select(PagePackageProposal).where(
                PagePackageProposal.parent_version_id == failed.id
            )
        )
        is None
    )
    job = session.get(Job, stored.job_id)
    assert job is not None
    assert job.error_code == "snapshot_migration_requires_generation"


def test_migration_cleans_only_trusted_new_snapshot_after_validation_failure(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-invalid-capture",
        project_id=project_id,
        wordpress_id=705,
    )
    session.add(legacy)
    session.commit()
    invalid = snapshot_capture(wordpress_id=805, version=2)
    invalid["content_schema"] = {
        "schema_version": "snapshot-text-v1",
        "document_fields": [],
        "blocks": [],
    }
    bridge = MigrationBridge([invalid])
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    auth_as(projects.owner)

    response = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "blueprint_id": legacy.id,
            "state": "failed",
            "action": "recapture",
        }
    ]
    assert bridge.deleted == [805]
    session.expire_all()
    stored = session.get(PageBlueprint, legacy.id)
    assert stored.wordpress_blueprint_id == 705
    assert stored.wordpress_snapshot_id is None
    assert (
        session.scalar(
            select(PageBlueprint).where(PageBlueprint.supersedes_id == legacy.id)
        )
        is None
    )
    migration_job = session.scalar(
        select(Job).where(
            Job.job_type == "page_blueprint_snapshot_migration",
            Job.checkpoint["blueprint_id"].as_string() == legacy.id,
        )
    )
    assert migration_job is not None
    assert migration_job.state == "failed"
    assert migration_job.checkpoint["transitions"][-1] == "failed"


def test_migration_retries_durable_remote_cleanup_before_recapture(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-cleanup-retry",
        project_id=project_id,
        wordpress_id=708,
    )
    session.add(legacy)
    session.commit()
    response = requests.Response()
    response.status_code = 500
    bridge = MigrationBridge(
        [
            snapshot_capture(wordpress_id=808, version=2),
            snapshot_capture(wordpress_id=809, version=2),
        ],
        delete_results=[
            requests.HTTPError(response=response),
            requests.HTTPError(response=response),
            None,
        ],
    )
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    original_migrate = page_blueprints.migrate_unapproved_proposals
    migration_calls = 0

    def fail_first_backend_transaction(session, legacy, successor, proposals):
        nonlocal migration_calls
        migration_calls += 1
        if migration_calls == 1:
            raise RuntimeError("backend migration failed")
        return original_migrate(session, legacy, successor, proposals)

    monkeypatch.setattr(
        page_blueprints,
        "migrate_unapproved_proposals",
        fail_first_backend_transaction,
    )
    auth_as(projects.owner)

    first = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert first.status_code == 200, first.text
    assert first.json()["items"] == [
        {
            "blueprint_id": legacy.id,
            "state": "failed",
            "action": "cleanup",
        }
    ]
    session.expire_all()
    migration_job = session.scalar(
        select(Job).where(
            Job.job_type == "page_blueprint_snapshot_migration",
            Job.checkpoint["blueprint_id"].as_string() == legacy.id,
        )
    )
    assert migration_job is not None
    assert migration_job.checkpoint["cleanup_snapshot_id"] == 808
    assert len(bridge.capture_payloads) == 1

    second = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert second.status_code == 200, second.text
    assert second.json()["items"] == [
        {
            "blueprint_id": legacy.id,
            "state": "failed",
            "action": "cleanup",
        }
    ]
    assert len(bridge.capture_payloads) == 1
    session.expire_all()
    assert migration_job.checkpoint["cleanup_snapshot_id"] == 808

    third = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert third.status_code == 200, third.text
    assert third.json()["items"] == [
        {"blueprint_id": legacy.id, "state": "migrated"}
    ]
    assert len(bridge.capture_payloads) == 2
    assert bridge.deleted == [808, 808, 808]
    session.expire_all()
    assert "cleanup_snapshot_id" not in migration_job.checkpoint


def test_migration_waits_for_current_generating_proposal_before_capture(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-generating",
        project_id=project_id,
        wordpress_id=709,
    )
    session.add(legacy)
    generating = proposal_for_blueprint(
        session,
        proposal_id="proposal-generating",
        blueprint=legacy,
        proposed_by=projects.owner.id,
        state="generating",
    )
    session.commit()
    bridge = MigrationBridge([snapshot_capture(wordpress_id=810, version=2)])
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    auth_as(projects.owner)

    response = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "blueprint_id": legacy.id,
            "state": "pending",
            "action": "wait",
        }
    ]
    assert bridge.capture_payloads == []
    session.expire_all()
    assert (
        session.scalar(
            select(PageBlueprint).where(PageBlueprint.supersedes_id == legacy.id)
        )
        is None
    )
    stored = session.get(PagePackageProposal, generating.id)
    assert stored is not None
    assert stored.state == "generating"
    assert stored.is_current is True
    assert stored.current_version_id == generating.id
    assert stored.blueprint_id == legacy.id
    migration_job = session.scalar(
        select(Job).where(
            Job.job_type == "page_blueprint_snapshot_migration",
            Job.checkpoint["blueprint_id"].as_string() == legacy.id,
        )
    )
    assert migration_job is not None
    assert migration_job.state == "pending"
    assert migration_job.checkpoint["action"] == "wait"
    assert migration_job.checkpoint["blocked_proposal_ids"] == [generating.id]


def test_concurrent_successor_terminalizes_migrating_job_without_capture(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-concurrent-successor",
        project_id=project_id,
        wordpress_id=710,
    )
    session.add(legacy)
    session.commit()
    captured = snapshot_capture(wordpress_id=811, version=2)
    concurrent_successor = PageBlueprint(
        id="concurrent-successor",
        project_id=project_id,
        name=legacy.name,
        page_type=legacy.page_type,
        source_wordpress_page_id=legacy.source_wordpress_page_id,
        wordpress_blueprint_id=811,
        wordpress_snapshot_id=811,
        snapshot_version=2,
        schema_version="snapshot-text-v1",
        adapter_version="acf-v1",
        capture_state="ready",
        migration_state="native",
        verified_at=datetime.now(UTC),
        builder="acf",
        seo_plugin="yoast",
        version=2,
        structure_hash=captured["structure_hash"],
        content_schema=captured["content_schema"],
        state="ready",
        is_default_for_page_type=False,
        supersedes_id=legacy.id,
    )
    bridge = MigrationBridge([])
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    original_scalar = session.scalar
    successor_added = False
    successor_checked_before_lock = False

    def add_successor_after_legacy_lock(statement, *args, **kwargs):
        nonlocal successor_added, successor_checked_before_lock
        sql = str(statement)
        is_legacy_lock = (
            "page_blueprints.id =" in sql
            and "page_blueprints.wordpress_snapshot_id IS NULL" in sql
        )
        is_successor_recheck = "page_blueprints.supersedes_id =" in sql
        if is_successor_recheck and not successor_added:
            successor_checked_before_lock = True
        result = original_scalar(statement, *args, **kwargs)
        if is_legacy_lock and not successor_added:
            session.add(concurrent_successor)
            session.flush()
            successor_added = True
        return result

    monkeypatch.setattr(session, "scalar", add_successor_after_legacy_lock)
    auth_as(projects.owner)

    response = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"blueprint_id": legacy.id, "state": "migrated"}
    ]
    assert bridge.capture_payloads == []
    assert successor_checked_before_lock is False
    session.expire_all()
    migration_job = session.scalar(
        select(Job).where(
            Job.job_type == "page_blueprint_snapshot_migration",
            Job.checkpoint["blueprint_id"].as_string() == legacy.id,
        )
    )
    assert migration_job is not None
    assert migration_job.state == "migrated"
    assert migration_job.checkpoint["successor_blueprint_id"] == (
        concurrent_successor.id
    )


def test_migration_reloads_cleanup_committed_while_waiting_for_legacy_lock(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-concurrent-cleanup",
        project_id=project_id,
        wordpress_id=712,
    )
    session.add(legacy)
    session.commit()
    events: list[str] = []

    class OrderedMigrationBridge(MigrationBridge):
        def capture_blueprint(self, payload):
            events.append("capture")
            return super().capture_blueprint(payload)

        def delete_blueprint(self, wordpress_blueprint_id):
            events.append(f"delete:{wordpress_blueprint_id}")
            return super().delete_blueprint(wordpress_blueprint_id)

    bridge = OrderedMigrationBridge(
        [snapshot_capture(wordpress_id=813, version=2)]
    )
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    original_scalar = session.scalar
    cleanup_committed = False

    def commit_cleanup_after_legacy_lock(statement, *args, **kwargs):
        nonlocal cleanup_committed
        result = original_scalar(statement, *args, **kwargs)
        sql = str(statement)
        if (
            not cleanup_committed
            and "page_blueprints.id =" in sql
            and "page_blueprints.wordpress_snapshot_id IS NULL" in sql
        ):
            job_id = page_blueprints.snapshot_migration_job_id(legacy.id)
            stale_job = session.get(Job, job_id)
            checkpoint = {
                **stale_job.checkpoint,
                "action": "cleanup",
                "cleanup_snapshot_id": 812,
            }
            session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(
                    state="failed",
                    checkpoint=checkpoint,
                    error_code="snapshot_migration_cleanup_required",
                ),
                execution_options={"synchronize_session": False},
            )
            cleanup_committed = True
        return result

    monkeypatch.setattr(session, "scalar", commit_cleanup_after_legacy_lock)
    auth_as(projects.owner)

    response = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"blueprint_id": legacy.id, "state": "migrated"}
    ]
    assert events == ["delete:812", "capture"]
    assert bridge.deleted == [812]
    assert len(bridge.capture_payloads) == 1
    session.expire_all()
    migration_job = session.get(
        Job,
        page_blueprints.snapshot_migration_job_id(legacy.id),
    )
    assert migration_job is not None
    assert migration_job.state == "migrated"
    assert "cleanup_snapshot_id" not in migration_job.checkpoint


def test_migration_persists_captured_seo_identity_and_verifies_successor(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    project_id = projects.member_project.id
    legacy = legacy_blueprint(
        blueprint_id="legacy-seo-change",
        project_id=project_id,
        wordpress_id=706,
    )
    session.add(legacy)
    session.commit()
    captured = snapshot_capture(
        wordpress_id=806,
        version=2,
        seo_plugin="rank_math",
    )
    bridge = MigrationBridge([captured])
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    auth_as(projects.owner)

    migrated = client.post(f"/projects/{project_id}/page-blueprints/migrate")

    assert migrated.status_code == 200, migrated.text
    session.expire_all()
    successor = session.scalar(
        select(PageBlueprint).where(PageBlueprint.supersedes_id == legacy.id)
    )
    assert successor is not None
    assert successor.seo_plugin == "rank_math"
    bridge.inspections[806] = snapshot_capture(
        wordpress_id=806,
        version=2,
        created=False,
        seo_plugin="rank_math",
    )

    verified = client.post(
        f"/projects/{project_id}/page-blueprints/{successor.id}/verify"
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["seo_plugin"] == "rank_math"


def test_route_fixture_enforces_composite_blueprint_foreign_key(
    session: Session,
    projects,
) -> None:
    blueprint = legacy_blueprint(
        blueprint_id="legacy-fk",
        project_id=projects.member_project.id,
        wordpress_id=707,
    )
    session.add(blueprint)
    proposal = proposal_for_blueprint(
        session,
        proposal_id="proposal-fk",
        blueprint=blueprint,
        proposed_by=projects.owner.id,
    )
    proposal.blueprint_version = blueprint.version + 1

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
