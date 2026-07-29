from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import (
    KeywordOpportunity,
    KeywordOpportunitySyncRun,
    KeywordOpportunitySyncState,
)
from app.domains.dataforseo.service import (
    seed_fingerprint,
    sync_keyword_opportunity_window,
)
from app.domains.recommendations.models import CompanyProfile
from tests.recommendations.conftest import ProjectFixtures


class StubProvider:
    def __init__(self, windows: list[list[dict]]) -> None:
        self.windows = windows
        self.calls: list[tuple[list[str], int, int]] = []

    def keyword_ideas(
        self,
        seeds: list[str],
        *,
        limit: int,
        offset: int,
    ) -> list[dict]:
        self.calls.append((seeds, limit, offset))
        return self.windows[len(self.calls) - 1]


class FailingProvider:
    def keyword_ideas(
        self,
        seeds: list[str],
        *,
        limit: int,
        offset: int,
    ) -> list[dict]:
        raise RuntimeError("Provider rejected secret-password")


def _add_profile(
    session: Session,
    projects: ProjectFixtures,
    services: list[str] | None = None,
) -> CompanyProfile:
    profile = CompanyProfile(
        project_id=projects.member_project.id,
        company_name="Transmissiehuis",
        description="Transmissiespecialist in Schiedam.",
        audience="Autobezitters met schakelklachten.",
        services=services or ["transmissie advies"],
        tone_of_voice="Duidelijk",
        custom_prompt="",
    )
    session.add(profile)
    session.commit()
    return profile


def _row(keyword: str, *, search_volume: int = 10) -> dict:
    return {
        "keyword": keyword,
        "location_code": 2528,
        "language_code": "nl",
        "search_volume": search_volume,
    }


def _full_window(prefix: str) -> list[dict]:
    return [_row(f"transmissie {prefix} {index}") for index in range(50)]


def _keywords(session: Session, project_id: str) -> set[str]:
    return set(
        session.scalars(
            select(KeywordOpportunity.keyword).where(
                KeywordOpportunity.project_id == project_id
            )
        ).all()
    )


def test_seed_fingerprint_normalizes_case_whitespace_and_order() -> None:
    assert seed_fingerprint(["  DSG   Revisie ", "Koppeling vervangen"]) == (
        seed_fingerprint(["koppeling VERVANGEN", "dsg revisie"])
    )
    assert seed_fingerprint(["dsg revisie"]) != seed_fingerprint(
        ["koppeling vervangen"]
    )


