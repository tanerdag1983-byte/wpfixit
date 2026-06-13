from typing import Annotated, Literal

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text, encrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.projects.service import get_membership, get_project
from app.domains.recommendations.models import (
    CompanyProfile,
    OrganizationAiSettings,
)

router = APIRouter(tags=["ai-settings"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


class AiSettingsRequest(BaseModel):
    provider: Literal["openai", "openai_compatible"]
    base_url: AnyHttpUrl
    model: str = Field(min_length=1, max_length=255)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)


class CompanyProfileRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5_000)
    audience: str = Field(default="", max_length=2_000)
    services: list[str] = Field(default_factory=list, max_length=100)
    tone_of_voice: str = Field(default="", max_length=255)
    custom_prompt: str = Field(default="", max_length=5_000)


@router.get("/organizations/{organization_id}/ai-settings")
def get_ai_settings(
    organization_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    if get_membership(session, user.id, organization_id) is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    settings = session.get(OrganizationAiSettings, organization_id)
    if settings is None:
        return {"configured": False}
    return _settings_payload(settings)


@router.put("/organizations/{organization_id}/ai-settings")
def put_ai_settings(
    organization_id: str,
    payload: AiSettingsRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    membership = get_membership(session, user.id, organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=404, detail="Organization not found")
    settings = session.get(OrganizationAiSettings, organization_id)
    if settings is None:
        if payload.api_key is None:
            raise HTTPException(status_code=422, detail="API key is required")
        settings = OrganizationAiSettings(organization_id=organization_id)
        session.add(settings)
    settings.provider = payload.provider
    settings.base_url = str(payload.base_url).rstrip("/")
    settings.model = payload.model.strip()
    if payload.api_key is not None:
        settings.encrypted_api_key = encrypt_text(payload.api_key)
    session.commit()
    return _settings_payload(settings)


@router.post("/organizations/{organization_id}/ai-settings/test")
def test_ai_settings(
    organization_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, str]:
    membership = get_membership(session, user.id, organization_id)
    settings = session.get(OrganizationAiSettings, organization_id)
    if membership is None or settings is None:
        raise HTTPException(status_code=404, detail="AI settings not found")
    try:
        response = requests.get(
            f"{settings.base_url}/models",
            headers={
                "Authorization": (f"Bearer {decrypt_text(settings.encrypted_api_key)}")
            },
            timeout=15,
        )
        response.raise_for_status()
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="AI provider connection failed",
        ) from error
    return {"status": "connected", "model": settings.model}


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


def _settings_payload(settings: OrganizationAiSettings) -> dict:
    return {
        "provider": settings.provider,
        "base_url": settings.base_url,
        "model": settings.model,
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
