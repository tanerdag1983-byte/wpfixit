import re
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.projects.models import Project
from app.domains.wordpress.models import WordPressPage


def project_seed_terms(
    session: Session,
    project: Project,
    *,
    limit: int = 20,
) -> list[str]:
    host = urlparse(project.domain).hostname or project.domain
    values = [host, project.name]
    pages = session.scalars(
        select(WordPressPage)
        .where(WordPressPage.project_id == project.id)
        .order_by(WordPressPage.last_synced_at.desc())
        .limit(limit)
    ).all()
    values.extend(page.title or page.slug for page in pages)
    return _unique_nonempty(values)[:limit]


def upsert_keyword_opportunities(
    session: Session,
    project: Project,
    rows: list[dict],
) -> list[KeywordOpportunity]:
    pages = session.scalars(
        select(WordPressPage).where(WordPressPage.project_id == project.id)
    ).all()
    synced: list[KeywordOpportunity] = []
    now = datetime.now(UTC)
    for row in rows:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        location_code = int(row.get("location_code") or 2528)
        language_code = str(row.get("language_code") or "nl")
        opportunity = session.scalar(
            select(KeywordOpportunity).where(
                KeywordOpportunity.project_id == project.id,
                KeywordOpportunity.keyword == keyword,
                KeywordOpportunity.location_code == location_code,
                KeywordOpportunity.language_code == language_code,
            )
        )
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

        target_url = _target_url(keyword, pages)
        opportunity.search_volume = _optional_int(row.get("search_volume"))
        opportunity.cpc = _optional_decimal(row.get("cpc"))
        opportunity.competition = _optional_decimal(row.get("competition"))
        opportunity.competition_level = row.get("competition_level")
        opportunity.keyword_difficulty = _optional_int(
            row.get("keyword_difficulty")
        )
        opportunity.intent = row.get("intent")
        opportunity.target_url = target_url
        opportunity.recommended_action = (
            f"Verbeter {target_url} voor het zoekwoord '{keyword}'."
            if target_url
            else f"Maak een nieuwe landingspagina voor het zoekwoord '{keyword}'."
        )
        opportunity.source = "dataforseo"
        opportunity.raw_payload = row.get("raw_payload") or row
        opportunity.discovered_at = now
        synced.append(opportunity)
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
        "recommended_action": opportunity.recommended_action,
        "source": opportunity.source,
        "discovered_at": opportunity.discovered_at,
    }


def _target_url(keyword: str, pages: list[WordPressPage]) -> str | None:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", keyword.lower())
        if len(token) >= 4
    }
    best_page = None
    best_score = 0
    for page in pages:
        haystack = f"{page.title} {page.slug} {page.url}".lower()
        score = sum(token in haystack for token in tokens)
        if score > best_score:
            best_page = page
            best_score = score
    return best_page.url if best_page is not None and best_score > 0 else None


def _unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _optional_int(value) -> int | None:
    return int(value) if value is not None else None


def _optional_decimal(value) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
