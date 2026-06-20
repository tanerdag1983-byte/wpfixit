from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.projects import service
from app.domains.projects.schemas import (
    ProjectCreate,
    ProjectList,
    ProjectRead,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])

SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: SessionDependency,
    user: UserDependency,
) -> ProjectRead:
    project = service.create_project(session, user, payload)
    if project is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return ProjectRead.model_validate(project)


@router.get("", response_model=ProjectList)
def get_projects(
    session: SessionDependency,
    user: UserDependency,
) -> ProjectList:
    return ProjectList(
        items=[
            ProjectRead.model_validate(project)
            for project in service.list_projects(session, user)
        ]
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> ProjectRead:
    project = service.get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectRead.model_validate(project)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    session: SessionDependency,
    user: UserDependency,
) -> ProjectRead:
    project = service.update_project(session, user.id, project_id, payload)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> Response:
    if not service.soft_delete_project(session, user.id, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
