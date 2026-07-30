from datetime import UTC, datetime

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import page_blueprints
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_packages.models import PagePackageProposal
from app.domains.wordpress.models import WordPressPage


def valid_schema(*, role: str = "hero") -> dict:
    def field(field_id: str, path: str, value_type: str) -> dict:
        return {
            "id": field_id,
            "path": path,
            "label": field_id,
            "value_type": value_type,
            "current_value": "",
            "required": True,
            "max_length": 180,
        }

    return {
        "schema_version": "snapshot-text-v1",
        "document_fields": [
            field("document:title", "post_title", "heading"),
            field("document:slug", "post_name", "plain_text"),
            field("seo:title", "seo.title", "seo_title"),
            field(
                "seo:meta_description",
                "seo.meta_description",
                "meta_description",
            ),
            field("seo:focus_keyword", "seo.focus_keyword", "focus_keyword"),
        ],
        "blocks": [
            {
                "id": "block-hero",
                "layout": "hero_algemeen",
                "label": "Hero (algemeen)",
                "semantic_role": role,
                "fields": [
                    {
                        "id": "acf-title",
                        "path": "page_blocks/0/title",
                        "label": "Titel",
                        "value_type": "heading",
                        "current_value": "Transmissie onderhoud",
                        "required": True,
                        "max_length": 180,
                    }
                ],
            }
        ],
    }


def captured_blueprint(*, wordpress_id: int = 901, version: int = 1) -> dict:
    return {
        "created": True,
        "wordpress_blueprint_id": wordpress_id,
        "wordpress_snapshot_id": wordpress_id,
        "snapshot_version": version,
        "schema_version": "snapshot-text-v1",
        "post_type": "wpfixpilot_snapshot",
        "adapter_version": "acf-v1",
        "source_page_id": 19,
        "builder": "acf",
        "page_type": "service",
        "seo_plugin": "yoast",
        "version": version,
        "structure_hash": f"hash-v{version}",
        "content_schema": valid_schema(),
        "status": "ready",
    }


class FakeBlueprintBridge:
    def __init__(self) -> None:
        self.captures = [
            captured_blueprint(),
            captured_blueprint(wordpress_id=902, version=2),
        ]
        self.deleted: list[int] = []
        self.inspections: dict[int, dict] = {}
        self.capture_payloads: list[dict] = []

    def capture_blueprint(self, payload: dict) -> dict:
        self.capture_payloads.append(payload)
        captured = self.captures.pop(0)
        captured["page_type"] = payload["page_type"]
        captured["version"] = payload["version"]
        captured["snapshot_version"] = payload["version"]
        return captured

    def blueprint(self, wordpress_blueprint_id: int) -> dict:
        return self.inspections.get(
            wordpress_blueprint_id,
            captured_blueprint(wordpress_id=wordpress_blueprint_id),
        )

    def delete_blueprint(self, wordpress_blueprint_id: int) -> dict:
        self.deleted.append(wordpress_blueprint_id)
        return {"deleted": True}


class TimeoutBlueprintBridge(FakeBlueprintBridge):
    def capture_blueprint(self, payload: dict) -> dict:
        raise requests.Timeout("WordPress took too long")