def test_successive_syncs_keep_old_rows_and_advance_offset(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    _add_profile(session, projects)
    provider = StubProvider([_full_window("eerste"), _full_window("tweede")])

    first = sync_keyword_opportunity_window(
        session, projects.member_project, provider
    )
    second = sync_keyword_opportunity_window(
        session, projects.member_project, provider
    )

    assert (first.offset, second.offset) == (0, 50)
    assert (first.next_offset, second.next_offset) == (50, 100)
    assert len(_keywords(session, projects.member_project.id)) == 100
    assert "transmissie eerste 0" in _keywords(
        session, projects.member_project.id
    )
    assert "transmissie tweede 0" in _keywords(
        session, projects.member_project.id
    )


def test_sync_reports_exact_counts_and_collapses_duplicate_identities(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    _add_profile(session, projects)
    session.add(
        KeywordOpportunity(
            id="existing-opportunity",
            project_id=projects.member_project.id,
            keyword="transmissie bestaand",
            location_code=2528,
            language_code="nl",
            search_volume=1,
            source="dataforseo",
            raw_payload={},
        )
    )
    session.commit()
    provider = StubProvider(
        [
            [
                _row("transmissie nieuw", search_volume=10),
                _row("transmissie nieuw", search_volume=20),
                _row("transmissie bestaand", search_volume=30),
                _row("vakantiehuis frankrijk"),
            ]
        ]
    )

    result = sync_keyword_opportunity_window(
        session, projects.member_project, provider, limit=10
    )

    assert (
        result.provider_count,
        result.accepted_count,
        result.created_count,
        result.updated_count,
        result.rejected_count,
    ) == (4, 3, 1, 1, 1)
    opportunities = session.scalars(
        select(KeywordOpportunity).where(
            KeywordOpportunity.project_id == projects.member_project.id
        )
    ).all()
    assert len(opportunities) == 2
    assert {item.keyword: item.search_volume for item in opportunities} == {
        "transmissie bestaand": 30,
        "transmissie nieuw": 20,
    }
    new_item = next(
        item for item in opportunities if item.keyword == "transmissie nieuw"
    )
    assert new_item.first_seen_run_id == result.run_id
    assert new_item.last_seen_run_id == result.run_id


def test_provider_failure_persists_safe_run_without_cursor_or_row_mutation(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    _add_profile(session, projects)
    sync_keyword_opportunity_window(
        session,
        projects.member_project,
        StubProvider([_full_window("eerste")]),
    )
    before_keywords = _keywords(session, projects.member_project.id)

    try:
        sync_keyword_opportunity_window(
            session,
            projects.member_project,
            FailingProvider(),
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("provider failure was not propagated")

    session.expire_all()
    state = session.get(
        KeywordOpportunitySyncState, projects.member_project.id
    )
    assert state is not None
    assert state.next_offset == 50
    assert state.exhausted is False
    assert _keywords(session, projects.member_project.id) == before_keywords
    runs = session.scalars(
        select(KeywordOpportunitySyncRun)
        .where(
            KeywordOpportunitySyncRun.project_id == projects.member_project.id
        )
        .order_by(KeywordOpportunitySyncRun.started_at)
    ).all()
    assert [run.state for run in runs] == ["completed", "failed"]
    assert runs[-1].offset == 50
    assert runs[-1].error_message == "DataForSEO synchronization failed"
    assert state.last_error == "DataForSEO synchronization failed"
    assert "secret-password" not in runs[-1].error_message


def test_processing_failure_rolls_back_partial_opportunity_updates(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    _add_profile(session, projects)
    sync_keyword_opportunity_window(
        session,
        projects.member_project,
        StubProvider([_full_window("eerste")]),
    )

    try:
        sync_keyword_opportunity_window(
            session,
            projects.member_project,
            StubProvider(
                [
                    [
                        _row("transmissie eerste 0", search_volume=999),
                        {
                            "keyword": "transmissie ongeldige locatie",
                            "location_code": "niet-numeriek",
                            "language_code": "nl",
                        },
                    ]
                ]
            ),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid provider row was not rejected")

    session.expire_all()
    existing = session.scalar(
        select(KeywordOpportunity).where(
            KeywordOpportunity.project_id == projects.member_project.id,
            KeywordOpportunity.keyword == "transmissie eerste 0",
        )
    )
    assert existing is not None
    assert existing.search_volume == 10
    assert len(_keywords(session, projects.member_project.id)) == 50
    state = session.get(
        KeywordOpportunitySyncState, projects.member_project.id
    )
    assert state is not None
    assert state.next_offset == 50


def test_changed_seed_fingerprint_restarts_at_zero(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    profile = _add_profile(session, projects)
    provider = StubProvider(
        [_full_window("eerste"), [_row("koppeling tweede")]]
    )
    sync_keyword_opportunity_window(
        session, projects.member_project, provider
    )
    profile.services = ["koppeling montage"]
    session.commit()

    sync_keyword_opportunity_window(
        session, projects.member_project, provider
    )

    assert [call[2] for call in provider.calls] == [0, 0]


def test_exhausted_state_starts_the_next_cycle_at_zero(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    _add_profile(session, projects)
    provider = StubProvider(
        [
            _full_window("eerste"),
            [_row("transmissie tweede")],
            [_row("transmissie derde")],
        ]
    )

    first = sync_keyword_opportunity_window(
        session, projects.member_project, provider
    )
    second = sync_keyword_opportunity_window(
        session, projects.member_project, provider
    )
    third = sync_keyword_opportunity_window(
        session, projects.member_project, provider
    )

    assert first.exhausted is False
    assert (second.offset, second.exhausted) == (50, True)
    assert third.offset == 0
    assert [call[2] for call in provider.calls] == [0, 50, 0]
