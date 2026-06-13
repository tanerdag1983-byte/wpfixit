from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.dashboards.service import dashboard_overview
from app.domains.projects.service import get_project

router = APIRouter(prefix="/projects/{project_id}", tags=["dashboards"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/dashboard-overview")
def get_dashboard_overview(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    q: str | None = Query(default=None, max_length=200),
    priority: str | None = Query(default=None),
    page_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    max_score: int = Query(default=100, ge=0, le=100),
) -> dict[str, object]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return dashboard_overview(
        session,
        project_id,
        query=q,
        priority=priority,
        page_type=page_type,
        status=status,
        max_score=max_score,
    )

