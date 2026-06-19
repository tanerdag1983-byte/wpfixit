from collections.abc import Generator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.projects.models import (
    Organization,
    OrganizationMember,
    Profile,
    Project,
)
from app.main import app


@dataclass
class ProjectFixtures:
    member: Profile
    outsider: Profile
    new_user: Profile
    organization: Organization
    member_project: Project
    other_project: Project


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
    member = Profile(id="user-member", email="member@example.com")
    outsider = Profile(id="user-outsider", email="outsider@example.com")
    new_user = Profile(id="user-new", email="new@example.com")
    organization = Organization(id="org-member", name="Member Organization")
    other_organization = Organization(id="org-other", name="Other Organization")
    member_project = Project(
        id="project-member",
        organization_id=organization.id,
        name="Member Site",
        domain="https://member.example",
    )
    other_project = Project(
        id="project-other",
        organization_id=other_organization.id,
        name="Other Site",
        domain="https://other.example",
    )
    session.add_all(
        [
            member,
            outsider,
            new_user,
            organization,
            other_organization,
            OrganizationMember(
                organization_id=organization.id,
                profile_id=member.id,
                role="owner",
            ),
            member_project,
            other_project,
        ]
    )
    session.commit()
    return ProjectFixtures(
        member=member,
        outsider=outsider,
        new_user=new_user,
        organization=organization,
        member_project=member_project,
        other_project=other_project,
    )


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
