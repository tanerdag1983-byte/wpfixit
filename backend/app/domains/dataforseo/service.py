import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import (
    KeywordOpportunity,
    KeywordOpportunitySyncRun,
    KeywordOpportunitySyncState,
)
from app.domains.dataforseo.relevance import (
    PageMatch,
    build_keyword_context,
    classify_target,
    is_relevant,
)
from app.domains.projects.models import Project

SAFE_SYNC_ERROR = "DataForSEO synchronization failed"


@dataclass(frozen=True)
class OpportunitySyncResult:
    run_id: str
    offset: int
    next_offset: int
    exhausted: bool
    provider_count: int
    accepted_count: int
    created_count: int
    updated_count: int
    rejected_count: int


def project_seed_terms(
    session: Session,
    project: Project,
    *,
    limit: int = 20,
) -> list[str]:
    return list(build_keyword_context(session, project, limit=limit).seeds)


def seed_fingerprint(seeds: list[str]) -> str:
    normalized = sorted(" ".join(str(seed).casefold().split()) for seed in seeds)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def sync_keyword_opportunity_window(
    session: Session,
    project: Project,
    provider,
    *,
    limit: int = 50,
) -> OpportunitySyncResult:
    project_id = project.id
    seeds = project_seed_terms(session, project)
    fingerprint = seed_fingerprint(seeds)
    state = _locked_sync_state(session, project_id)
    if state is None:
        state = KeywordOpportunitySyncState(
            project_id=project_id,
            seed_fingerprint=fingerprint,
            next_offset=0,
            exhausted=False,
        )
        session.add(state)
    offset = (
        0
        if state.seed_fingerprint != fingerprint or state.exhausted
        else state.next_offset
    )
    previous_successful_run_id = state.last_successful_run_id
    run = KeywordOpportunitySyncRun.started(
        project_id,
        fingerprint,
        offset,
        limit,
    )
    run_id = run.id
    session.add(run)

    try:
        session.flush()
        rows = provider.keyword_ideas(seeds, limit=limit, offset=offset)
        _, accepted_count, created_count, updated_count = (
            _upsert_keyword_opportunities(
                session,
                project,
                rows,
                run_id=run_id,
            )
        )
        provider_count = len(rows)
        rejected_count = provider_count - accepted_count
        exhausted = provider_count < limit
        completed_at = datetime.now(UTC)
        next_offset = offset + limit

        run.state = "completed"
        run.provider_count = provider_count
        run.accepted_count = accepted_count
        run.created_count = created_count
        run.updated_count = updated_count
        run.rejected_count = rejected_count
        run.completed_at = completed_at
        state.seed_fingerprint = fingerprint
        state.next_offset = next_offset
        state.exhausted = exhausted
        state.last_successful_run_id = run_id
        state.last_synced_at = completed_at
        state.last_error = None
        session.commit()
    except Exception:
        session.rollback()
        persisted_state = _locked_sync_state(session, project_id)
        failed_run = KeywordOpportunitySyncRun(
            id=run_id,
            project_id=project_id,
            seed_fingerprint=fingerprint,
            offset=offset,
            limit=limit,
            state="failed",
            completed_at=datetime.now(UTC),
            error_message=SAFE_SYNC_ERROR,
        )
        session.add(failed_run)
        if (
            persisted_state is not None
            and persisted_state.last_successful_run_id
            == previous_successful_run_id
        ):
            persisted_state.last_error = SAFE_SYNC_ERROR
        session.commit()
        raise

    return OpportunitySyncResult(
        run_id=run_id,
        offset=offset,
        next_offset=next_offset,
        exhausted=exhausted,
        provider_count=provider_count,
        accepted_count=accepted_count,
        created_count=created_count,
        updated_count=updated_count,
        rejected_count=rejected_count,
    )


def upsert_keyword_opportunities(
    session: Session,
    project: Project,
    rows: list[dict],
) -> list[KeywordOpportunity]:
    synced, _, _, _ = _upsert_keyword_opportunities(
        session,
        project,
        rows,
        run_id=None,
    )
    session.commit()
    return synced


def reclassify_keyword_opportunities(
    session: Session,
    project: Project,
) -> None:
    context = build_keyword_context(session, project)
    opportunities = session.scalars(
        select(KeywordOpportunity).where(
            KeywordOpportunity.project_id == project.id,
            KeywordOpportunity.source == "dataforseo",
        )
    ).all()
    for opportunity in opportunities:
        _apply_target_match(
            opportunity,
            classify_target(opportunity.keyword, context),
        )


