from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.projects.models import Organization, Profile
from app.domains.projects.service import get_membership

router = APIRouter(tags=["preferences"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class ProfilePreferencesRequest(BaseModel):
    dashboard_view: Literal["analytics", "action", "hybrid"]
    locale: Literal["nl", "en"]


class BrandingRequest(BaseModel):
    brand_name: str = Field(min_length=1, max_length=160)
    primary_color: HexColor
    accent_color: HexColor


@router.get("/profile/preferences")
def get_profile_preferences(
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, str]:
    profile = session.get(Profile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {
        "dashboard_view": profile.dashboard_view,
        "locale": profile.locale,
    }


@router.patch("/profile/preferences")
def update_profile_preferences(
    payload: ProfilePreferencesRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, str]:
    profile = session.get(Profile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.dashboard_view = payload.dashboard_view
    profile.locale = payload.locale
    session.commit()
    return {
        "dashboard_view": profile.dashboard_view,
        "locale": profile.locale,
    }


@router.get("/organizations/{organization_id}/branding")
def get_branding(
    organization_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, str]:
    membership = get_membership(session, user.id, organization_id)
    organization = session.get(Organization, organization_id)
    if membership is None or organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _branding_payload(organization)


@router.patch("/organizations/{organization_id}/branding")
def update_branding(
    organization_id: str,
    payload: BrandingRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, str]:
    membership = get_membership(session, user.id, organization_id)
    organization = session.get(Organization, organization_id)
    if (
        membership is None
        or organization is None
        or membership.role not in {"owner", "admin"}
    ):
        raise HTTPException(status_code=404, detail="Organization not found")
    organization.brand_name = payload.brand_name.strip()
    organization.primary_color = payload.primary_color.lower()
    organization.accent_color = payload.accent_color.lower()
    session.commit()
    return _branding_payload(organization)


def _branding_payload(organization: Organization) -> dict[str, str]:
    return {
        "brand_name": organization.brand_name,
        "primary_color": organization.primary_color,
        "accent_color": organization.accent_color,
    }