def create_blueprint(client: TestClient, project_id: str) -> dict:
    response = client.post(
        f"/projects/{project_id}/page-blueprints",
        json={
            "name": "Dienstpagina",
            "page_type": "service",
            "source_wordpress_page_id": "source-page",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_optimization_source_is_hidden_from_registry_and_actions(
    client,
    auth_as,
    projects,
    session,
    monkeypatch,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    optimization_source = PageBlueprint(
        id="optimization-source-blueprint",
        project_id=projects.member_project.id,
        name="Existing page capture",
        page_type="service",
        source_wordpress_page_id="source-page",
        wordpress_blueprint_id=990,
        wordpress_snapshot_id=990,
        snapshot_version=1,
        schema_version="snapshot-text-v1",
        adapter_version="optimization-source-v1",
        capture_state="ready",
        migration_state="native",
        verified_at=datetime.now(UTC),
        builder="acf",
        seo_plugin="yoast",
        version=1,
        structure_hash="optimization-source-hash",
        content_schema=valid_schema(),
        state="ready",
        is_default_for_page_type=False,
    )
    session.add(optimization_source)
    session.commit()
    route = (
        f"/projects/{projects.member_project.id}/page-blueprints/"
        f"{optimization_source.id}"
    )

    listed = client.get(f"/projects/{projects.member_project.id}/page-blueprints")
    detail = client.get(route)
    defaulted = client.post(f"{route}/set-default")
    versioned = client.post(f"{route}/new-version")

    assert listed.status_code == 200
    assert listed.json()["items"] == []
    for response in (detail, defaulted, versioned):
        assert response.status_code == 404
        assert response.json()["detail"] == "Blueprint not found"
    assert bridge.capture_payloads == []


def test_capture_timeout_returns_actionable_gateway_error(
    client, auth_as, projects, monkeypatch
):
    auth_as(projects.owner)
    monkeypatch.setattr(
        page_blueprints,
        "_bridge",
        lambda session, project_id: TimeoutBlueprintBridge(),
    )

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints",
        json={
            "name": "Blogartikel",
            "page_type": "blog",
            "source_wordpress_page_id": "source-page",
        },
    )

    assert response.status_code == 504
    assert response.json()["detail"] == (
        "WordPress had meer tijd nodig om deze pagina vast te leggen. Probeer opnieuw."
    )


def test_publishing_source_after_capture_does_not_stale_snapshot(
    client,
    auth_as,
    projects,
    session,
    snapshot_capture,
    monkeypatch,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    bridge.captures = [snapshot_capture()]
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)

    source = session.get(WordPressPage, "source-page")
    source.status = "draft"
    session.commit()
    created = create_blueprint(client, projects.member_project.id)
    source.status = "publish"
    session.commit()
    bridge.inspections[901] = snapshot_capture(created=False)

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/"
        f"{created['id']}/verify"
    )

    assert response.status_code == 200, response.text
    assert response.json()["capture_state"] == "ready"
    assert response.json()["wordpress_snapshot_id"] == 901


def test_manager_captures_lists_defaults_and_versions_blueprint(
    client, auth_as, projects, monkeypatch
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)

    created = create_blueprint(client, projects.member_project.id)
    blueprint_id = created["id"]
    assert created["builder"] == "acf"
    assert created["state"] == "ready"
    assert bridge.capture_payloads == [
        {
            "source_page_id": 19,
            "name": "Dienstpagina",
            "page_type": "service",
            "version": 1,
        }
    ]

    listed = client.get(f"/projects/{projects.member_project.id}/page-blueprints")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [blueprint_id]

    defaulted = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/{blueprint_id}/set-default"
    )
    assert defaulted.status_code == 200
    assert defaulted.json()["is_default_for_page_type"] is True

    versioned = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/{blueprint_id}/new-version"
    )
    assert versioned.status_code == 201, versioned.text
    assert versioned.json()["version"] == 2
    assert versioned.json()["supersedes_id"] == blueprint_id
    assert versioned.json()["is_default_for_page_type"] is True
    assert bridge.capture_payloads[-1] == {
        "source_page_id": 19,
        "name": "Dienstpagina",
        "page_type": "service",
        "version": 2,
    }


def test_route_rejects_reactivating_superseded_legacy_default(
    client,
    auth_as,
    projects,
    monkeypatch,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    legacy = create_blueprint(client, projects.member_project.id)
    defaulted = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/"
        f"{legacy['id']}/set-default"
    )
    assert defaulted.status_code == 200
    successor = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/"
        f"{legacy['id']}/new-version"
    ).json()

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/"
        f"{legacy['id']}/set-default"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "A superseded blueprint cannot be set as the default"
    )
    current = client.get(
        f"/projects/{projects.member_project.id}/page-blueprints/{successor['id']}"
    ).json()
    assert current["is_default_for_page_type"] is True


def test_routes_require_manager_and_project_membership(
    client, auth_as, projects, monkeypatch
):
    monkeypatch.setattr(
        page_blueprints, "_bridge", lambda session, project_id: FakeBlueprintBridge()
    )
    auth_as(projects.viewer)
    denied = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints",
        json={
            "name": "Dienstpagina",
            "page_type": "service",
            "source_wordpress_page_id": "source-page",
        },
    )
    assert denied.status_code == 403

    auth_as(projects.outsider)
    hidden = client.get(f"/projects/{projects.member_project.id}/page-blueprints")
    assert hidden.status_code == 404


