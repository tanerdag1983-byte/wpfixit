from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import encrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.google.models import GoogleConnection
from app.domains.google.oauth import GoogleOAuthService, InvalidOAuthState
from app.domains.google.token_store import (
    provider_from_settings,
    valid_access_token,
)
from app.domains.gsc.models import (
    GscConnection,
    GscPagePerformance,
    GscQuery,
)
from app.domains.gsc.sync import sync_search_console
from app.domains.projects.service import get_project

router = APIRouter(tags=["google"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class PropertyBindingRequest(BaseModel):
    google_connection_id: str
    property_uri: str
    permission_level: str | None = None


def oauth_service(session: Session) -> GoogleOAuthService:
    settings = get_settings()
    return GoogleOAuthService(
        session=session,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
    )


@router.post("/projects/{project_id}/connect-search-console")
def connect_search_console(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    payload: PropertyBindingRequest | None = None,
) -> dict[str, str]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload is None:
        authorization = oauth_service(session).create_authorization(
            user.id,
            project_id,
        )
        return {"authorization_url": authorization.url}

    google_connection = session.scalar(
        select(GoogleConnection).where(
            GoogleConnection.id == payload.google_connection_id,
            GoogleConnection.user_id == user.id,
            GoogleConnection.revoked_at.is_(None),
        )
    )
    if google_connection is None:
        raise HTTPException(status_code=404, detail="Google connection not found")
    binding = session.scalar(
        select(GscConnection).where(GscConnection.project_id == project_id)
    )
    if binding is None:
        binding = GscConnection(id=str(uuid4()), project_id=project_id)
        session.add(binding)
    binding.google_connection_id = google_connection.id
    binding.property_uri = payload.property_uri
    binding.permission_level = payload.permission_level
    binding.state = "connected"
    session.commit()
    return {"status": "connected", "property_uri": binding.property_uri}


@router.post("/auth/google/callback")
def google_callback(
    payload: OAuthCallbackRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, str]:
    try:
        consumed = oauth_service(session).consume_state(payload.state, user.id)
    except InvalidOAuthState as error:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from error
    provider = provider_from_settings()
    token = provider.exchange_code(payload.code, consumed.code_verifier)
    connection = session.scalar(
        select(GoogleConnection).where(
            GoogleConnection.user_id == user.id,
            GoogleConnection.google_subject == token.subject,
        )
    )
    if connection is None:
        connection = GoogleConnection(
            id=str(uuid4()),
            user_id=user.id,
            google_subject=token.subject,
            email=token.email,
            encrypted_access_token=encrypt_text(token.access_token),
            scopes=token.scopes,
            token_expires_at=token.expires_at,
        )
        session.add(connection)
    connection.email = token.email
    connection.encrypted_access_token = encrypt_text(token.access_token)
    if token.refresh_token:
        connection.encrypted_refresh_token = encrypt_text(token.refresh_token)
    connection.scopes = token.scopes
    connection.token_expires_at = token.expires_at
    connection.revoked_at = None
    session.commit()
    return {
        "google_connection_id": connection.id,
        "project_id": consumed.project_id,
    }


@router.get("/google/connections/{connection_id}/search-console-properties")
def search_console_properties(
    connection_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, list[dict]]:
    connection = session.scalar(
        select(GoogleConnection).where(
            GoogleConnection.id == connection_id,
            GoogleConnection.user_id == user.id,
            GoogleConnection.revoked_at.is_(None),
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Google connection not found")
    provider = provider_from_settings()
    token = valid_access_token(session, connection, provider)
    return {"items": provider.list_search_console_properties(token)}


@router.post("/projects/{project_id}/sync-search-console")
def sync_gsc(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> dict[str, int]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    binding = session.scalar(
        select(GscConnection).where(GscConnection.project_id == project_id)
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Search Console not connected")
    connection = session.get(GoogleConnection, binding.google_connection_id)
    if connection is None or connection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Google connection not found")
    result = sync_search_console(
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


@router.get("/projects/{project_id}/search-console-data")
def get_gsc_data(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    page_statement = select(GscPagePerformance).where(
        GscPagePerformance.project_id == project_id
    )
    query_statement = select(GscQuery).where(GscQuery.project_id == project_id)
    if start_date:
        page_statement = page_statement.where(
            GscPagePerformance.date >= start_date
        )
        query_statement = query_statement.where(GscQuery.date >= start_date)
    if end_date:
        page_statement = page_statement.where(GscPagePerformance.date <= end_date)
        query_statement = query_statement.where(GscQuery.date <= end_date)
    pages = list(session.scalars(page_statement.order_by(GscPagePerformance.date)))
    queries = list(session.scalars(query_statement.order_by(GscQuery.clicks.desc())))
    return {
        "pages": [
            {
                "date": row.date,
                "page_url": row.page_url,
                "clicks": row.clicks,
                "impressions": row.impressions,
                "ctr": row.ctr,
                "average_position": row.average_position,
            }
            for row in pages
        ],
        "queries": [
            {
                "date": row.date,
                "query": row.query,
                "page_url": row.page_url,
                "clicks": row.clicks,
                "impressions": row.impressions,
                "ctr": row.ctr,
                "average_position": row.average_position,
            }
            for row in queries[:100]
        ],
    }
