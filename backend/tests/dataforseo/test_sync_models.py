import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import (
    KeywordOpportunity,
    KeywordOpportunitySyncRun,
    KeywordOpportunitySyncState,
)
from tests.recommendations.conftest import ProjectFixtures


def keyword_opportunity(
    projects: ProjectFixtures,
    *,
    first_seen_run_id: str | None = None,
    last_seen_run_id: str | None = None,
) -> KeywordOpportunity:
    return KeywordOpportunity(
        id="opportunity-sync",
        project_id=projects.member_project.id,
        keyword="transmissie revisie",
        location_code=2528,
        language_code="nl",
        source="dataforseo",
        raw_payload={},
        first_seen_run_id=first_seen_run_id,
        last_seen_run_id=last_seen_run_id,
    )


def test_keyword_identity_survives_multiple_sync_runs(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    first = KeywordOpportunitySyncRun.started(
        projects.member_project.id, "seed-a", 0, 50
    )
    second = KeywordOpportunitySyncRun.started(
        projects.member_project.id, "seed-a", 50, 50
    )
    opportunity = keyword_opportunity(
        projects,
        first_seen_run_id=first.id,
        last_seen_run_id=second.id,
    )
    session.add_all([first, second, opportunity])
    session.commit()

    assert opportunity.first_seen_run_id == first.id
    assert opportunity.last_seen_run_id == second.id


def test_sync_state_rejects_negative_offset(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    session.add(
        KeywordOpportunitySyncState(
            project_id=projects.member_project.id,
            seed_fingerprint="seed-a",
            next_offset=-1,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("offset", -1),
        ("limit", -1),
        ("provider_count", -1),
        ("accepted_count", -1),
        ("created_count", -1),
        ("updated_count", -1),
        ("rejected_count", -1),
    ],
)
def test_sync_run_rejects_negative_values(
    session: Session,
    projects: ProjectFixtures,
    field: str,
    value: int,
) -> None:
    run = KeywordOpportunitySyncRun.started(
        projects.member_project.id, "seed-a", 0, 50
    )
    setattr(run, field, value)
    session.add(run)

    with pytest.raises(IntegrityError):
        session.commit()


def test_sync_run_rejects_unknown_state(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    run = KeywordOpportunitySyncRun.started(
        projects.member_project.id, "seed-a", 0, 50
    )
    run.state = "unknown"
    session.add(run)

    with pytest.raises(IntegrityError):
        session.commit()


def test_sync_run_delete_clears_nullable_lineage(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    run = KeywordOpportunitySyncRun.started(
        projects.member_project.id, "seed-a", 0, 50
    )
    opportunity = keyword_opportunity(
        projects,
        first_seen_run_id=run.id,
        last_seen_run_id=run.id,
    )
    state = KeywordOpportunitySyncState(
        project_id=projects.member_project.id,
        seed_fingerprint="seed-a",
        last_successful_run_id=run.id,
    )
    session.add_all([run, opportunity, state])
    session.commit()

    session.execute(
        delete(KeywordOpportunitySyncRun).where(KeywordOpportunitySyncRun.id == run.id)
    )
    session.commit()
    session.refresh(opportunity)
    session.refresh(state)

    assert opportunity.first_seen_run_id is None
    assert opportunity.last_seen_run_id is None
    assert state.last_successful_run_id is None
