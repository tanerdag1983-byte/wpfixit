from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.domains.projects.models import (
    Organization,
    OrganizationMember,
    Profile,
    Project,
)
from app.domains.projects.schemas import ProjectCreate, ProjectUpdate


def ensure_workspace(session: Session, user: CurrentUser) -> OrganizationMember:
    membership = session.scalar(
        select(OrganizationMember).where(OrganizationMember.profile_id == user.id)
    )
    if membership is not None:
        return membership

    profile = session.get(Profile, user.id)
    if profile is None:
        profile = Profile(id=user.id, email=user.email)
        session.add(profile)

    organization = Organization(
        id=str(uuid4()),
        name=f"{user.email.split('@')[0]} workspace",
    )
    membership = OrganizationMember(
        organization_id=organization.id,
        profile_id=user.id,
        role="owner",
    )
    session.add_all([organization, membership])
    session.commit()
    return membership


def _visible_projects(user_id: str) -> Select[tuple[Project]]:
    return (
        select(Project)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Project.organization_id,
        )
        .where(
            OrganizationMember.profile_id == user_id,
            Project.deleted_at.is_(None),
        )
    )


def list_projects(session: Session, user: CurrentUser) -> list[Project]:
    ensure_workspace(session, user)
    return list(
        session.scalars(_visible_projects(user.id).order_by(Project.created_at))
    )


def get_project(session: Session, user_id: str, project_id: str) -> Project | None:
    return session.scalar(_visible_projects(user_id).where(Project.id == project_id))


def get_membership(
    session: Session,
    user_id: str,
    organization_id: str,
) -> OrganizationMember | None:
    return session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.profile_id == user_id,
            OrganizationMember.organization_id == organization_id,
        )
    )


def create_project(
    session: Session,
    user: CurrentUser,
    payload: ProjectCreate,
) -> Project | None:
    organization_id = payload.organization_id
    if organization_id is None:
        organization_id = ensure_workspace(session, user).organization_id

    membership = get_membership(session, user.id, organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        return None

    project = Project(
        id=str(uuid4()),
        organization_id=organization_id,
        name=payload.name,
        domain=str(payload.domain).rstrip("/"),
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def soft_delete_project(
    session: Session,
    user_id: str,
    project_id: str,
) -> bool:
    project = get_project(session, user_id, project_id)
    if project is None:
        return False
    membership = get_membership(session, user_id, project.organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        return False

    project.deleted_at = datetime.now(UTC)
    session.commit()
    return True


def update_project(
    session: Session,
    user_id: str,
    project_id: str,
    payload: ProjectUpdate,
) -> Project | None:
    project = get_project(session, user_id, project_id)
    if project is None:
        return None
    membership = get_membership(session, user_id, project.organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        return None

    project.name = payload.name
    session.commit()
    session.refresh(project)
    return project
