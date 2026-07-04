from collections.abc import Generator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.audits import models as audit_models  # noqa: F401
from app.domains.projects.models import (
    Organization,
    OrganizationMember,
    Profile,
    Project,
)
from app.domains.wordpress.models import WordPressPage
from app.main import app


@dataclass
class ProjectFixtures:
    owner: Profile
    viewer: Profile
    outsider: Profile
    organization: Organization
    member_project: Project


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture
def projects(session: Session) -> ProjectFixtures:
    owner = Profile(id="blueprint-owner", email="owner@example.com")
    viewer = Profile(id="blueprint-viewer", email="viewer@example.com")
    outsider = Profile(id="blueprint-outsider", email="outsider@example.com")
    organization = Organization(id="blueprint-org", name="Blueprint Organization")
    project = Project(
        id="blueprint-project",
        organization_id=organization.id,
        name="Blueprint Site",
        domain="https://blueprint.example",
    )
    source = WordPressPage(
        id="source-page",
        project_id=project.id,
        wordpress_object_id=19,
        post_type="page",
        status="publish",
        title="Reference page",
        slug="reference-page",
        url="https://blueprint.example/reference-page/",
    )
    session.add_all(
        [
            owner,
            viewer,
            outsider,
            organization,
            OrganizationMember(
                organization_id=organization.id,
                profile_id=owner.id,
                role="owner",
            ),
            OrganizationMember(
                organization_id=organization.id,
                profile_id=viewer.id,
                role="viewer",
            ),
            project,
            source,
        ]
    )
    session.commit()
    return ProjectFixtures(owner, viewer, outsider, organization, project)


@pytest.fixture
def auth_as():
    def authenticate(profile: Profile) -> None:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=profile.id,
            email=profile.email,
        )

    yield authenticate
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client(session: Session) -> Generator[TestClient, None, None]:
    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_session, None)
