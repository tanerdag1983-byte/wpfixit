from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.dataforseo.models import DataForSeoConnection, KeywordOpportunity
from tests.recommendations.conftest import ProjectFixtures


def test_dataforseo_connection_is_unique_per_organization(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    session.add(
        DataForSeoConnection(
            organization_id=projects.organization.id,
            login="login-one",
            encrypted_password="encrypted-one",
            enabled=True,
        )
    )
    session.commit()

    session.add(
        DataForSeoConnection(
            organization_id=projects.organization.id,
            login="login-two",
            encrypted_password="encrypted-two",
            enabled=True,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_keyword_opportunity_is_unique_per_project_keyword_location_language(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    session.add(
        KeywordOpportunity(
            id="opportunity-1",
            project_id=projects.member_project.id,
            keyword="automatische transmissie revisie",
            location_code=2528,
            language_code="nl",
            search_volume=320,
            cpc=Decimal("4.25"),
            competition=Decimal("0.42"),
            competition_level="medium",
            keyword_difficulty=38,
            intent="commercial",
            target_url="https://member.example/revisie",
            recommended_action="Verbeter bestaande pagina voor dit zoekwoord.",
            source="dataforseo",
            raw_payload={"keyword": "automatische transmissie revisie"},
        )
    )
    session.commit()

    session.add(
        KeywordOpportunity(
            id="opportunity-2",
            project_id=projects.member_project.id,
            keyword="automatische transmissie revisie",
            location_code=2528,
            language_code="nl",
            source="dataforseo",
            raw_payload={},
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
