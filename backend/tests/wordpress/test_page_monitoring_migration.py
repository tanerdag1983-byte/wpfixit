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
    database_name = f"wpfixpilot_page_monitoring_{uuid4().hex}"
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


def test_page_monitoring_migration_round_trip(migration_database_url: str) -> None:
    _upgrade("0023_keyword_sync_lifecycle")
    engine = create_engine(migration_database_url)

    _upgrade("head")

    with engine.connect() as connection:
        page_version_columns = {
            column["name"]
            for column in inspect(connection).get_columns("page_observed_versions")
        }
        snapshot_job_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "wordpress_snapshot_capture_jobs"
            )
        }
        proposal_columns = {
            column["name"]
            for column in inspect(connection).get_columns("page_package_proposals")
        }
        proposal_foreign_keys = inspect(connection).get_foreign_keys(
            "page_package_proposals"
        )
        page_version_foreign_keys = inspect(connection).get_foreign_keys(
            "page_observed_versions"
        )
        timeline_foreign_keys = inspect(connection).get_foreign_keys(
            "page_timeline_events"
        )
        draft_job_unique_constraints = inspect(connection).get_unique_constraints(
            "wordpress_draft_jobs"
        )
        page_version_unique_constraints = inspect(connection).get_unique_constraints(
            "page_observed_versions"
        )
        score_unique_constraints = inspect(connection).get_unique_constraints(
            "page_score_snapshots"
        )
        recommendation_columns = {
            column["name"]
            for column in inspect(connection).get_columns("page_recommendations")
        }
        recommendation_unique_constraints = inspect(connection).get_unique_constraints(
            "page_recommendations"
        )

    assert {
        "id",
        "project_id",
        "wordpress_page_id",
        "content_hash",
        "source",
        "snapshot_payload",
        "proposal_version_id",
        "draft_job_id",
        "observed_at",
        "published_at",
    } <= page_version_columns
    assert {
        "id",
        "project_id",
        "wordpress_page_id",
        "state",
        "claim_token",
        "claim_expires_at",
        "claimed_at",
        "terminal_claim_token_hash",
        "snapshot_result",
        "attempt_count",
        "completed_at",
        "failed_at",
        "cancelled_at",
    } <= snapshot_job_columns
    assert "source_wordpress_page_id" in proposal_columns
    assert any(
        foreign_key["constrained_columns"]
        == ["project_id", "source_wordpress_page_id"]
        and foreign_key["referred_table"] == "wordpress_pages"
        for foreign_key in proposal_foreign_keys
    )
    assert any(
        foreign_key["constrained_columns"] == ["project_id", "draft_job_id"]
        and foreign_key["referred_table"] == "wordpress_draft_jobs"
        for foreign_key in page_version_foreign_keys
    )
    assert any(
        foreign_key["constrained_columns"] == ["project_id", "page_version_id"]
        and foreign_key["referred_table"] == "page_observed_versions"
        for foreign_key in timeline_foreign_keys
    )
    assert any(
        constraint["column_names"] == ["project_id", "id"]
        for constraint in draft_job_unique_constraints
    )
    assert any(
        constraint["column_names"] == ["project_id", "id"]
        for constraint in page_version_unique_constraints
    )
    assert any(
        constraint["column_names"] == ["page_version_id"]
        for constraint in score_unique_constraints
    )
    assert "wordpress_page_id" in recommendation_columns
    assert any(
        constraint["column_names"] == ["wordpress_page_id", "fingerprint"]
        for constraint in recommendation_unique_constraints
    )

    _downgrade("0023_keyword_sync_lifecycle")

    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        proposal_columns = {
            column["name"]
            for column in inspect(connection).get_columns("page_package_proposals")
        }
        draft_job_unique_constraints = inspect(connection).get_unique_constraints(
            "wordpress_draft_jobs"
        )

    assert "page_observed_versions" not in tables
    assert "page_score_snapshots" not in tables
    assert "page_recommendations" not in tables
    assert "page_timeline_events" not in tables
    assert "wordpress_snapshot_capture_jobs" not in tables
    assert "source_wordpress_page_id" not in proposal_columns
    assert not any(
        constraint["column_names"] == ["project_id", "id"]
        for constraint in draft_job_unique_constraints
    )

    _upgrade("head")

    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert revision == "0024_page_monitoring"
    engine.dispose()
