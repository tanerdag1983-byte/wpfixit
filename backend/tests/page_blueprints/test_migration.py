from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import page_blueprints
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.service import legacy_blueprint_candidates
from app.domains.page_packages.models import (
    PagePackageProposal,
    ProjectPagePackageSettings,
)


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
    def __init__(self, captures: list[dict | Exception]) -> None:
        self.captures = captures
        self.deleted: list[int] = []

    def capture_blueprint(self, payload: dict) -> dict:
        result = self.captures.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def delete_blueprint(self, wordpress_blueprint_id: int) -> dict:
        self.deleted.append(wordpress_blueprint_id)
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
    opportunity = KeywordOpportunity(
        id=f"opportunity-{proposal_id}",
        project_id=blueprint.project_id,
        keyword=f"keyword {proposal_id}",
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
        package={"replacements": [{"field_id": "acf-title", "value": "New"}]},
        rendered_html="<h1>New</h1>",
        config_snapshot={"source": "migration-test"},
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
    bridge = MigrationBridge(
        [
            snapshot_capture(wordpress_id=801, version=2),
            RuntimeError("capture failed"),
        ]
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


def test_migration_versions_compatible_unapproved_proposal_and_preserves_approved(
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
    stored_approved = session.get(PagePackageProposal, approved.id)
    assert stored_approved is not None
    assert stored_approved.blueprint_id == legacy.id
    assert stored_approved.current_version_id == approved.id
    assert stored_approved.is_current is True


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