def _upsert_keyword_opportunities(
    session: Session,
    project: Project,
    rows: list[dict],
    *,
    run_id: str | None,
) -> tuple[list[KeywordOpportunity], int, int, int]:
    context = build_keyword_context(session, project)
    existing = {
        (item.keyword, item.location_code, item.language_code): item
        for item in session.scalars(
            select(KeywordOpportunity).where(
                KeywordOpportunity.project_id == project.id,
                KeywordOpportunity.source == "dataforseo",
            )
        ).all()
    }
    synced: list[KeywordOpportunity] = []
    created: set[tuple[str, int, str]] = set()
    updated: set[tuple[str, int, str]] = set()
    accepted_count = 0
    now = datetime.now(UTC)
    for row in rows:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword or not is_relevant(keyword, context):
            continue
        accepted_count += 1
        location_code = int(row.get("location_code") or 2528)
        language_code = str(row.get("language_code") or "nl")
        identity = (keyword, location_code, language_code)
        opportunity = existing.get(identity)
        if opportunity is None:
            opportunity = KeywordOpportunity(
                id=str(uuid4()),
                project_id=project.id,
                keyword=keyword,
                location_code=location_code,
                language_code=language_code,
                raw_payload={},
                discovered_at=now,
                first_seen_run_id=run_id,
            )
            session.add(opportunity)
            existing[identity] = opportunity
            created.add(identity)
        elif identity not in created:
            updated.add(identity)

        match = classify_target(keyword, context)
        opportunity.search_volume = _optional_int(row.get("search_volume"))
        opportunity.cpc = _optional_decimal(row.get("cpc"))
        opportunity.competition = _optional_decimal(row.get("competition"))
        opportunity.competition_level = row.get("competition_level")
        opportunity.keyword_difficulty = _optional_int(
            row.get("keyword_difficulty")
        )
        opportunity.intent = row.get("intent")
        _apply_target_match(opportunity, match)
        opportunity.source = "dataforseo"
        opportunity.raw_payload = row.get("raw_payload") or row
        if run_id is not None:
            opportunity.last_seen_run_id = run_id
        opportunity.last_seen_at = now
        synced.append(opportunity)
    return synced, accepted_count, len(created), len(updated)


def _apply_target_match(opportunity: KeywordOpportunity, match: PageMatch) -> None:
    keyword = opportunity.keyword
    opportunity.target_url = match.url
    opportunity.target_classification = match.classification
    opportunity.target_score = match.score
    opportunity.target_evidence = list(match.evidence)
    if match.classification == "existing_page":
        opportunity.recommended_action = (
            f"Verbeter {match.url} voor het zoekwoord '{keyword}'."
        )
    elif match.classification == "review":
        opportunity.recommended_action = (
            f"Controleer of '{keyword}' bij een bestaande of nieuwe pagina hoort."
        )
    else:
        opportunity.recommended_action = (
            f"Maak een nieuwe landingspagina voor het zoekwoord '{keyword}'."
        )


def _locked_sync_state(
    session: Session,
    project_id: str,
) -> KeywordOpportunitySyncState | None:
    statement = select(KeywordOpportunitySyncState).where(
        KeywordOpportunitySyncState.project_id == project_id
    )
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            select(Project.id)
            .where(Project.id == project_id)
            .with_for_update()
        ).scalar_one()
        statement = statement.with_for_update()
    return session.scalar(statement)


def opportunity_impact_score(opportunity: KeywordOpportunity) -> int:
    volume_score = min(70, ((opportunity.search_volume or 0) + 10) // 20)
    difficulty = (
        opportunity.keyword_difficulty
        if opportunity.keyword_difficulty is not None
        else 50
    )
    difficulty_bonus = max(
        0,
        20 - (difficulty + 2) // 5,
    )
    intent_bonus = 10 if opportunity.intent == "commercial" else 5
    return min(100, volume_score + difficulty_bonus + intent_bonus)


def opportunity_payload(
    opportunity: KeywordOpportunity,
    *,
    is_new: bool = False,
) -> dict:
    return {
        "id": opportunity.id,
        "keyword": opportunity.keyword,
        "location_code": opportunity.location_code,
        "language_code": opportunity.language_code,
        "search_volume": opportunity.search_volume,
        "cpc": opportunity.cpc,
        "competition": opportunity.competition,
        "competition_level": opportunity.competition_level,
        "keyword_difficulty": opportunity.keyword_difficulty,
        "intent": opportunity.intent,
        "target_url": opportunity.target_url,
        "target_classification": opportunity.target_classification,
        "target_score": opportunity.target_score,
        "target_evidence": opportunity.target_evidence,
        "recommended_action": opportunity.recommended_action,
        "source": opportunity.source,
        "discovered_at": opportunity.discovered_at,
        "is_new": is_new,
        "first_seen_at": opportunity.discovered_at,
        "last_seen_at": opportunity.last_seen_at,
    }


def _optional_int(value) -> int | None:
    return int(value) if value is not None else None


def _optional_decimal(value) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
