from collections.abc import Generator
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import get_settings


@pytest.fixture
def migration_database_url(monkeypatch) -> Generator[str, None, None]:
    database_url = make_url(get_settings().database_url)
    database_name = f"wpfixpilot_keyword_sync_{uuid4().hex}"
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


def _upgrade(revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", "alembic")
    command.upgrade(config, revision)


def _downgrade(revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", "alembic")
    command.downgrade(config, revision)


def test_keyword_sync_migration_round_trips_existing_opportunities(
    migration_database_url: str,
) -> None:
    _upgrade("0022_snapshot_draft_jobs")
    engine = create_engine(migration_database_url)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO organizations (id, name) VALUES ('org-sync', 'Sync')")
        )
        connection.execute(
            text(
                "INSERT INTO projects (id, organization_id, name, domain) VALUES "
                "('project-sync', 'org-sync', 'Sync site', 'https://sync.example')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO keyword_opportunities "
                "(id, project_id, keyword, location_code, language_code, raw_payload) "
                "VALUES ('opportunity-sync', 'project-sync', 'transmissie revisie', "
                "2528, 'nl', CAST('{}' AS json))"
            )
        )

    _upgrade("0023_keyword_sync_lifecycle")

    with engine.connect() as connection:
        opportunity_columns = {
            column["name"]
            for column in inspect(connection).get_columns("keyword_opportunities")
        }
        state_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "keyword_opportunity_sync_states"
            )
        }
        run_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "keyword_opportunity_sync_runs"
            )
        }
        timestamps = connection.execute(
            text(
                "SELECT discovered_at, last_seen_at FROM keyword_opportunities "
                "WHERE id = 'opportunity-sync'"
            )
        ).one()

    assert {
        "first_seen_run_id",
        "last_seen_run_id",
        "last_seen_at",
        "dismissed_at",
    } <= opportunity_columns
    assert {
        "project_id",
        "seed_fingerprint",
        "next_offset",
        "exhausted",
        "last_successful_run_id",
        "last_synced_at",
        "last_error",
    } <= state_columns
    assert {
        "id",
        "project_id",
        "seed_fingerprint",
        "offset",
        "limit",
        "state",
        "provider_count",
        "accepted_count",
        "created_count",
        "updated_count",
        "rejected_count",
        "started_at",
        "completed_at",
        "error_message",
    } <= run_columns
    assert timestamps[0] == timestamps[1]

    _downgrade("0022_snapshot_draft_jobs")

    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("keyword_opportunities")
        }
        opportunity_id = connection.execute(
            text("SELECT id FROM keyword_opportunities WHERE id = 'opportunity-sync'")
        ).scalar_one()

    assert "last_seen_at" not in columns
    assert opportunity_id == "opportunity-sync"
    engine.dispose()
