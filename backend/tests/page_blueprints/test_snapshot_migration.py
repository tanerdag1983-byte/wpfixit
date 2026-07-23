from collections.abc import Generator
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import get_settings


@pytest.fixture
def migration_database_url(monkeypatch) -> Generator[str, None, None]:
    database_url = make_url(get_settings().database_url)
    database_name = f"wpfixpilot_snapshot_{uuid4().hex}"
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


def _insert_legacy_blueprint(connection) -> None:
    connection.execute(
        text(
            "INSERT INTO organizations (id, name) VALUES "
            "('org-snapshot', 'Snapshot organization')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO projects (id, organization_id, name, domain) VALUES "
            "('project-snapshot', 'org-snapshot', 'Snapshot site', "
            "'https://snapshot.example')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO wordpress_pages "
            "(id, project_id, wordpress_object_id, post_type, status, title, slug, "
            "url) "
            "VALUES ('source-snapshot', 'project-snapshot', 5001, 'page', "
            "'publish', 'Source', 'source', 'https://snapshot.example/source')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO page_blueprints "
            "(id, project_id, name, page_type, source_wordpress_page_id, "
            "wordpress_blueprint_id, builder, seo_plugin, version, structure_hash, "
            "content_schema, state, is_default_for_page_type) "
            "VALUES ('legacy-snapshot', 'project-snapshot', 'Legacy', 'service', "
            "'source-snapshot', 6001, 'acf', 'yoast', 1, 'legacy-hash', "
            "CAST(:content_schema AS json), 'ready', false)"
        ),
        {"content_schema": '{"schema_version":"blueprint-v1","blocks":[]}'},
    )


def test_snapshot_migration_upgrades_and_downgrades_with_legacy_rows(
    migration_database_url: str,
) -> None:
    _upgrade("0019_outbound_wp_draft_jobs")
    engine = create_engine(migration_database_url)
    with engine.begin() as connection:
        _insert_legacy_blueprint(connection)

    _upgrade("0020_template_snapshots")

    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("page_blueprints")
        }
        legacy_identity = connection.execute(
            text(
                "SELECT wordpress_snapshot_id, snapshot_version, schema_version, "
                "adapter_version, capture_state, migration_state, verified_at "
                "FROM page_blueprints WHERE id = 'legacy-snapshot'"
            )
        ).one()

    assert {
        "wordpress_snapshot_id",
        "snapshot_version",
        "schema_version",
        "adapter_version",
        "capture_state",
        "migration_state",
        "verified_at",
    } <= columns
    assert legacy_identity == (None, None, None, None, None, None, None)

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO page_blueprints "
                    "(id, project_id, name, page_type, source_wordpress_page_id, "
                    "wordpress_blueprint_id, builder, seo_plugin, version, "
                    "structure_hash, content_schema, state, is_default_for_page_type, "
                    "wordpress_snapshot_id, snapshot_version, schema_version, "
                    "adapter_version, capture_state, migration_state, verified_at) "
                    "VALUES ('partial-snapshot', 'project-snapshot', 'Partial', "
                    "'landing', 'source-snapshot', 6002, 'acf', 'yoast', 1, "
                    "'partial-hash', CAST(:content_schema AS json), 'ready', false, "
                    "7001, 1, NULL, 'acf-v1', 'ready', 'native', now())"
                ),
                {"content_schema": '{"schema_version":"blueprint-v1","blocks":[]}'},
            )

    _downgrade("0019_outbound_wp_draft_jobs")

    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("page_blueprints")
        }
        legacy_id = connection.execute(
            text("SELECT id FROM page_blueprints WHERE id = 'legacy-snapshot'")
        ).scalar_one()

    assert "wordpress_snapshot_id" not in columns
    assert legacy_id == "legacy-snapshot"
    engine.dispose()
