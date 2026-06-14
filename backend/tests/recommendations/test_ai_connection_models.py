from collections.abc import Generator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, delete, event, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from alembic import command
from app.core.config import get_settings
from app.core.database import Base
from app.domains.projects.models import Organization, Project
from app.domains.recommendations import models as recommendation_models
from app.domains.recommendations.models import AiConnection, ProjectAiPolicy

LONG_LEGACY_PROVIDER = "provider-" + ("x" * 55)


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture
def projects(session: Session) -> SimpleNamespace:
    organization = Organization(id="org-member", name="Member Organization")
    member_project = Project(
        id="project-member",
        organization_id=organization.id,
        name="Member Site",
        domain="https://member.example",
    )
    session.add_all([organization, member_project])
    session.commit()
    return SimpleNamespace(
        organization=organization,
        member_project=member_project,
    )


@pytest.fixture
def migration_database_url(monkeypatch) -> Generator[str, None, None]:
    database_url = make_url(get_settings().database_url)
    database_name = f"wpfixpilot_test_{uuid4().hex}"
    admin_url = database_url.set(database="postgres")
    test_url = database_url.set(database=database_name)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    monkeypatch.setenv(
        "WP_FIXPILOT_DATABASE_URL",
        test_url.render_as_string(hide_password=False),
    )
    get_settings.cache_clear()
    try:
        yield test_url.render_as_string(hide_password=False)
    finally:
        get_settings.cache_clear()
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name "
                    "AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()


