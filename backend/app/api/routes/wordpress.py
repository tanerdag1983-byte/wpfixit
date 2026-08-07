from datetime import UTC, datetime, timedelta
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
from app.domains.page_packages.models import (
    PagePackageProposal,
    PagePackageRegenerationCandidate,
)
from app.domains.projects.service import get_membership, get_project
from app.domains.recommendations.provider import (
    PUBLISHABLE_ACTION_TYPES,
    publishable_action_type,
)
from app.domains.wordpress.client import WordPressClient
from app.domains.wordpress.demo import DemoWordPressClient
from app.domains.wordpress.models import (
    PageObservedVersion,
    PageRecommendation,
    PageScoreSnapshot,
    PageTimelineEvent,
    WordPressChangeEvent,
    WordPressChangeProposal,
    WordPressConnection,
    WordPressDraftJob,
    WordPressPage,
)
from app.domains.wordpress.monitoring import _score_factors, check_page
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
from app.domains.wordpress.service import sync_current_state, sync_inventory

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


def _page_or_404(session: Session, project_id: str, page_id: str) -> WordPressPage:
    page = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if page is None:
        raise HTTPException(status_code=404, detail="WordPress page not found")
    return page


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
    health = client.health()
    connection.site_url = health.site_url.rstrip("/")
    connection.plugin_version = health.plugin_version
    connection.seo_plugin = health.seo_plugin
    connection.health_state = "connected"
    connection.last_checked_at = datetime.now(UTC)
    inventory = client.inventory()
    saved_count = sync_inventory(session, project_id, inventory)
    for item in inventory:
        page = session.scalar(
            select(WordPressPage).where(
                WordPressPage.project_id == project_id,
                WordPressPage.wordpress_object_id == int(item["id"]),
                WordPressPage.post_type == str(item["type"]),
            )
        )
        if page is not None:
            sync_current_state(
                session,
                page,
                client.current_state(page.wordpress_object_id),
            )
    session.commit()
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


@router.post("/wordpress-pages/{page_id}/checks")
def check_wordpress_page(
    project_id: str,
    page_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, Any]:
    _project_or_404(session, user, project_id)
    page = _page_or_404(session, project_id, page_id)
    facts = _current_wordpress_state(session, project_id, page)
    result = check_page(session, page, facts, trigger="manual")
    session.commit()
    return {
        "version_id": result.version.id,
        "version_created": result.version_created,
        "overall_score": result.score.overall_score,
        "recommendations_created": result.recommendations_created,
        "checked_at": result.checked_at,
    }


