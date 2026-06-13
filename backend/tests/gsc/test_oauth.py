from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.google.oauth import GoogleOAuthService, InvalidOAuthState
from app.domains.projects.models import Organization, Profile, Project


def test_oauth_state_is_one_time_and_bound_to_user() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        alice = Profile(id="alice", email="alice@example.com")
        bob = Profile(id="bob", email="bob@example.com")
        organization = Organization(id="org-1", name="Organization")
        project = Project(
            id="project-1",
            organization_id=organization.id,
            name="Project",
            domain="https://example.com",
        )
        session.add_all([alice, bob, organization, project])
        session.commit()
        service = GoogleOAuthService(
            session=session,
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="https://app.example.com/auth/google/callback",
            now=lambda: datetime.now(UTC),
        )
        authorization = service.create_authorization(alice.id, project.id)

        with pytest.raises(InvalidOAuthState):
            service.consume_state(authorization.state, bob.id)

        consumed = service.consume_state(authorization.state, alice.id)
        assert consumed.project_id == project.id
        assert consumed.expires_at > datetime.now(UTC) - timedelta(seconds=1)

        with pytest.raises(InvalidOAuthState):
            service.consume_state(authorization.state, alice.id)

