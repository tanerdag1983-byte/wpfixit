from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text, encrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.audits.service import audit_project
from app.domains.projects.service import get_project
from app.domains.wordpress.client import WordPressClient
from app.domains.wordpress.models import WordPressConnection, WordPressPage
from app.domains.wordpress.schemas import (
    WordPressConnectionRead,
    WordPressConnectRequest,
)
from app.domains.wordpress.service import sync_inventory

router = APIRouter(prefix="/projects/{project_id}", tags=["wordpress"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _project_or_404(
    session: Session,
    user: CurrentUser,
    project_id: str,
):
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/wordpress-connect",
    response_model=WordPressConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
def connect_wordpress(
    project_id: str,
    payload: WordPressConnectRequest,
    session: SessionDependency,
    user: UserDependency,
) -> WordPressConnectionRead:
    _project_or_404(session, user, project_id)
    client = WordPressClient(str(payload.site_url), payload.secret)
    try:
        health = client.health()
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="WordPress bridge could not be verified",
        ) from error

    connection = session.scalar(
        select(WordPressConnection).where(
            WordPressConnection.project_id == project_id
        )
    )
    if connection is None:
        connection = WordPressConnection(id=str(uuid4()), project_id=project_id)
        session.add(connection)
    connection.site_url = health.site_url.rstrip("/")
    connection.encrypted_secret = encrypt_text(payload.secret)
    connection.plugin_version = health.plugin_version
    connection.seo_plugin = health.seo_plugin
    connection.health_state = "connected"
    connection.last_checked_at = datetime.now(UTC)
    session.commit()
    return WordPressConnectionRead(
        project_id=project_id,
        site_url=connection.site_url,
        plugin_version=connection.plugin_version,
        seo_plugin=connection.seo_plugin,
        health_state=connection.health_state,
    )


@router.post("/sync-pages")
def sync_pages(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, int | str]:
    _project_or_404(session, user, project_id)
    connection = session.scalar(
        select(WordPressConnection).where(
            WordPressConnection.project_id == project_id
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="WordPress connection not found")
    client = WordPressClient(
        connection.site_url,
        decrypt_text(connection.encrypted_secret),
    )
    saved_count = sync_inventory(session, project_id, client.inventory())
    return {"status": "ok", "saved_count": saved_count}


@router.get("/wordpress-pages")
def get_pages(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, object]:
    _project_or_404(session, user, project_id)
    pages = list(
        session.scalars(
            select(WordPressPage)
            .where(WordPressPage.project_id == project_id)
            .order_by(WordPressPage.url)
        )
    )
    return {
        "count": len(pages),
        "items": [
            {
                "id": page.id,
                "wordpress_object_id": page.wordpress_object_id,
                "post_type": page.post_type,
                "status": page.status,
                "title": page.title,
                "slug": page.slug,
                "url": page.url,
                "content_hash": page.content_hash,
            }
            for page in pages
        ],
    }


@router.post("/audit")
def run_audit(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, int | str]:
    project = _project_or_404(session, user, project_id)
    return {
        "status": "ok",
        "audited_count": audit_project(session, project),
    }

