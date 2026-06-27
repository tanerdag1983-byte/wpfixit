from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.page_packages.models import ProjectPagePackageSettings
from app.domains.page_packages.schemas import PagePackageSettingsWrite
from app.domains.projects.service import get_membership, get_project
from app.domains.wordpress.models import WordPressPage

router = APIRouter(prefix="/projects/{project_id}", tags=["page-packages"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/page-package-settings")
def get_page_package_settings(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _project_or_404(session, user, project_id)
    settings = session.get(ProjectPagePackageSettings, project_id)
    if settings is None:
        return {"configured": False, "validation_state": "unconfigured"}
    return _settings_payload(settings)


@router.put("/page-package-settings")
def put_page_package_settings(
    project_id: str,
    payload: PagePackageSettingsWrite,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    template = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == payload.template_wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Template page not found")
    settings = session.get(ProjectPagePackageSettings, project_id)
    if settings is None:
        settings = ProjectPagePackageSettings(project_id=project_id)
        session.add(settings)
    settings.builder = payload.builder
    settings.template_wordpress_page_id = template.id
    settings.seo_plugin = payload.seo_plugin
    settings.slot_mapping = payload.slot_mapping
    settings.template_content_hash = None
    settings.validation_state = "unvalidated"
    settings.validated_at = None
    session.commit()
    return _settings_payload(settings)


def _project_or_404(
    session: Session,
    user: CurrentUser,
    project_id: str,
):
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_manager(
    session: Session,
    user: CurrentUser,
    organization_id: str,
) -> None:
    membership = get_membership(session, user.id, organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")


def _settings_payload(settings: ProjectPagePackageSettings) -> dict:
    return {
        "configured": True,
        "project_id": settings.project_id,
        "builder": settings.builder,
        "template_wordpress_page_id": settings.template_wordpress_page_id,
        "seo_plugin": settings.seo_plugin,
        "slot_mapping": settings.slot_mapping,
        "template_content_hash": settings.template_content_hash,
        "validation_state": settings.validation_state,
        "validated_at": settings.validated_at,
    }
