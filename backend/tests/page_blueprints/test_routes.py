import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import page_blueprints
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_packages.models import PagePackageProposal


def valid_schema(*, role: str = "hero") -> dict:
    return {
        "schema_version": "blueprint-v1",
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
        "wordpress_blueprint_id": wordpress_id,
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
        return self.captures.pop(0)

    def blueprint(self, wordpress_blueprint_id: int) -> dict:
        return self.inspections.get(
            wordpress_blueprint_id,
            captured_blueprint(wordpress_id=wordpress_blueprint_id),
        )

    def delete_blueprint(self, wordpress_blueprint_id: int) -> dict:
        self.deleted.append(wordpress_blueprint_id)
        return {"deleted": True}


def create_blueprint(client: TestClient, project_id: str) -> dict:
    response = client.post(
        f"/projects/{project_id}/page-blueprints",
        json={
            "name": "Dienstpagina",
            "page_type": "service",
            "source_wordpress_page_id": "source-page",
            "builder": "acf",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


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
            "builder": "acf",
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
        "builder": "acf",
        "version": 2,
    }


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
            "builder": "acf",
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
            "page_type": "brand",
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
        ({"version": 2}, "stale"),
        ({"builder": "elementor"}, "stale"),
        ({"seo_plugin": "rank_math"}, "stale"),
        ({"source_page_id": 77}, "stale"),
        ({"wordpress_blueprint_id": 999}, "stale"),
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

    response = client.delete(
        f"/projects/{projects.member_project.id}/page-blueprints/{created['id']}"
    )
    assert response.status_code == 204, response.text
    assert bridge.deleted == [901]


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
            "builder": "acf",
        },
    )

    assert response.status_code == 502
    assert bridge.deleted == [901]
    assert session.scalar(select(PageBlueprint)) is None


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
