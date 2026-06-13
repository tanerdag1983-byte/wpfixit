from fastapi.testclient import TestClient

from .conftest import ProjectFixtures


def test_member_can_list_only_organization_projects(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)

    response = client.get("/projects")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        projects.member_project.id
    ]


def test_non_member_cannot_read_project(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.outsider)

    response = client.get(f"/projects/{projects.member_project.id}")

    assert response.status_code == 404


def test_owner_can_create_and_soft_delete_project(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    create_response = client.post(
        "/projects",
        json={
            "organization_id": projects.organization.id,
            "name": "New Site",
            "domain": "https://new.example/",
        },
    )

    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    delete_response = client.delete(f"/projects/{project_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/projects/{project_id}").status_code == 404
