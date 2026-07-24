import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.page_packages.models import PageProposalStage
from app.domains.page_packages.stages import (
    MAX_STAGE_ERRORS_BYTES,
    MAX_STAGE_RESULT_BYTES,
    STALE_RUNNING_STAGE_SECONDS,
    attention_stage,
    begin_stage,
    complete_stage,
    fail_stage,
    reclaim_stale_running_stage,
    retry_stage,
)
from tests.page_packages.test_proposal_versions import page_proposal_factory
from tests.recommendations.conftest import ProjectFixtures

POSTGRES_TEST_URL = os.getenv("WP_FIXPILOT_POSTGRES_TEST_URL")


def _stage(
    session: Session,
    proposal_id: str,
    name: str,
    *,
    state: str = "pending",
) -> PageProposalStage:
    item = PageProposalStage(
        proposal_version_id=proposal_id,
        name=name,
        state=state,
        result={},
        errors={},
    )
    session.add(item)
    session.commit()
    return item


@pytest.fixture
def proposal(session: Session, projects: ProjectFixtures):
    return page_proposal_factory(
        session,
        projects,
        proposal_id="proposal-stages",
        state="generating",
        proposal_group_id="proposal-stages",
    )


def test_stage_identity_is_unique_and_cascades_with_proposal(
    session: Session,
    proposal,
) -> None:
    _stage(session, proposal.id, "template")
    session.add(
        PageProposalStage(
            proposal_version_id=proposal.id,
            name="template",
            state="pending",
            result={},
            errors={},
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.delete(proposal)
    session.commit()
    assert session.scalar(
        select(PageProposalStage).where(
            PageProposalStage.proposal_version_id == proposal.id
        )
    ) is None


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"name": "draft", "state": "pending"}, "name"),
        ({"name": "text", "state": "cancelled"}, "state"),
        ({"name": "text", "state": "pending", "retry_count": -1}, "retry"),
    ],
)
def test_stage_database_constraints_reject_invalid_values(
    session: Session,
    proposal,
    values: dict,
    message: str,
) -> None:
    session.add(
        PageProposalStage(
            proposal_version_id=proposal.id,
            result={},
            errors={},
            **values,
        )
    )

    with pytest.raises(IntegrityError, match=message):
        session.commit()
    session.rollback()


