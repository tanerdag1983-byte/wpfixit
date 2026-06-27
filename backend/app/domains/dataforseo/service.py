from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.dataforseo.relevance import (
    build_keyword_context,
    classify_target,
    is_relevant,
)
from app.domains.projects.models import Project


def project_seed_terms(
    session: Session,
    project: Project,
    *,
    limit: int = 20,
) -> list[str]:
    return list(build_keyword_context(session, project, limit=limit).seeds)


def upsert_keyword_opportunities(
    session: Session,
    project: Project,
    rows: list[dict],
) -> list[KeywordOpportunity]:
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
    accepted: set[tuple[str, int, str]] = set()
    now = datetime.now(UTC)
    for row in rows:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword or not is_relevant(keyword, context):
            continue
        location_code = int(row.get("location_code") or 2528)
        language_code = str(row.get("language_code") or "nl")
        identity = (keyword, location_code, language_code)
        accepted.add(identity)
        opportunity = existing.get(identity)
        if opportunity is None:
            opportunity = KeywordOpportunity(
                id=str(uuid4()),
                project_id=project.id,
                keyword=keyword,
                location_code=location_code,
                language_code=language_code,
                raw_payload={},
            )
            session.add(opportunity)

        match = classify_target(keyword, context)
        matched_url = match.url
        opportunity.search_volume = _optional_int(row.get("search_volume"))
        opportunity.cpc = _optional_decimal(row.get("cpc"))
        opportunity.competition = _optional_decimal(row.get("competition"))
        opportunity.competition_level = row.get("competition_level")
        opportunity.keyword_difficulty = _optional_int(
            row.get("keyword_difficulty")
        )
        opportunity.intent = row.get("intent")
        opportunity.target_url = matched_url
        opportunity.target_classification = match.classification
        opportunity.target_score = match.score
        opportunity.target_evidence = list(match.evidence)
        if match.classification == "existing_page":
            opportunity.recommended_action = (
                f"Verbeter {matched_url} voor het zoekwoord '{keyword}'."
            )
        elif match.classification == "review":
            opportunity.recommended_action = (
                f"Controleer of '{keyword}' bij een bestaande of nieuwe pagina hoort."
            )
        else:
            opportunity.recommended_action = (
                f"Maak een nieuwe landingspagina voor het zoekwoord '{keyword}'."
            )
        opportunity.source = "dataforseo"
        opportunity.raw_payload = row.get("raw_payload") or row
        opportunity.discovered_at = now
        synced.append(opportunity)
    for identity, opportunity in existing.items():
        if identity not in accepted:
            session.delete(opportunity)
    session.commit()
    return synced


def opportunity_payload(opportunity: KeywordOpportunity) -> dict:
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
    }


def _optional_int(value) -> int | None:
    return int(value) if value is not None else None


def _optional_decimal(value) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
