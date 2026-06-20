from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.audits.models import SeoRecommendation
from app.domains.audits.service import audit_project
from app.domains.projects.service import get_membership, get_project
from app.domains.recommendations.provider import (
    PUBLISHABLE_ACTION_TYPES,
    publishable_action_type,
)
from app.domains.wordpress.client import WordPressClient
from app.domains.wordpress.demo import DemoWordPressClient
from app.domains.wordpress.models import (
    WordPressChangeEvent,
    WordPressChangeProposal,
    WordPressConnection,
    WordPressPage,
)
from app.domains.wordpress.publishing import (
    MutationResult,
    PublishConflict,
    Publisher,
    PublishNotApproved,
)
from app.domains.wordpress.schemas import (
    WordPressConnectionRead,
    WordPressConnectRequest,
)
from app.domains.wordpress.service import sync_inventory

router = APIRouter(prefix="/projects/{project_id}", tags=["wordpress"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


class ChangeProposalRequest(BaseModel):
    wordpress_page_id: str
    recommendation_id: str | None = None
    change_type: str
    before_value: Any
    after_value: Any


class RollbackRequest(BaseModel):
    confirmed: bool


class ChangeProposalUpdate(BaseModel):
    after_value: Any


SUPPORTED_CHANGE_TYPES = PUBLISHABLE_ACTION_TYPES


def _project_or_404(
    session: Session,
    user: CurrentUser,
    project_id: str,
):
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_manager(session: Session, user: CurrentUser, project) -> None:
    membership = get_membership(
        session,
        user.id,
        project.organization_id,
    )
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")


def _connection_client(
    session: Session,
    project_id: str,
) -> WordPressClient | DemoWordPressClient:
    settings = get_settings()
    if settings.environment == "development" and settings.demo_mode:
        return DemoWordPressClient()
    connection = session.scalar(
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="WordPress connection not found")
    return WordPressClient(
        connection.site_url,
        decrypt_text(connection.encrypted_secret),
    )


def _proposal_or_404(
    session: Session,
    project_id: str,
    proposal_id: str,
) -> WordPressChangeProposal:
    proposal = session.scalar(
        select(WordPressChangeProposal).where(
            WordPressChangeProposal.id == proposal_id,
            WordPressChangeProposal.project_id == project_id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Change proposal not found")
    return proposal


def _publishable_change_type(action_type: str) -> str:
    return publishable_action_type(action_type)


def _current_wordpress_state(
    session: Session,
    project_id: str,
    page: WordPressPage,
) -> dict[str, Any]:
    try:
        return _connection_client(session, project_id).current_state(
            page.wordpress_object_id
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="Current WordPress state could not be loaded",
        ) from error


def _refresh_proposal_from_wordpress(
    session: Session,
    project_id: str,
    proposal: WordPressChangeProposal,
    page: WordPressPage,
) -> None:
    current = _current_wordpress_state(session, project_id, page)
    proposal.base_content_hash = current["content_hash"]
    proposal.current_content_hash = current["content_hash"]
    proposal.before_value = current.get("values", {}).get(proposal.change_type, "")
    proposal.approval_state = "proposed"
    proposal.approved_by = None
    proposal.approved_at = None
    page.content_hash = current["content_hash"]


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
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
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


@router.get("/wordpress-connection", response_model=WordPressConnectionRead)
def get_wordpress_connection(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> WordPressConnectionRead:
    _project_or_404(session, user, project_id)
    connection = session.scalar(
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="WordPress connection not found")
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
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
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


@router.post(
    "/change-proposals",
    status_code=status.HTTP_201_CREATED,
)
def create_change_proposal(
    project_id: str,
    payload: ChangeProposalRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, Any]:
    _project_or_404(session, user, project_id)
    page = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == payload.wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if page is None or not page.content_hash:
        raise HTTPException(status_code=404, detail="WordPress page not found")
    if payload.recommendation_id:
        recommendation = session.scalar(
            select(SeoRecommendation).where(
                SeoRecommendation.id == payload.recommendation_id,
                SeoRecommendation.project_id == project_id,
                SeoRecommendation.wordpress_page_id == page.id,
            )
        )
        if recommendation is None:
            raise HTTPException(status_code=404, detail="Recommendation not found")
    proposal = WordPressChangeProposal(
        id=str(uuid4()),
        project_id=project_id,
        wordpress_page_id=page.id,
        recommendation_id=payload.recommendation_id,
        change_type=payload.change_type,
        before_value=payload.before_value,
        after_value=payload.after_value,
        base_content_hash=page.content_hash,
        proposed_by=user.id,
        approval_state="proposed",
    )
    session.add(proposal)
    session.commit()
    return _proposal_payload(proposal, page)


@router.post(
    "/recommendations/{recommendation_id}/change-proposal",
    status_code=status.HTTP_201_CREATED,
)
def create_change_proposal_from_recommendation(
    project_id: str,
    recommendation_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, Any]:
    _project_or_404(session, user, project_id)
    recommendation = session.scalar(
        select(SeoRecommendation).where(
            SeoRecommendation.id == recommendation_id,
            SeoRecommendation.project_id == project_id,
        )
    )
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    page = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == recommendation.wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if page is None:
        raise HTTPException(status_code=404, detail="WordPress page not found")
    change_type = _publishable_change_type(recommendation.action_type)
    existing = session.scalar(
        select(WordPressChangeProposal)
        .where(
            WordPressChangeProposal.project_id == project_id,
            WordPressChangeProposal.recommendation_id == recommendation.id,
            WordPressChangeProposal.approval_state.in_(
                ["proposed", "approved", "conflict"]
            ),
        )
        .order_by(WordPressChangeProposal.created_at.desc())
    )
    if existing is None:
        existing = WordPressChangeProposal(
            id=str(uuid4()),
            project_id=project_id,
            wordpress_page_id=page.id,
            recommendation_id=recommendation.id,
            change_type=change_type,
            before_value="",
            after_value=recommendation.recommendation,
            base_content_hash=page.content_hash or "",
            proposed_by=user.id,
            approval_state="proposed",
        )
        session.add(existing)
    else:
        existing.change_type = change_type
        existing.after_value = recommendation.recommendation
    _refresh_proposal_from_wordpress(session, project_id, existing, page)
    session.commit()
    return _proposal_payload(existing, page)


@router.get("/change-proposals")
def list_change_proposals(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, list[dict[str, Any]]]:
    _project_or_404(session, user, project_id)
    proposals = list(
        session.scalars(
            select(WordPressChangeProposal)
            .where(WordPressChangeProposal.project_id == project_id)
            .order_by(WordPressChangeProposal.created_at.desc())
        )
    )
    pages = {
        page.id: page
        for page in session.scalars(
            select(WordPressPage).where(WordPressPage.project_id == project_id)
        )
    }
    return {
        "items": [
            _proposal_payload(proposal, pages[proposal.wordpress_page_id])
            for proposal in proposals
        ]
    }


@router.put("/change-proposals/{proposal_id}")
def update_change_proposal(
    project_id: str,
    proposal_id: str,
    payload: ChangeProposalUpdate,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, Any]:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project)
    proposal = _proposal_or_404(session, project_id, proposal_id)
    if proposal.approval_state != "proposed":
        raise HTTPException(
            status_code=409,
            detail="Only proposed changes can be edited",
        )
    proposal.after_value = payload.after_value
    session.commit()
    page = session.get(WordPressPage, proposal.wordpress_page_id)
    assert page is not None
    return _proposal_payload(proposal, page)


@router.post("/change-proposals/{proposal_id}/refresh")
def refresh_change_proposal(
    project_id: str,
    proposal_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, Any]:
    _project_or_404(session, user, project_id)
    proposal = _proposal_or_404(session, project_id, proposal_id)
    page = session.get(WordPressPage, proposal.wordpress_page_id)
    assert page is not None
    if proposal.approval_state not in {"proposed", "approved", "conflict"}:
        raise HTTPException(
            status_code=409,
            detail="Only active proposals can be refreshed",
        )
    _refresh_proposal_from_wordpress(session, project_id, proposal, page)
    session.commit()
    return _proposal_payload(proposal, page)


@router.get("/change-events")
def list_change_events(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, list[dict[str, Any]]]:
    _project_or_404(session, user, project_id)
    events = session.scalars(
        select(WordPressChangeEvent)
        .where(WordPressChangeEvent.project_id == project_id)
        .order_by(WordPressChangeEvent.created_at.desc())
    )
    return {
        "items": [
            {
                "id": event.id,
                "proposal_id": event.proposal_id,
                "actor_id": event.actor_id,
                "mutation_type": event.mutation_type,
                "before_value": event.before_value,
                "after_value": event.after_value,
                "content_hash": event.content_hash,
                "created_at": event.created_at,
            }
            for event in events
        ]
    }


@router.post("/change-proposals/{proposal_id}/approve")
def approve_change_proposal(
    project_id: str,
    proposal_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, Any]:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project)
    proposal = _proposal_or_404(session, project_id, proposal_id)
    if proposal.approval_state != "proposed":
        raise HTTPException(status_code=409, detail="Proposal is not awaiting approval")
    proposal.approval_state = "approved"
    proposal.approved_by = user.id
    proposal.approved_at = datetime.now(UTC)
    session.commit()
    page = session.get(WordPressPage, proposal.wordpress_page_id)
    assert page is not None
    return _proposal_payload(proposal, page)


@router.post("/change-proposals/{proposal_id}/publish")
def publish_change_proposal(
    project_id: str,
    proposal_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, Any]:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project)
    proposal = _proposal_or_404(session, project_id, proposal_id)
    page = session.get(WordPressPage, proposal.wordpress_page_id)
    assert page is not None
    try:
        result = Publisher(_connection_client(session, project_id)).publish(
            _publishing_proposal(proposal, page)
        )
    except PublishNotApproved as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except PublishConflict as error:
        proposal.approval_state = "conflict"
        session.commit()
        raise HTTPException(status_code=409, detail=str(error)) from error
    proposal.approval_state = "published"
    proposal.published_at = datetime.now(UTC)
    proposal.current_content_hash = result.content_hash
    page.content_hash = result.content_hash
    event = _record_event(session, proposal, user.id, result)
    session.commit()
    return {
        "proposal": _proposal_payload(proposal, page),
        "event_id": event.id,
    }


@router.post("/change-proposals/{proposal_id}/rollback")
def rollback_change_proposal(
    project_id: str,
    proposal_id: str,
    payload: RollbackRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, Any]:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project)
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Rollback confirmation required")
    proposal = _proposal_or_404(session, project_id, proposal_id)
    publish_event = session.scalar(
        select(WordPressChangeEvent)
        .where(
            WordPressChangeEvent.proposal_id == proposal.id,
            WordPressChangeEvent.mutation_type == "publish",
        )
        .order_by(WordPressChangeEvent.created_at.desc())
    )
    if publish_event is None or proposal.approval_state != "published":
        raise HTTPException(status_code=409, detail="Proposal is not published")
    page = session.get(WordPressPage, proposal.wordpress_page_id)
    assert page is not None
    published = MutationResult(
        mutation_type="publish",
        before_value=publish_event.before_value,
        after_value=publish_event.after_value,
        content_hash=publish_event.content_hash,
        response=publish_event.provider_response,
    )
    try:
        result = Publisher(_connection_client(session, project_id)).rollback(
            _publishing_proposal(proposal, page),
            published,
            confirmed=True,
        )
    except PublishConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    proposal.approval_state = "rolled_back"
    proposal.current_content_hash = result.content_hash
    page.content_hash = result.content_hash
    event = _record_event(session, proposal, user.id, result)
    session.commit()
    return {
        "proposal": _proposal_payload(proposal, page),
        "event_id": event.id,
    }


def _publishing_proposal(
    proposal: WordPressChangeProposal,
    page: WordPressPage,
):
    class PublishingProposal:
        id = proposal.id
        wordpress_object_id = page.wordpress_object_id
        change_type = proposal.change_type
        before_value = proposal.before_value
        after_value = proposal.after_value
        base_content_hash = proposal.base_content_hash
        approval_state = proposal.approval_state

    return PublishingProposal()


def _record_event(
    session: Session,
    proposal: WordPressChangeProposal,
    actor_id: str,
    result: MutationResult,
) -> WordPressChangeEvent:
    event = WordPressChangeEvent(
        id=str(uuid4()),
        project_id=proposal.project_id,
        proposal_id=proposal.id,
        actor_id=actor_id,
        mutation_type=result.mutation_type,
        before_value=result.before_value,
        after_value=result.after_value,
        content_hash=result.content_hash,
        provider_response=result.response,
    )
    session.add(event)
    return event


def _proposal_payload(
    proposal: WordPressChangeProposal,
    page: WordPressPage,
) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "wordpress_page_id": page.id,
        "wordpress_object_id": page.wordpress_object_id,
        "url": page.url,
        "change_type": proposal.change_type,
        "before_value": proposal.before_value,
        "after_value": proposal.after_value,
        "base_content_hash": proposal.base_content_hash,
        "approval_state": proposal.approval_state,
        "proposed_by": proposal.proposed_by,
        "approved_by": proposal.approved_by,
        "created_at": proposal.created_at,
        "published_at": proposal.published_at,
    }