@pytest.mark.parametrize(
    ("field_name", "limit"),
    [
        ("result", MAX_STAGE_RESULT_BYTES),
        ("errors", MAX_STAGE_ERRORS_BYTES),
    ],
)
def test_stage_json_bounds_are_enforced_by_the_database(
    session: Session,
    proposal,
    field_name: str,
    limit: int,
) -> None:
    values = {"result": {}, "errors": {}}
    values[field_name] = {"value": "x" * limit}
    session.add(
        PageProposalStage(
            proposal_version_id=proposal.id,
            name="text",
            state="pending",
            **values,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_stage_transitions_record_timestamps_and_retry_metadata(
    session: Session,
    proposal,
) -> None:
    _stage(session, proposal.id, "validation")

    running = begin_stage(session, proposal.id, "validation")
    assert running.state == "running"
    assert running.started_at is not None
    assert running.completed_at is None

    attention = attention_stage(
        session,
        proposal.id,
        "validation",
        errors={"document:title": "required"},
        attempt_token=running.attempt_token,
    )
    assert attention.state == "attention"
    assert attention.completed_at is not None
    assert attention.errors == {"document:title": "required"}

    retried = retry_stage(session, proposal.id, "validation")
    assert retried.state == "running"
    assert retried.retry_count == 1
    assert retried.last_retried_at is not None
    assert retried.completed_at is None
    assert retried.errors == {}

    completed = complete_stage(
        session,
        proposal.id,
        "validation",
        result={"replacements": {"document:title": "Nieuwe titel"}},
        attempt_token=retried.attempt_token,
    )
    assert completed.state == "ready"
    assert completed.completed_at is not None


def test_fresh_running_stage_cannot_be_reclaimed(
    session: Session,
    proposal,
) -> None:
    item = _stage(session, proposal.id, "text", state="running")
    now = datetime.now(UTC)
    item.started_at = now - timedelta(seconds=STALE_RUNNING_STAGE_SECONDS - 1)
    session.commit()

    with pytest.raises(ValueError, match="stage_in_progress"):
        reclaim_stale_running_stage(session, proposal.id, "text", now=now)

    session.refresh(item)
    assert item.state == "running"
    assert item.retry_count == 0
    assert item.started_at.replace(tzinfo=UTC) == now - timedelta(
        seconds=STALE_RUNNING_STAGE_SECONDS - 1
    )


def test_stale_running_stage_is_reclaimed_with_a_new_lease(
    session: Session,
    proposal,
) -> None:
    item = _stage(session, proposal.id, "text", state="running")
    now = datetime.now(UTC)
    item.started_at = now - timedelta(seconds=STALE_RUNNING_STAGE_SECONDS + 1)
    item.result = {"partial": "discard"}
    item.errors = {"message": "interrupted"}
    session.commit()

    reclaimed = reclaim_stale_running_stage(session, proposal.id, "text", now=now)

    assert reclaimed.state == "running"
    assert reclaimed.retry_count == 1
    assert reclaimed.started_at == now
    assert reclaimed.last_retried_at == now
    assert reclaimed.completed_at is None
    assert reclaimed.result == {}
    assert reclaimed.errors == {}


def test_reclaimed_stage_rejects_late_success_from_previous_attempt(
    session: Session,
    proposal,
) -> None:
    item = _stage(session, proposal.id, "text")
    previous = begin_stage(session, proposal.id, "text")
    previous_token = previous.attempt_token
    previous.started_at = datetime.now(UTC) - timedelta(
        seconds=STALE_RUNNING_STAGE_SECONDS + 1
    )
    session.commit()

    current = reclaim_stale_running_stage(session, proposal.id, "text")

    with pytest.raises(ValueError, match="stale_stage_attempt"):
        complete_stage(
            session,
            proposal.id,
            "text",
            result={"winner": "previous"},
            attempt_token=previous_token,
        )

    session.refresh(item)
    assert item.state == "running"
    assert item.attempt_token == current.attempt_token
    assert item.result == {}

    complete_stage(
        session,
        proposal.id,
        "text",
        result={"winner": "current"},
        attempt_token=current.attempt_token,
    )
    assert item.state == "ready"
    assert item.result == {"winner": "current"}


def test_reclaimed_stage_rejects_late_failure_from_previous_attempt(
    session: Session,
    proposal,
) -> None:
    item = _stage(session, proposal.id, "validation")
    previous = begin_stage(session, proposal.id, "validation")
    previous_token = previous.attempt_token
    previous.started_at = datetime.now(UTC) - timedelta(
        seconds=STALE_RUNNING_STAGE_SECONDS + 1
    )
    session.commit()

    current = reclaim_stale_running_stage(session, proposal.id, "validation")

    with pytest.raises(ValueError, match="stale_stage_attempt"):
        fail_stage(
            session,
            proposal.id,
            "validation",
            errors={"message": "late failure"},
            attempt_token=previous_token,
        )

    session.refresh(item)
    assert item.state == "running"
    assert item.attempt_token == current.attempt_token
    assert item.errors == {}


def test_text_success_survives_validation_attention(
    session: Session,
    proposal,
) -> None:
    text_stage = _stage(session, proposal.id, "text", state="running")
    validation_stage = _stage(session, proposal.id, "validation", state="running")

    complete_stage(
        session,
        proposal.id,
        "text",
        result={"text_replacements": {"a": {"value": "b"}}},
        attempt_token=text_stage.attempt_token,
    )
    attention_stage(
        session,
        proposal.id,
        "validation",
        errors={"acf:hero:label": "unsafe_html"},
        attempt_token=validation_stage.attempt_token,
    )
    session.commit()
    session.expire_all()

    text = session.scalar(
        select(PageProposalStage).where(
            PageProposalStage.proposal_version_id == proposal.id,
            PageProposalStage.name == "text",
        )
    )
    assert text is not None
    assert text.state == "ready"
    assert text.result["text_replacements"] == {"a": {"value": "b"}}


def test_terminal_transition_race_has_one_winner_and_locks_the_row(
    session: Session,
    proposal,
    monkeypatch,
) -> None:
    item = _stage(session, proposal.id, "text", state="running")
    statements = []
    original_scalar = session.scalar

    def capture_scalar(statement, *args, **kwargs):
        statements.append(statement)
        return original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(session, "scalar", capture_scalar)
    complete_stage(
        session,
        proposal.id,
        "text",
        result={"ok": True},
        attempt_token=item.attempt_token,
    )

    with pytest.raises(ValueError, match="invalid_stage_transition"):
        fail_stage(
            session,
            proposal.id,
            "text",
            errors={"provider": "late failure"},
            attempt_token=item.attempt_token,
        )

    assert any(statement._for_update_arg is not None for statement in statements)


def test_helpers_reject_oversized_json_before_flush(
    session: Session,
    proposal,
) -> None:
    item = _stage(session, proposal.id, "text", state="running")
    oversized = {"value": "x" * MAX_STAGE_RESULT_BYTES}
    assert len(json.dumps(oversized).encode()) > MAX_STAGE_RESULT_BYTES

    with pytest.raises(ValueError, match="stage_result_too_large"):
        complete_stage(
            session,
            proposal.id,
            "text",
            result=oversized,
            attempt_token=item.attempt_token,
        )


def test_stage_migration_round_trip_on_sqlite(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'stages.db'}")
    metadata = MetaData()
    Table(
        "page_package_proposals",
        metadata,
        Column("id", String(64), primary_key=True),
    )
    metadata.create_all(engine)
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "0021_resumable_proposal_stages.py"
    )
    spec = spec_from_file_location("task5_stage_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert "page_proposal_stages" in inspect(connection).get_table_names()
        attempt_token = next(
            column
            for column in inspect(connection).get_columns("page_proposal_stages")
            if column["name"] == "attempt_token"
        )
        assert attempt_token["nullable"] is False
        migration.downgrade()
        assert "page_proposal_stages" not in inspect(connection).get_table_names()

    engine.dispose()


@pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="WP_FIXPILOT_POSTGRES_TEST_URL is required",
)
def test_concurrent_terminal_stage_transitions_have_one_winner_postgres() -> None:
    schema = f"task5_stage_{uuid4().hex}"
    admin_engine = create_engine(POSTGRES_TEST_URL)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".page_package_proposals '
                "(id VARCHAR(64) PRIMARY KEY)"
            )
        )
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".page_proposal_stages ('
                "id VARCHAR(64) PRIMARY KEY, "
                "proposal_version_id VARCHAR(64) NOT NULL REFERENCES "
                f'"{schema}".page_package_proposals(id) ON DELETE CASCADE, '
                "name VARCHAR(24) NOT NULL, state VARCHAR(24) NOT NULL, "
                "result JSON NOT NULL, errors JSON NOT NULL, "
                "retry_count INTEGER NOT NULL DEFAULT 0, "
                "attempt_token VARCHAR(64) NOT NULL, "
                "started_at TIMESTAMPTZ NULL, completed_at TIMESTAMPTZ NULL, "
                "last_retried_at TIMESTAMPTZ NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "UNIQUE (proposal_version_id, name))"
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".page_package_proposals (id) '
                "VALUES ('proposal-race')"
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".page_proposal_stages '
                "(id, proposal_version_id, name, state, result, errors, "
                "attempt_token) "
                "VALUES ('stage-race', 'proposal-race', 'text', 'running', "
                "'{}', '{}', 'attempt-race')"
            )
        )

    engine = create_engine(
        POSTGRES_TEST_URL,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_size=2,
        max_overflow=0,
    )
    barrier = Barrier(2)

    def finish(target: str) -> str:
        with Session(engine) as current_session:
            barrier.wait(timeout=10)
            try:
                if target == "ready":
                    complete_stage(
                        current_session,
                        "proposal-race",
                        "text",
                        result={"winner": target},
                        attempt_token="attempt-race",
                    )
                else:
                    fail_stage(
                        current_session,
                        "proposal-race",
                        "text",
                        errors={"winner": target},
                        attempt_token="attempt-race",
                    )
                current_session.commit()
                return target
            except ValueError:
                current_session.rollback()
                return "rejected"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=10)
                for future in [
                    executor.submit(finish, "ready"),
                    executor.submit(finish, "failed"),
                ]
            ]
        assert results.count("rejected") == 1
        assert set(results) & {"ready", "failed"}
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="WP_FIXPILOT_POSTGRES_TEST_URL is required",
)
def test_concurrent_stale_stage_reclaims_have_one_winner_postgres() -> None:
    schema = f"task5_reclaim_{uuid4().hex}"
    admin_engine = create_engine(POSTGRES_TEST_URL)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".page_package_proposals '
                "(id VARCHAR(64) PRIMARY KEY)"
            )
        )
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".page_proposal_stages ('
                "id VARCHAR(64) PRIMARY KEY, "
                "proposal_version_id VARCHAR(64) NOT NULL REFERENCES "
                f'"{schema}".page_package_proposals(id) ON DELETE CASCADE, '
                "name VARCHAR(24) NOT NULL, state VARCHAR(24) NOT NULL, "
                "result JSON NOT NULL, errors JSON NOT NULL, "
                "retry_count INTEGER NOT NULL DEFAULT 0, "
                "attempt_token VARCHAR(64) NOT NULL, "
                "started_at TIMESTAMPTZ NULL, completed_at TIMESTAMPTZ NULL, "
                "last_retried_at TIMESTAMPTZ NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "UNIQUE (proposal_version_id, name))"
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".page_package_proposals (id) '
                "VALUES ('proposal-reclaim')"
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".page_proposal_stages '
                "(id, proposal_version_id, name, state, result, errors, "
                "attempt_token, started_at) "
                "VALUES ('stage-reclaim', 'proposal-reclaim', 'text', 'running', "
                "'{}', '{}', 'attempt-reclaim', "
                "CURRENT_TIMESTAMP - INTERVAL '10 minutes')"
            )
        )

    engine = create_engine(
        POSTGRES_TEST_URL,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_size=2,
        max_overflow=0,
    )
    barrier = Barrier(2)

    def reclaim() -> str:
        with Session(engine) as current_session:
            barrier.wait(timeout=10)
            try:
                reclaim_stale_running_stage(
                    current_session,
                    "proposal-reclaim",
                    "text",
                )
                current_session.commit()
                return "reclaimed"
            except ValueError as error:
                current_session.rollback()
                return str(error)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=10)
                for future in [
                    executor.submit(reclaim),
                    executor.submit(reclaim),
                ]
            ]
        assert results.count("reclaimed") == 1
        assert results.count("stage_in_progress") == 1
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()