def _run_migration(revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", "alembic")
    command.upgrade(config, revision)


def _downgrade_migration(revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", "alembic")
    command.downgrade(config, revision)


def test_legacy_model_alias_is_removed() -> None:
    assert not hasattr(recommendation_models, "OrganizationAiSettings")


def test_organization_has_multiple_ai_connections_and_project_policy(
    session: Session,
    projects: SimpleNamespace,
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
            organization_id=projects.organization.id,
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
    projects: SimpleNamespace,
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
    projects: SimpleNamespace,
) -> None:
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
        organization_id=projects.organization.id,
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
    with pytest.raises(IntegrityError):
        session.commit()


def test_cross_organization_connection_policy_is_rejected(
    session: Session,
    projects: SimpleNamespace,
) -> None:
    other_organization = Organization(id="org-other", name="Other Organization")
    other_connection = AiConnection(
        id="ai-other",
        organization_id=other_organization.id,
        name="Other",
        provider="openai",
        base_url="https://api.openai.com/v1",
        encrypted_api_key="encrypted-other",
    )
    session.add_all([other_organization, other_connection])
    session.commit()

    session.add(
        ProjectAiPolicy(
            project_id=projects.member_project.id,
            organization_id=projects.organization.id,
            primary_connection_id=other_connection.id,
            primary_model="gpt-5.4-mini",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_organization_and_project_delete_cascade_owned_ai_records(
    session: Session,
    projects: SimpleNamespace,
) -> None:
    connection = AiConnection(
        id="ai-primary",
        organization_id=projects.organization.id,
        name="Primary",
        provider="openai",
        base_url="https://api.openai.com/v1",
        encrypted_api_key="encrypted-one",
    )
    policy = ProjectAiPolicy(
        project_id=projects.member_project.id,
        organization_id=projects.organization.id,
        primary_connection_id=connection.id,
        primary_model="gpt-5.4-mini",
    )
    session.add_all([connection, policy])
    session.commit()
    connection_id = connection.id

    session.execute(delete(Project).where(Project.id == projects.member_project.id))
    session.commit()

    assert session.get(ProjectAiPolicy, projects.member_project.id) is None
    assert session.get(AiConnection, connection_id) is not None

    session.execute(
        delete(Organization).where(Organization.id == projects.organization.id)
    )
    session.commit()

    assert session.get(AiConnection, connection_id) is None


def test_upgrade_and_downgrade_preserve_legacy_settings_exactly(
    migration_database_url: str,
) -> None:
    assert len(LONG_LEGACY_PROVIDER) == 64
    _run_migration("0010_ai_settings")
    engine = create_engine(migration_database_url)
    legacy_updated_at = datetime(2026, 1, 2, tzinfo=UTC)
    providers = {
        "org-openai": "openai",
        "org-compatible": "openai_compatible",
        "org-unknown": "custom",
        "org-long": LONG_LEGACY_PROVIDER,
    }
    with engine.begin() as connection:
        for organization_id, legacy_provider in providers.items():
            connection.execute(
                text(
                    "INSERT INTO organizations (id, name) "
                    "VALUES (:organization_id, :name)"
                ),
                {
                    "organization_id": organization_id,
                    "name": organization_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO organization_ai_settings "
                    "(organization_id, provider, base_url, model, "
                    "encrypted_api_key, updated_at) "
                    "VALUES (:organization_id, :provider, :base_url, :model, "
                    ":encrypted_api_key, :updated_at)"
                ),
                {
                    "organization_id": organization_id,
                    "provider": legacy_provider,
                    "base_url": f"https://{organization_id}.example/v1",
                    "model": f"{organization_id}-model",
                    "encrypted_api_key": f"{organization_id}-secret",
                    "updated_at": legacy_updated_at,
                },
            )

    _run_migration("head")

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT organization_id, name, provider, base_url, "
                "default_model, encrypted_api_key, created_at, updated_at "
                "FROM ai_connections ORDER BY organization_id"
            )
        ).mappings()
        migrated = {row["organization_id"]: row for row in rows}
        policy_count = connection.execute(
            text("SELECT count(*) FROM project_ai_policies")
        ).scalar_one()

    assert set(migrated) == set(providers)
    for organization_id, expected_provider in providers.items():
        row = migrated[organization_id]
        assert row["name"] == "Bestaande AI-koppeling"
        assert row["provider"] == expected_provider
        assert len(row["provider"]) <= 64
        assert row["base_url"] == f"https://{organization_id}.example/v1"
        assert row["default_model"] == f"{organization_id}-model"
        assert row["encrypted_api_key"] == f"{organization_id}-secret"
        assert row["created_at"] == legacy_updated_at
        assert row["updated_at"] == legacy_updated_at
    assert policy_count == 0

    indexes = {
        index["name"] for index in inspect(engine).get_indexes("project_ai_policies")
    }
    assert indexes == {
        "ix_project_ai_policies_fallback_connection_id",
        "ix_project_ai_policies_primary_connection_id",
    }

    _downgrade_migration("0010_ai_settings")

    with engine.connect() as connection:
        restored_rows = connection.execute(
            text(
                "SELECT organization_id, provider "
                "FROM organization_ai_settings ORDER BY organization_id"
            )
        ).all()

    assert dict(restored_rows) == providers
    engine.dispose()


def test_downgrade_selects_oldest_connection_by_created_at_then_id(
    migration_database_url: str,
) -> None:
    _run_migration("head")
    engine = create_engine(migration_database_url)
    oldest_created_at = datetime(2026, 1, 1, tzinfo=UTC)
    newer_created_at = datetime(2026, 1, 2, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations (id, name) "
                "VALUES ('org-downgrade', 'Downgrade Test')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO ai_connections "
                "(id, organization_id, name, provider, base_url, "
                "default_model, encrypted_api_key, created_at, updated_at) "
                "VALUES "
                "('ai-b', 'org-downgrade', 'B', 'anthropic', "
                "'https://b.example/v1', 'model-b', 'secret-b', "
                ":oldest_created_at, :newer_created_at), "
                "('ai-a', 'org-downgrade', 'A', 'openai', "
                "'https://a.example/v1', 'model-a', 'secret-a', "
                ":oldest_created_at, :oldest_created_at), "
                "('ai-newer', 'org-downgrade', 'Newer', 'custom', "
                "'https://newer.example/v1', 'model-newer', 'secret-newer', "
                ":newer_created_at, :newer_created_at)"
            ),
            {
                "oldest_created_at": oldest_created_at,
                "newer_created_at": newer_created_at,
            },
        )

    _downgrade_migration("0010_ai_settings")

    with engine.connect() as connection:
        restored = (
            connection.execute(
                text(
                    "SELECT provider, base_url, model, encrypted_api_key, updated_at "
                    "FROM organization_ai_settings "
                    "WHERE organization_id = 'org-downgrade'"
                )
            )
            .mappings()
            .one()
        )

    assert dict(restored) == {
        "provider": "openai",
        "base_url": "https://a.example/v1",
        "model": "model-a",
        "encrypted_api_key": "secret-a",
        "updated_at": oldest_created_at,
    }
    engine.dispose()
