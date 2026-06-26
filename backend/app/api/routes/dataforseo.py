from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text, encrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.dataforseo.models import DataForSeoConnection, KeywordOpportunity
from app.domains.dataforseo.provider import DataForSeoProvider
from app.domains.dataforseo.service import (
    opportunity_payload,
    project_seed_terms,
    upsert_keyword_opportunities,
)
from app.domains.projects.service import get_membership, get_project

router = APIRouter(tags=["dataforseo"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


class DataForSeoConnectionWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    login: str = Field(min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=4096)
    enabled: bool = True


@router.get("/organizations/{organization_id}/dataforseo-connection")
def get_dataforseo_connection(
    organization_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _require_membership(session, user, organization_id)
    connection = session.get(DataForSeoConnection, organization_id)
    return _connection_payload(connection)


@router.put("/organizations/{organization_id}/dataforseo-connection")
def put_dataforseo_connection(
    organization_id: str,
    payload: DataForSeoConnectionWrite,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _require_manager(session, user, organization_id)
    connection = session.get(DataForSeoConnection, organization_id)
    if connection is None:
        if payload.password is None:
            raise HTTPException(status_code=422, detail="Password is required")
        connection = DataForSeoConnection(
            organization_id=organization_id,
            login=payload.login,
            encrypted_password=encrypt_text(payload.password),
        )
        session.add(connection)
    connection.login = payload.login
    connection.enabled = payload.enabled
    if payload.password is not None:
        connection.encrypted_password = encrypt_text(payload.password)
    session.commit()
    return _connection_payload(connection)


@router.post("/organizations/{organization_id}/dataforseo-connection/test")
def test_dataforseo_connection(
    organization_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _require_manager(session, user, organization_id)
    connection = _required_connection(session, organization_id)
    password = decrypt_text(connection.encrypted_password)
    tested_at = datetime.now(UTC)
    try:
        DataForSeoProvider(connection.login, password).test_connection()
    except Exception as error:
        message = _safe_failure_message(error, password)
        connection.last_tested_at = tested_at
        connection.last_test_status = "failed"
        connection.last_test_message = message
        session.commit()
        raise HTTPException(status_code=400, detail=message) from error
    connection.last_tested_at = tested_at
    connection.last_test_status = "connected"
    connection.last_test_message = "Connection successful"
    session.commit()
    return _connection_payload(connection)


@router.post("/projects/{project_id}/sync-keyword-opportunities")
def sync_keyword_opportunities(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_manager(session, user, project.organization_id)
    connection = _required_connection(session, project.organization_id)
    if not connection.enabled:
        raise HTTPException(status_code=422, detail="DataForSEO connection is disabled")
    password = decrypt_text(connection.encrypted_password)
    provider = DataForSeoProvider(connection.login, password)
    try:
        rows = provider.keyword_ideas(project_seed_terms(session, project))
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=_safe_failure_message(error, password),
        ) from error
    opportunities = upsert_keyword_opportunities(session, project, rows)
    return {"synced": len(opportunities)}


@router.get("/projects/{project_id}/keyword-opportunities")
def get_keyword_opportunities(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    opportunities = session.scalars(
        select(KeywordOpportunity)
        .where(KeywordOpportunity.project_id == project_id)
        .order_by(
            KeywordOpportunity.search_volume.desc().nullslast(),
            KeywordOpportunity.keyword,
        )
    ).all()
    return {"items": [opportunity_payload(item) for item in opportunities]}


def _required_connection(
    session: Session,
    organization_id: str,
) -> DataForSeoConnection:
    connection = session.get(DataForSeoConnection, organization_id)
    if connection is None:
        raise HTTPException(
            status_code=422,
            detail="DataForSEO connection is not configured",
        )
    return connection


def _require_membership(
    session: Session,
    user: CurrentUser,
    organization_id: str,
) -> None:
    if get_membership(session, user.id, organization_id) is None:
        raise HTTPException(status_code=404, detail="Organization not found")


def _require_manager(
    session: Session,
    user: CurrentUser,
    organization_id: str,
) -> None:
    membership = get_membership(session, user.id, organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=404, detail="Organization not found")


def _connection_payload(connection: DataForSeoConnection | None) -> dict:
    if connection is None:
        return {
            "configured": False,
            "login": None,
            "enabled": False,
            "last_tested_at": None,
            "last_test_status": None,
            "last_test_message": None,
        }
    return {
        "configured": True,
        "login": connection.login,
        "enabled": connection.enabled,
        "last_tested_at": connection.last_tested_at,
        "last_test_status": connection.last_test_status,
        "last_test_message": connection.last_test_message,
    }


def _safe_failure_message(error: Exception, password: str) -> str:
    message = str(error).strip() or "Connection failed"
    if password:
        message = message.replace(password, "[redacted]")
    if len(message) > 300:
        message = f"{message[:299]}…"
    return f"DataForSEO connection failed: {message}"
