from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.ga4.models import (
    Ga4Connection,
    Ga4PagePerformance,
    Ga4TrafficSource,
)
from app.domains.ga4.sync import sync_ga4
from app.domains.google.models import GoogleConnection
from app.domains.google.token_store import (
    provider_from_settings,
    valid_access_token,
)
from app.domains.projects.service import get_project

router = APIRouter(tags=["ga4"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


class Ga4BindingRequest(BaseModel):
    google_connection_id: str
    account_id: str | None = None
    property_id: str
    display_name: str
    currency: str | None = None
    timezone: str | None = None


def _google_connection(
    session: Session,
    user_id: str,
    connection_id: str,
) -> GoogleConnection:
    connection = session.scalar(
        select(GoogleConnection).where(
            GoogleConnection.id == connection_id,
            GoogleConnection.user_id == user_id,
            GoogleConnection.revoked_at.is_(None),
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Google connection not found")
    return connection


@router.get("/google/connections/{connection_id}/ga4-properties")
def ga4_properties(
    connection_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, list[dict]]:
    connection = _google_connection(session, user.id, connection_id)
    provider = provider_from_settings()
    token = valid_access_token(session, connection, provider)
    return {"items": provider.list_ga4_properties(token)}


@router.post("/projects/{project_id}/connect-ga4")
def connect_ga4(
    project_id: str,
    payload: Ga4BindingRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, str]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    google_connection = _google_connection(
        session,
        user.id,
        payload.google_connection_id,
    )
    binding = session.scalar(
        select(Ga4Connection).where(Ga4Connection.project_id == project_id)
    )
    if binding is None:
        binding = Ga4Connection(id=str(uuid4()), project_id=project_id)
        session.add(binding)
    binding.google_connection_id = google_connection.id
    binding.account_id = payload.account_id
    binding.property_id = payload.property_id.removeprefix("properties/")
    binding.display_name = payload.display_name
    binding.currency = payload.currency
    binding.timezone = payload.timezone
    binding.state = "connected"
    session.commit()
    return {
        "status": "connected",
        "property_id": binding.property_id,
    }


@router.post("/projects/{project_id}/sync-ga4")
def sync_ga4_data(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> dict[str, int]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    binding = session.scalar(
        select(Ga4Connection).where(Ga4Connection.project_id == project_id)
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="GA4 not connected")
    connection = _google_connection(
        session,
        user.id,
        binding.google_connection_id,
    )
    result = sync_ga4(
        session,
        binding,
        connection,
        provider_from_settings(),
        start_date=start_date or date.today() - timedelta(days=90),
        end_date=end_date or date.today(),
    )
    binding.last_synced_at = datetime.now(UTC)
    session.commit()
    return result


@router.get("/projects/{project_id}/ga4-data")
def get_ga4_data(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    page_statement = select(Ga4PagePerformance).where(
        Ga4PagePerformance.project_id == project_id
    )
    source_statement = select(Ga4TrafficSource).where(
        Ga4TrafficSource.project_id == project_id
    )
    if start_date:
        page_statement = page_statement.where(
            Ga4PagePerformance.date >= start_date
        )
        source_statement = source_statement.where(
            Ga4TrafficSource.date >= start_date
        )
    if end_date:
        page_statement = page_statement.where(
            Ga4PagePerformance.date <= end_date
        )
        source_statement = source_statement.where(
            Ga4TrafficSource.date <= end_date
        )
    pages = list(session.scalars(page_statement.order_by(Ga4PagePerformance.date)))
    sources = list(
        session.scalars(
            source_statement.order_by(Ga4TrafficSource.sessions.desc())
        )
    )
    return {
        "pages": [
            {
                "date": row.date,
                "page_path": row.page_path,
                "sessions": row.sessions,
                "users": row.active_users,
                "engagement_rate": row.engagement_rate,
                "conversions": row.key_events,
                "revenue": row.revenue,
            }
            for row in pages
        ],
        "traffic_sources": [
            {
                "date": row.date,
                "source": row.source,
                "medium": row.medium,
                "campaign": row.campaign,
                "sessions": row.sessions,
                "users": row.active_users,
                "engagement_rate": row.engagement_rate,
                "conversions": row.key_events,
                "revenue": row.revenue,
            }
            for row in sources[:100]
        ],
    }

