from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.crypto import decrypt_text
from app.core.security import CurrentUser, get_current_user
from app.domains.page_packages.models import ProjectPagePackageSettings
from app.domains.page_packages.schemas import PagePackageSettingsWrite
from app.domains.projects.service import get_membership, get_project
from app.domains.wordpress.models import WordPressPage
from app.domains.wordpress.client import WordPressClient
from app.domains.wordpress.models import WordPressConnection

router = APIRouter(prefix="/projects/{project_id}", tags=["page-packages"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]
REQUIRED_SLOTS = {
    "hero_title",
    "introduction",
    "main_content",
    "faq",
    "cta_title",
    "cta_text",
}


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


@router.post("/page-package-settings/inspect-template")
def inspect_page_package_template(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    settings, template = _configured_settings(session, project_id)
    try:
        return _page_package_client(session, project_id).template_slots(
            template.wordpress_object_id,
            settings.builder,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="WordPress template could not be inspected",
        ) from error


@router.post("/page-package-settings/validate")
def validate_page_package_settings(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    settings, template = _configured_settings(session, project_id)
    try:
        inspection = _page_package_client(session, project_id).template_slots(
            template.wordpress_object_id,
            settings.builder,
        )
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="WordPress template could not be inspected",
        ) from error
    available_paths = {
        str(slot.get("path"))
        for slot in inspection.get("slots", [])
        if isinstance(slot, dict) and slot.get("path")
    }
    mapped_required = {
        slot for slot in REQUIRED_SLOTS if settings.slot_mapping.get(slot)
    }
    mapped_paths = {
        settings.slot_mapping[slot] for slot in mapped_required
    }
    valid = (
        inspection.get("builder") == settings.builder
        and inspection.get("seo_plugin") == settings.seo_plugin
        and mapped_required == REQUIRED_SLOTS
        and mapped_paths.issubset(available_paths)
        and bool(inspection.get("template_hash"))
    )
    if not valid:
        settings.validation_state = "invalid"
        settings.template_content_hash = None
        settings.validated_at = None
        session.commit()
        raise HTTPException(
            status_code=409,
            detail="Builder, SEO plugin, or mapped slots do not match the template",
        )
    settings.validation_state = "valid"
    settings.template_content_hash = str(inspection["template_hash"])
    settings.validated_at = datetime.now(UTC)
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


def _configured_settings(
    session: Session,
    project_id: str,
) -> tuple[ProjectPagePackageSettings, WordPressPage]:
    settings = session.get(ProjectPagePackageSettings, project_id)
    if settings is None:
        raise HTTPException(status_code=422, detail="Page package is not configured")
    template = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == settings.template_wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Template page not found")
    return settings, template


def _page_package_client(session: Session, project_id: str) -> WordPressClient:
    connection = session.scalar(
        select(WordPressConnection).where(
            WordPressConnection.project_id == project_id
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="WordPress connection not found")
    return WordPressClient(
        connection.site_url,
        decrypt_text(connection.encrypted_secret),
    )


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
