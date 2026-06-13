import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.recommendations.models import AiConnection, ProjectAiPolicy
from tests.projects.conftest import ProjectFixtures


def test_organization_has_multiple_ai_connections_and_project_policy(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    primary = AiConnection(
        id="ai-primary",
        organization_id=projects.organization.id,
        name="OpenAI productie",
        provider="openai",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.4-mini",
        encrypted_api_key="encrypted-one",
    )
    fallback = AiConnection(
        id="ai-fallback",
        organization_id=projects.organization.id,
        name="Claude fallback",
        provider="anthropic",
        base_url="https://api.anthropic.com/v1",
        encrypted_api_key="encrypted-two",
        enabled=False,
    )
    session.add_all([primary, fallback])
    session.add(
        ProjectAiPolicy(
            project_id=projects.member_project.id,
            primary_connection_id=primary.id,
            primary_model="gpt-5.4-mini",
            fallback_connection_id=fallback.id,
            fallback_model="claude-sonnet-4-5",
        )
    )
    session.commit()

    connections = session.scalars(
        select(AiConnection).where(
            AiConnection.organization_id == projects.organization.id
        )
    ).all()
    policy = session.get(ProjectAiPolicy, projects.member_project.id)

    assert {item.provider for item in connections} == {"openai", "anthropic"}
    assert primary.enabled is True
    assert fallback.enabled is False
    assert primary.created_at is not None
    assert primary.updated_at is not None
    assert policy is not None
    assert policy.primary_connection_id == primary.id
    assert policy.fallback_connection_id == fallback.id
    assert policy.updated_at is not None


def test_connection_name_is_unique_per_organization(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    session.add_all(
        [
            AiConnection(
                id="ai-first",
                organization_id=projects.organization.id,
                name="Productie",
                provider="openai",
                base_url="https://api.openai.com/v1",
                encrypted_api_key="encrypted-one",
            ),
            AiConnection(
                id="ai-second",
                organization_id=projects.organization.id,
                name="Productie",
                provider="anthropic",
                base_url="https://api.anthropic.com/v1",
                encrypted_api_key="encrypted-two",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_policy_connection_delete_rules(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    session.execute(text("PRAGMA foreign_keys=ON"))
    primary = AiConnection(
        id="ai-primary",
        organization_id=projects.organization.id,
        name="Primary",
        provider="openai",
        base_url="https://api.openai.com/v1",
        encrypted_api_key="encrypted-one",
    )
    fallback = AiConnection(
        id="ai-fallback",
        organization_id=projects.organization.id,
        name="Fallback",
        provider="anthropic",
        base_url="https://api.anthropic.com/v1",
        encrypted_api_key="encrypted-two",
    )
    policy = ProjectAiPolicy(
        project_id=projects.member_project.id,
        primary_connection_id=primary.id,
        primary_model="gpt-5.4-mini",
        fallback_connection_id=fallback.id,
        fallback_model="claude-sonnet-4-5",
    )
    session.add_all([primary, fallback, policy])
    session.commit()

    session.delete(primary)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.delete(fallback)
    session.commit()
    session.refresh(policy)

    assert policy.fallback_connection_id is None