def test_update_allows_roles_but_rejects_unknown_blocks(
    client, auth_as, projects, monkeypatch
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    route = f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"

    updated = client.put(
        route,
        json={
            "name": "Nieuwe naam",
            "semantic_roles": {"block-hero": "introduction"},
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Nieuwe naam"
    assert (
        updated.json()["content_schema"]["blocks"][0]["semantic_role"] == "introduction"
    )

    rejected = client.put(route, json={"semantic_roles": {"unknown": "hero"}})
    assert rejected.status_code == 422

    validated = client.post(f"{route}/validate")
    assert validated.status_code == 200, validated.text


def test_default_blueprint_page_type_cannot_be_changed(
    client, auth_as, projects, monkeypatch
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    route = f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    assert client.post(f"{route}/set-default").status_code == 200

    response = client.put(route, json={"page_type": "brand"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Change the default before changing page type"


def test_page_type_change_requires_a_new_blueprint_version(
    client, auth_as, projects, monkeypatch
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    route = f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"

    updated = client.put(route, json={"page_type": "brand"})
    assert updated.status_code == 200
    assert updated.json()["state"] == "stale"

    validation = client.post(f"{route}/validate")
    assert validation.status_code == 409

    versioned = client.post(f"{route}/new-version")
    assert versioned.status_code == 201, versioned.text
    assert versioned.json()["page_type"] == "brand"
    assert versioned.json()["state"] == "ready"


def test_validation_marks_hash_drift_stale(client, auth_as, projects, monkeypatch):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    bridge.inspections[901] = {
        **captured_blueprint(),
        "structure_hash": "changed",
    }

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}/validate"
    )
    assert response.status_code == 409
    detail = client.get(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    )
    assert detail.json()["state"] == "stale"


@pytest.mark.parametrize(
    ("override", "expected_state"),
    [
        ({"status": "invalid"}, "invalid"),
        ({"snapshot_version": 2}, "stale"),
        ({"builder": "elementor"}, "stale"),
        ({"seo_plugin": "rank_math"}, "stale"),
        ({"page_type": "brand"}, "stale"),
        ({"source_page_id": 77}, "stale"),
        ({"wordpress_snapshot_id": 999}, "stale"),
    ],
)
def test_validation_rejects_incompatible_wordpress_identity(
    client, auth_as, projects, monkeypatch, override, expected_state
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    bridge.inspections[901] = {**captured_blueprint(), **override}

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}/validate"
    )

    assert response.status_code == 409
    detail = client.get(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    )
    assert detail.json()["state"] == expected_state


def test_delete_removes_wordpress_clone_after_dependency_check(
    client, auth_as, projects, monkeypatch
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    original_lookup = page_blueprints._blueprint_or_404
    lock_requests: list[bool] = []

    def tracked_lookup(session, project_id, blueprint_id, *, for_update=False):
        lock_requests.append(for_update)
        return original_lookup(session, project_id, blueprint_id)

    monkeypatch.setattr(page_blueprints, "_blueprint_or_404", tracked_lookup)

    response = client.delete(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    )
    assert response.status_code == 204, response.text
    assert bridge.deleted == [901]
    assert lock_requests == [True]


def test_invalid_capture_is_removed_and_not_persisted(
    client, auth_as, projects, monkeypatch, session
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    bridge.captures[0]["content_schema"] = {
        "schema_version": "blueprint-v1",
        "blocks": [],
    }
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints",
        json={
            "name": "Ongeldig",
            "page_type": "service",
            "source_wordpress_page_id": "source-page",
        },
    )

    assert response.status_code == 502
    assert bridge.deleted == [901]
    assert session.scalar(select(PageBlueprint)) is None


def test_create_commit_failure_cleans_only_uncommitted_snapshot(
    client,
    auth_as,
    projects,
    monkeypatch,
    session,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)

    def fail_commit():
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="database commit failed"):
        client.post(
            f"/projects/{projects.member_project.id}/page-blueprints",
            json={
                "name": "Commit failure",
                "page_type": "service",
                "source_wordpress_page_id": "source-page",
            },
        )

    assert bridge.deleted == [901]
    session.rollback()
    assert session.scalar(select(PageBlueprint)) is None


def test_create_refresh_failure_keeps_committed_snapshot(
    client,
    auth_as,
    projects,
    monkeypatch,
    session,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    original_refresh = session.refresh

    def fail_blueprint_refresh(instance, *args, **kwargs):
        if isinstance(instance, PageBlueprint):
            raise RuntimeError("database refresh failed")
        return original_refresh(instance, *args, **kwargs)

    monkeypatch.setattr(session, "refresh", fail_blueprint_refresh)

    with pytest.raises(RuntimeError, match="database refresh failed"):
        create_blueprint(client, projects.member_project.id)

    assert bridge.deleted == []
    session.expire_all()
    stored = session.scalar(select(PageBlueprint))
    assert stored is not None
    assert stored.wordpress_snapshot_id == 901
    assert stored.state == "ready"


@pytest.mark.parametrize(
    "capture_override",
    [
        {"wordpress_snapshot_id": 0, "wordpress_blueprint_id": 0},
        {
            "wordpress_snapshot_id": "not-an-id",
            "wordpress_blueprint_id": "not-an-id",
        },
        {"wordpress_blueprint_id": 999},
        {"post_type": "page"},
        {"created": False},
    ],
)
def test_untrusted_capture_identity_is_never_deleted(
    client, auth_as, projects, monkeypatch, capture_override
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    bridge.captures[0].update(capture_override)
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints",
        json={
            "name": "Onbetrouwbaar",
            "page_type": "service",
            "source_wordpress_page_id": "source-page",
        },
    )

    assert response.status_code == 502
    assert bridge.deleted == []


@pytest.mark.parametrize("missing_key", ["post_type", "adapter_version"])
def test_capture_rejects_missing_snapshot_trust_field_without_cleanup(
    client,
    auth_as,
    projects,
    monkeypatch,
    missing_key,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    bridge.captures[0].pop(missing_key)
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints",
        json={
            "name": "Incomplete trust contract",
            "page_type": "service",
            "source_wordpress_page_id": "source-page",
        },
    )

    assert response.status_code == 502
    assert bridge.deleted == []


@pytest.mark.parametrize(
    "inspection_change",
    [
        {"post_type": None},
        {"post_type": "page"},
        {"adapter_version": None},
    ],
)
def test_verify_rejects_missing_or_wrong_snapshot_trust_field(
    client,
    auth_as,
    projects,
    monkeypatch,
    inspection_change,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    inspected = captured_blueprint()
    for key, value in inspection_change.items():
        if value is None:
            inspected.pop(key)
        else:
            inspected[key] = value
    bridge.inspections[901] = inspected

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/"
        f"{created['id']}/verify"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Snapshot structure has changed"


def test_duplicate_capture_identity_does_not_delete_existing_clone(
    client, auth_as, projects, monkeypatch
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    create_blueprint(client, projects.member_project.id)
    bridge.captures[0]["wordpress_snapshot_id"] = 901
    bridge.captures[0]["wordpress_blueprint_id"] = 901

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints",
        json={
            "name": "Dubbel",
            "page_type": "brand",
            "source_wordpress_page_id": "source-page",
        },
    )

    assert response.status_code == 409
    assert bridge.deleted == []


def test_delete_rejects_blueprint_used_by_proposal_before_wordpress_call(
    client, auth_as, projects, monkeypatch, session
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    opportunity = KeywordOpportunity(
        id="blueprint-opportunity",
        project_id=projects.member_project.id,
        keyword="dsg revisie",
        location_code=2528,
        language_code="nl",
        search_volume=100,
        keyword_difficulty=10,
        competition=0.2,
        competition_level="low",
        cpc=1.0,
        intent="commercial",
        source="test",
        target_classification="new_page",
        target_score=50,
        target_evidence=["test"],
        raw_payload={},
    )
    job = Job(
        id="blueprint-job",
        project_id=projects.member_project.id,
        job_type="page_package_generation",
        state="completed",
        progress=100,
        checkpoint={},
    )
    proposal = PagePackageProposal(
        id="blueprint-proposal",
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id=job.id,
        state="proposed",
        proposal_group_id="blueprint-proposal",
        current_version_id="blueprint-proposal",
        blueprint_id=created["id"],
        blueprint_version=created["version"],
        blueprint_structure_hash=created["structure_hash"],
        package={},
        rendered_html="",
        config_snapshot={},
        proposed_by=projects.owner.id,
    )
    session.add_all([opportunity, job, proposal])
    session.commit()

    response = client.delete(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    )

    assert response.status_code == 409
    assert bridge.deleted == []
    assert session.get(PageBlueprint, created["id"]) is not None


def test_new_version_rolls_back_registry_when_default_transfer_fails(
    client, auth_as, projects, monkeypatch, session
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    route = f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    assert client.post(f"{route}/set-default").status_code == 200

    def fail_default(*args, **kwargs):
        raise RuntimeError("default transfer failed")

    monkeypatch.setattr(page_blueprints, "set_default_blueprint", fail_default)
    with pytest.raises(RuntimeError, match="default transfer failed"):
        client.post(f"{route}/new-version")

    rows = session.scalars(select(PageBlueprint)).all()
    assert [row.id for row in rows] == [created["id"]]
    assert bridge.deleted == [902]


def test_new_version_refresh_failure_keeps_committed_snapshot(
    client,
    auth_as,
    projects,
    monkeypatch,
    session,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    original_refresh = session.refresh

    def fail_replacement_refresh(instance, *args, **kwargs):
        if (
            isinstance(instance, PageBlueprint)
            and instance.wordpress_snapshot_id == 902
        ):
            raise RuntimeError("replacement refresh failed")
        return original_refresh(instance, *args, **kwargs)

    monkeypatch.setattr(session, "refresh", fail_replacement_refresh)

    with pytest.raises(RuntimeError, match="replacement refresh failed"):
        client.post(
            f"/projects/{projects.member_project.id}/page-blueprints/"
            f"{created['id']}/new-version"
        )

    assert bridge.deleted == []
    session.expire_all()
    replacement = session.scalar(
        select(PageBlueprint).where(PageBlueprint.supersedes_id == created["id"])
    )
    assert replacement is not None
    assert replacement.wordpress_snapshot_id == 902
    assert replacement.state == "ready"


def test_new_version_locks_original_before_wordpress_capture(
    client, auth_as, projects, monkeypatch, session
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    original_lookup = page_blueprints._blueprint_or_404
    lock_requests: list[bool] = []

    def tracked_lookup(session, project_id, blueprint_id, *, for_update=False):
        lock_requests.append(for_update)
        return original_lookup(
            session,
            project_id,
            blueprint_id,
            for_update=for_update,
        )

    monkeypatch.setattr(page_blueprints, "_blueprint_or_404", tracked_lookup)

    response = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/"
        f"{created['id']}/new-version"
    )

    assert response.status_code == 201
    assert lock_requests == [True]


def test_delete_recovers_when_wordpress_clone_is_already_absent(
    client, auth_as, projects, monkeypatch
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    response = requests.Response()
    response.status_code = 404

    def already_absent(wordpress_blueprint_id: int):
        raise requests.HTTPError(response=response)

    bridge.delete_blueprint = already_absent
    deleted = client.delete(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    )
    assert deleted.status_code == 204


def test_delete_does_not_touch_remote_when_non_ready_commit_fails(
    client,
    auth_as,
    projects,
    monkeypatch,
    session,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)

    def fail_commit():
        raise RuntimeError("state commit failed")

    monkeypatch.setattr(session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="state commit failed"):
        client.delete(
            f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
        )

    assert bridge.deleted == []
    session.rollback()
    stored = session.get(PageBlueprint, created["id"])
    assert stored is not None
    assert stored.state == "ready"


def test_delete_db_failure_leaves_non_ready_row_for_safe_retry(
    client,
    auth_as,
    projects,
    monkeypatch,
    session,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    original_commit = session.commit

    def fail_row_delete_commit():
        if session.deleted:
            raise RuntimeError("row delete commit failed")
        original_commit()

    monkeypatch.setattr(session, "commit", fail_row_delete_commit)

    with pytest.raises(RuntimeError, match="row delete commit failed"):
        client.delete(
            f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
        )

    assert bridge.deleted == [901]
    session.rollback()
    session.expire_all()
    stored = session.get(PageBlueprint, created["id"])
    assert stored is not None
    assert stored.state == "invalid"
    assert stored.is_default_for_page_type is False

    monkeypatch.setattr(session, "commit", original_commit)
    retried = client.delete(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    )
    assert retried.status_code == 204
    assert bridge.deleted == [901, 901]
    assert session.get(PageBlueprint, created["id"]) is None


def test_remote_delete_failure_leaves_non_ready_row_for_retry(
    client,
    auth_as,
    projects,
    monkeypatch,
    session,
):
    auth_as(projects.owner)
    bridge = FakeBlueprintBridge()
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)
    created = create_blueprint(client, projects.member_project.id)
    response = requests.Response()
    response.status_code = 500

    def fail_remote_delete(wordpress_snapshot_id: int):
        raise requests.HTTPError(response=response)

    bridge.delete_blueprint = fail_remote_delete

    with pytest.raises(requests.HTTPError):
        client.delete(
            f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
        )

    session.expire_all()
    stored = session.get(PageBlueprint, created["id"])
    assert stored is not None
    assert stored.state == "invalid"
    assert stored.is_default_for_page_type is False
