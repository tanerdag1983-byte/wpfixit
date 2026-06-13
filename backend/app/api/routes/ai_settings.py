from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

import requests
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text, encrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.projects.service import get_membership, get_project
from app.domains.recommendations.models import (
    AiConnection,
    CompanyProfile,
    ProjectAiPolicy,
)

router = APIRouter(tags=["ai-settings"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]
AiProvider = Literal["openai", "anthropic", "gemini", "openai_compatible"]


class AiConnectionWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    provider: AiProvider
    base_url: AnyHttpUrl
    default_model: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    enabled: bool = True


class AiConnectionTestRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    model: str | None = Field(default=None, max_length=255)


class CompanyProfileRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5_000)
    audience: str = Field(default="", max_length=2_000)
    services: list[str] = Field(default_factory=list, max_length=100)
    tone_of_voice: str = Field(default="", max_length=255)
    custom_prompt: str = Field(default="", max_length=5_000)


@router.get("/organizations/{organization_id}/ai-connections")
def get_ai_connections(
    organization_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> list[dict]:
    _require_membership(session, user, organization_id)
    connections = session.scalars(
        select(AiConnection)
        .where(AiConnection.organization_id == organization_id)
        .order_by(AiConnection.name, AiConnection.id)
    ).all()
    return [_connection_payload(connection) for connection in connections]


@router.post(
    "/organizations/{organization_id}/ai-connections",
    status_code=status.HTTP_201_CREATED,
)
def create_ai_connection(
    organization_id: str,
    payload: AiConnectionWrite,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _require_manager(session, user, organization_id)
    if payload.api_key is None:
        raise HTTPException(status_code=422, detail="API key is required")
    _ensure_unique_name(session, organization_id, payload.name)
    connection = AiConnection(
        id=str(uuid4()),
        organization_id=organization_id,
        name=payload.name,
        provider=payload.provider,
        base_url=str(payload.base_url).rstrip("/"),
        default_model=payload.default_model,
        encrypted_api_key=encrypt_text(payload.api_key),
        enabled=payload.enabled,
    )
    session.add(connection)
    session.commit()
    return _connection_payload(connection)


@router.put("/organizations/{organization_id}/ai-connections/{connection_id}")
def update_ai_connection(
    organization_id: str,
    connection_id: str,
    payload: AiConnectionWrite,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _require_manager(session, user, organization_id)
    connection = _get_connection(session, organization_id, connection_id)
    _ensure_unique_name(
        session,
        organization_id,
        payload.name,
        exclude_id=connection.id,
    )
    connection.name = payload.name
    connection.provider = payload.provider
    connection.base_url = str(payload.base_url).rstrip("/")
    connection.default_model = payload.default_model
    connection.enabled = payload.enabled
    if payload.api_key is not None:
        connection.encrypted_api_key = encrypt_text(payload.api_key)
    session.commit()
    return _connection_payload(connection)


@router.delete(
    "/organizations/{organization_id}/ai-connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_ai_connection(
    organization_id: str,
    connection_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> Response:
    _require_manager(session, user, organization_id)
    connection = _get_connection(session, organization_id, connection_id)
    policy = session.scalar(
        select(ProjectAiPolicy).where(
            ProjectAiPolicy.organization_id == organization_id,
            or_(
                ProjectAiPolicy.primary_connection_id == connection.id,
                ProjectAiPolicy.fallback_connection_id == connection.id,
            ),
        )
    )
    if policy is not None:
        raise HTTPException(
            status_code=409,
            detail="AI connection is used by a project policy",
        )
    session.delete(connection)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/organizations/{organization_id}/ai-connections/{connection_id}/test"
)
def test_ai_connection(
    organization_id: str,
    connection_id: str,
    session: SessionDependency,
    user: UserDependency,
    payload: AiConnectionTestRequest | None = None,
) -> dict:
    _require_manager(session, user, organization_id)
    connection = _get_connection(session, organization_id, connection_id)
    model = (payload.model if payload else None) or connection.default_model
    if not model:
        raise HTTPException(status_code=422, detail="Model is required")

    tested_at = datetime.now(UTC)
    try:
        response = _provider_test_request(
            connection,
            model,
            decrypt_text(connection.encrypted_api_key),
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError("Provider returned an unsuccessful status")
    except Exception as error:
        connection.last_tested_at = tested_at
        connection.last_test_status = "failed"
        connection.last_test_message = "Connection failed"
        session.commit()
        raise HTTPException(
            status_code=400,
            detail="AI provider connection failed",
        ) from error

    connection.last_tested_at = tested_at
    connection.last_test_status = "connected"
    connection.last_test_message = "Connection successful"
    session.commit()
    return _connection_payload(connection)


@router.get("/projects/{project_id}/company-profile")
def get_company_profile(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    profile = session.get(CompanyProfile, project_id)
    return _profile_payload(profile) if profile else {"configured": False}


@router.put("/projects/{project_id}/company-profile")
def put_company_profile(
    project_id: str,
    payload: CompanyProfileRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    membership = get_membership(session, user.id, project.organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")
    profile = session.get(CompanyProfile, project_id)
    if profile is None:
        profile = CompanyProfile(project_id=project_id)
        session.add(profile)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    session.commit()
    return _profile_payload(profile)


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


def _get_connection(
    session: Session,
    organization_id: str,
    connection_id: str,
) -> AiConnection:
    connection = session.scalar(
        select(AiConnection).where(
            AiConnection.id == connection_id,
            AiConnection.organization_id == organization_id,
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="AI connection not found")
    return connection


def _ensure_unique_name(
    session: Session,
    organization_id: str,
    name: str,
    *,
    exclude_id: str | None = None,
) -> None:
    query = select(AiConnection.id).where(
        AiConnection.organization_id == organization_id,
        AiConnection.name == name,
    )
    if exclude_id is not None:
        query = query.where(AiConnection.id != exclude_id)
    if session.scalar(query) is not None:
        raise HTTPException(
            status_code=409,
            detail="AI connection name already exists",
        )


def _provider_test_request(
    connection: AiConnection,
    model: str,
    api_key: str,
) -> requests.Response:
    base_url = connection.base_url.rstrip("/")
    if connection.provider == "openai":
        return requests.post(
            f"{base_url}/responses",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "input": "Reply with OK",
                "max_output_tokens": 8,
            },
            timeout=15,
        )
    if connection.provider == "anthropic":
        return requests.post(
            f"{base_url}/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "Reply with OK"}],
            },
            timeout=15,
        )
    if connection.provider == "gemini":
        return requests.post(
            f"{base_url}/models/{model}:generateContent?key={api_key}",
            headers={},
            json={"contents": [{"parts": [{"text": "Reply with OK"}]}]},
            timeout=15,
        )
    return requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with OK"}],
            "max_tokens": 8,
        },
        timeout=15,
    )


def _connection_payload(connection: AiConnection) -> dict:
    return {
        "id": connection.id,
        "name": connection.name,
        "provider": connection.provider,
        "base_url": connection.base_url,
        "default_model": connection.default_model,
        "enabled": connection.enabled,
        "last_tested_at": connection.last_tested_at,
        "last_test_status": connection.last_test_status,
        "last_test_message": connection.last_test_message,
        "configured": True,
    }


def _profile_payload(profile: CompanyProfile) -> dict:
    return {
        "configured": True,
        "company_name": profile.company_name,
        "description": profile.description,
        "audience": profile.audience,
        "services": profile.services,
        "tone_of_voice": profile.tone_of_voice,
        "custom_prompt": profile.custom_prompt,
    }