@router.get("/wordpress-pages/{page_id}/monitoring")
def get_page_monitoring(
    project_id: str,
    page_id: str,
    session: SessionDependency,
    user: UserDependency,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    _project_or_404(session, user, project_id)
    page = _page_or_404(session, project_id, page_id)
    versions = list(
        session.scalars(
            select(PageObservedVersion)
            .where(PageObservedVersion.wordpress_page_id == page.id)
            .order_by(
                PageObservedVersion.observed_at.desc(),
                PageObservedVersion.id.desc(),
            )
        )
    )
    scores = list(
        session.scalars(
            select(PageScoreSnapshot)
            .join(
                PageObservedVersion,
                PageObservedVersion.id == PageScoreSnapshot.page_version_id,
            )
            .where(PageObservedVersion.wordpress_page_id == page.id)
            .order_by(
                PageScoreSnapshot.created_at.desc(),
                PageScoreSnapshot.id.desc(),
            )
        )
    )
    recommendations = list(
        session.scalars(
            select(PageRecommendation)
            .where(PageRecommendation.wordpress_page_id == page.id)
            .order_by(
                PageRecommendation.created_at.desc(),
                PageRecommendation.id.desc(),
            )
        )
    )
    events = list(
        session.scalars(
            select(PageTimelineEvent)
            .where(PageTimelineEvent.wordpress_page_id == page.id)
            .order_by(
                PageTimelineEvent.created_at.desc(),
                PageTimelineEvent.id.desc(),
            )
        )
    )
    proposal_query = select(PagePackageProposal).where(
        PagePackageProposal.project_id == project_id,
        PagePackageProposal.source_wordpress_page_id == page.id,
    )
    if proposal_id is not None:
        proposal = session.scalar(
            proposal_query.where(PagePackageProposal.id == proposal_id)
        )
        if proposal is None:
            raise HTTPException(status_code=404, detail="Page proposal not found")
    else:
        proposal = session.scalar(
            proposal_query.where(PagePackageProposal.is_current.is_(True)).order_by(
                PagePackageProposal.updated_at.desc(),
                PagePackageProposal.id.desc(),
            )
        )
    draft_job = (
        session.scalar(
            select(WordPressDraftJob).where(
                WordPressDraftJob.proposal_version_id == proposal.id
            )
        )
        if proposal is not None
        else None
    )
    source_content_hash = (
        proposal.config_snapshot.get("source_content_hash")
        if proposal is not None
        else None
    )
    captured_version = next(
        (
            version
            for version in versions
            if version.content_hash == source_content_hash
        ),
        None,
    )
    captured_score = next(
        (
            score
            for score in scores
            if captured_version is not None
            and score.page_version_id == captured_version.id
        ),
        None,
    )
    page_status = _monitoring_status(proposal, draft_job, scores, recommendations)
    timeline = _monitoring_events(session, events, proposal)
    projected_score = (
        _projected_score(
            captured_version.snapshot_payload,
            proposal.config_snapshot,
            proposal.package,
            proposal.rendered_html,
        )
        if captured_version is not None and proposal is not None and proposal.package
        else None
    )
    latest_check_at = next(
        (
            event.created_at
            for event in events
            if event.event_type == "page_checked"
        ),
        scores[0].created_at if scores else None,
    )
    latest_check_at = _as_utc_datetime(latest_check_at)
    return {
        "page": {
            "id": page.id,
            "title": page.title,
            "url": page.url,
            "wordpress_status": page.status,
            "status": page_status,
        },
        "latest_sync_at": latest_check_at,
        "next_check_at": (
            latest_check_at + timedelta(days=7)
            if latest_check_at is not None
            else None
        ),
        "captured_version": (
            _version_payload(captured_version)
            if captured_version is not None
            else None
        ),
        "captured_score": (
            _score_payload(captured_score) if captured_score is not None else None
        ),
        "live_changed_since_capture": bool(
            captured_version is not None
            and versions
            and versions[0].id != captured_version.id
        ),
        "versions": [
            _version_payload(version)
            for version in versions
        ],
        "scores": [
            _score_payload(score)
            for score in scores
        ],
        "projected_score": projected_score,
        "recommendations": [
            {
                "id": recommendation.id,
                "page_version_id": recommendation.page_version_id,
                "state": recommendation.state,
                "evidence": recommendation.evidence,
                "suggested_action": recommendation.suggested_action,
                "created_at": recommendation.created_at,
            }
            for recommendation in recommendations
        ],
        "events": timeline,
    }


def _monitoring_status(
    proposal: PagePackageProposal | None,
    draft_job: WordPressDraftJob | None,
    scores: list[PageScoreSnapshot],
    recommendations: list[PageRecommendation],
) -> str:
    if proposal is not None and (
        proposal.state == "draft_created"
        or (draft_job is not None and draft_job.state == "completed")
    ):
        return "draft_ready"
    if proposal is not None and proposal.state in {
        "proposed",
        "needs_attention",
        "approved",
        "draft_in_progress",
    }:
        return "proposal_ready"
    if len(scores) > 1 and scores[0].overall_score > scores[1].overall_score:
        return "improved"
    if any(item.state == "open" for item in recommendations):
        return "needs_attention"
    return "monitoring"


def _monitoring_events(
    session: Session,
    events: list[PageTimelineEvent],
    proposal: PagePackageProposal | None,
) -> list[dict[str, Any]]:
    timeline = [
        {
            "id": event.id,
            "page_version_id": event.page_version_id,
            "event_type": event.event_type,
            "payload": event.payload,
            "created_at": event.created_at,
        }
        for event in events
    ]
    if proposal is not None:
        proposal_versions = list(
            session.scalars(
                select(PagePackageProposal).where(
                    PagePackageProposal.project_id == proposal.project_id,
                    PagePackageProposal.proposal_group_id
                    == proposal.proposal_group_id,
                )
            )
        )
        proposal_ids = [version.id for version in proposal_versions]
        candidates = list(
            session.scalars(
                select(PagePackageRegenerationCandidate).where(
                    PagePackageRegenerationCandidate.proposal_group_id
                    == proposal.proposal_group_id
                )
            )
        )
        draft_jobs = list(
            session.scalars(
                select(WordPressDraftJob).where(
                    WordPressDraftJob.project_id == proposal.project_id,
                    WordPressDraftJob.proposal_version_id.in_(proposal_ids),
                )
            )
        )
        for version in proposal_versions:
            timeline.append(
                _state_event(
                    f"proposal-version-{version.id}",
                    "proposal_version_created",
                    version.created_at,
                    {
                        "proposal_id": version.id,
                        "version_number": version.version_number,
                    },
                )
            )
            if version.approved_at is not None:
                timeline.append(
                    _state_event(
                        f"proposal-approved-{version.id}",
                        "proposal_approved",
                        version.approved_at,
                        {"proposal_id": version.id},
                    )
                )
        for candidate in candidates:
            timeline.append(
                _state_event(
                    f"candidate-created-{candidate.id}",
                    "candidate_created",
                    candidate.created_at,
                    {"candidate_id": candidate.id},
                )
            )
            if candidate.status in {"accepted", "discarded", "failed"}:
                timeline.append(
                    _state_event(
                        f"candidate-{candidate.status}-{candidate.id}",
                        f"candidate_{candidate.status}",
                        candidate.updated_at,
                        {"candidate_id": candidate.id},
                    )
                )
        for job in draft_jobs:
            timeline.append(
                _state_event(
                    f"draft-requested-{job.id}",
                    "draft_requested",
                    job.created_at,
                    {"draft_job_id": job.id, "proposal_id": job.proposal_version_id},
                )
            )
            terminal_at = {
                "completed": job.completed_at,
                "failed": job.failed_at,
                "cancelled": job.cancelled_at,
            }.get(job.state)
            if terminal_at is not None:
                event_type = (
                    "draft_created"
                    if job.state == "completed"
                    else f"draft_{job.state}"
                )
                timeline.append(
                    _state_event(
                        f"draft-{job.state}-{job.id}",
                        event_type,
                        terminal_at,
                        {
                            "draft_job_id": job.id,
                            "proposal_id": job.proposal_version_id,
                        },
                    )
                )
    return sorted(
        timeline,
        key=lambda event: (_utc_timestamp(event["created_at"]), event["id"]),
        reverse=True,
    )


def _utc_timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _state_event(
    event_id: str,
    event_type: str,
    created_at: datetime,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": event_id,
        "page_version_id": None,
        "event_type": event_type,
        "payload": payload,
        "created_at": created_at,
    }


def _version_payload(version: PageObservedVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "content_hash": version.content_hash,
        "source": version.source,
        "snapshot_payload": version.snapshot_payload,
        "proposal_version_id": version.proposal_version_id,
        "draft_job_id": version.draft_job_id,
        "observed_at": version.observed_at,
        "published_at": version.published_at,
    }


def _score_payload(score: PageScoreSnapshot) -> dict[str, Any]:
    return {
        "id": score.id,
        "page_version_id": score.page_version_id,
        "overall_score": score.overall_score,
        "factors": score.factors,
        "created_at": score.created_at,
    }


def _projected_score(
    snapshot: dict,
    config_snapshot: dict,
    package: dict,
    rendered_html: str,
) -> dict[str, Any]:
    facts = dict(snapshot)
    values = dict(snapshot.get("values") or {})
    schema = config_snapshot.get("content_schema") or {}
    fields = list(schema.get("document_fields") or [])
    for block in schema.get("blocks") or []:
        fields.extend(block.get("fields") or [])
    replacements = package.get("text_replacements") or {}
    path_keys = {
        "post_title": "title",
        "seo.title": "seo_title",
        "seo.meta_description": "meta_description",
        "seo.focus_keyword": "focus_keyword",
        "seo.canonical": "canonical",
    }
    for field in fields:
        field_id = field.get("id")
        value = replacements.get(field_id)
        if isinstance(value, dict):
            value = value.get("value")
        value_key = path_keys.get(field.get("path"))
        if value_key is not None and isinstance(value, str):
            values[value_key] = value
    if rendered_html:
        values["content"] = rendered_html
    facts["values"] = values
    factors = _score_factors(facts)
    maximum = sum(factor["max_points"] for factor in factors)
    return {
        "overall_score": (
            round(100 * sum(factor["points"] for factor in factors) / maximum)
            if maximum
            else 0
        ),
        "factors": factors,
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
    if page is None:
        raise HTTPException(
            status_code=500,
            detail="Associated page not found",
        )
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
    if page is None:
        raise HTTPException(
            status_code=500,
            detail="Associated page not found",
        )
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
    if page is None:
        raise HTTPException(
            status_code=500,
            detail="Associated page not found",
        )
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
    if page is None:
        raise HTTPException(
            status_code=500,
            detail="Associated page not found",
        )
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
    if page is None:
        raise HTTPException(
            status_code=500,
            detail="Associated page not found",
        )
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
