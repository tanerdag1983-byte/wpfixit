import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text
from app.core.database import engine, get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.audits.models import SeoRecommendation
from app.domains.jobs.models import Job
from app.domains.priorities.service import project_priorities
from app.domains.projects.models import Project
from app.domains.projects.service import get_project
from app.domains.recommendations.models import (
    AiConnection,
    CompanyProfile,
    ProjectAiPolicy,
)
from app.domains.recommendations.policy import PolicyRecommendationGenerator
from app.domains.recommendations.provider_factory import build_generator
from app.domains.recommendations.schemas import PageFacts
from app.domains.recommendations.service import (
    RuleBasedRecommendationGenerator,
    persist_recommendation,
)
from app.domains.wordpress.client import WordPressClient
from app.domains.wordpress.demo import DemoWordPressClient
from app.domains.wordpress.models import WordPressConnection, WordPressPage

router = APIRouter(tags=["priorities"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/projects/{project_id}/seo-priority-score")
def seo_priority_score(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    minimum_score: Annotated[int, Query(ge=0, le=100)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, list[dict]]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    items = []
    for page, result, evidence in project_priorities(session, project_id):
        if result.priority_score < minimum_score:
            continue
        signals = result.signals
        if signals is None:
            raise HTTPException(
                status_code=500,
                detail="Priority signals missing",
            )
        items.append(
            {
                "url": page.url,
                "title": page.title,
                "seo_score": signals.seo_score,
                "clicks": signals.clicks,
                "impressions": signals.impressions,
                "ctr": signals.ctr,
                "average_position": signals.average_position,
                "sessions": signals.sessions,
                "conversions": signals.conversions,
                "trend": signals.trend,
                "priority_score": result.priority_score,
                "confidence": result.confidence,
                "components": result.components,
                "action": result.action,
                "evidence": [item.model_dump() for item in evidence],
            }
        )
    return {"items": items[:limit]}


def _recommendation_generator(session: Session, project):
    company_profile = session.get(CompanyProfile, project.id)
    company_context = _company_context(company_profile)
    policy = session.get(ProjectAiPolicy, project.id)
    if policy is None:
        return RuleBasedRecommendationGenerator()
    primary = session.get(AiConnection, policy.primary_connection_id)
    if (
        primary is None
        or primary.organization_id != project.organization_id
        or not primary.enabled
    ):
        return RuleBasedRecommendationGenerator()
    primary_generator = build_generator(
        primary,
        policy.primary_model,
        company_context,
    )
    fallback_generator = None
    if policy.fallback_connection_id and policy.fallback_model:
        fallback = session.get(AiConnection, policy.fallback_connection_id)
        if (
            fallback is not None
            and fallback.organization_id == project.organization_id
            and fallback.enabled
        ):
            fallback_generator = build_generator(
                fallback,
                policy.fallback_model,
                company_context,
            )
    return PolicyRecommendationGenerator(
        primary_generator,
        fallback_generator,
    )


@router.post(
    "/projects/{project_id}/recommendations/generate",
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_recommendations(
    project_id: str,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
    user: UserDependency,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> dict[str, dict]:
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job = Job(
        id=str(uuid4()),
        project_id=project.id,
        job_type="recommendation_generation",
        state="queued",
        checkpoint={
            "limit": limit,
            "total": 0,
            "completed": 0,
            "recommendation_ids": [],
        },
    )
    session.add(job)
    session.commit()
    background_tasks.add_task(
        _run_recommendation_job,
        engine,
        job.id,
        project.id,
        limit,
    )
    return {"job": _job_payload(job)}


@router.get("/projects/{project_id}/recommendations/generation-jobs/latest")
def latest_recommendation_generation_job(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, dict | None]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job = session.scalar(
        select(Job)
        .where(
            Job.project_id == project_id,
            Job.job_type == "recommendation_generation",
        )
        .order_by(Job.created_at.desc())
    )
    return {"job": _job_payload(job) if job else None}


@router.get("/projects/{project_id}/recommendations/generation-jobs/{job_id}")
def recommendation_generation_job(
    project_id: str,
    job_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, dict]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job = session.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.project_id == project_id,
            Job.job_type == "recommendation_generation",
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": _job_payload(job)}


def _run_recommendation_job(bind, job_id: str, project_id: str, limit: int) -> None:
    with Session(bind) as session:
        job = session.get(Job, job_id)
        project = session.get(Project, project_id)
        if job is None or project is None:
            return
        try:
            _generate_recommendations_for_job(session, job, project, limit)
        except Exception as error:
            job.state = "failed"
            job.error_code = error.__class__.__name__
            job.error_message = str(error)[:2_000]
            job.completed_at = datetime.now(UTC)
            session.commit()


def _generate_recommendations_for_job(
    session: Session,
    job: Job,
    project: Project,
    limit: int,
) -> None:
    job.state = "running"
    job.started_at = datetime.now(UTC)
    job.progress = 1
    session.commit()
    generator = _recommendation_generator(session, project)
    prompt_version = _prompt_version(
        session.get(CompanyProfile, project.id),
        session.get(ProjectAiPolicy, project.id),
    )
    priorities = project_priorities(session, project.id)[:limit]
    checkpoint = dict(job.checkpoint or {})
    checkpoint.update(
        {
            "limit": limit,
            "total": len(priorities),
            "completed": 0,
            "recommendation_ids": [],
        }
    )
    job.checkpoint = checkpoint
    if not priorities:
        job.state = "completed"
        job.progress = 100
        job.completed_at = datetime.now(UTC)
        session.commit()
        return
    for index, (page, result, evidence) in enumerate(priorities, start=1):
        wordpress_context = _wordpress_context(session, project.id, page)
        recommendation = persist_recommendation(
            session,
            project,
            page,
            PageFacts(
                url=page.url,
                title=page.title,
                wordpress_object_id=page.wordpress_object_id,
                post_type=page.post_type,
                status=page.status,
                seo_plugin=wordpress_context["seo_plugin"],
                current_values=wordpress_context["current_values"],
                priority_score=result.priority_score,
                components=result.components,
                evidence=evidence,
            ),
            generator,
            prompt_version=prompt_version,
        )
        checkpoint = dict(job.checkpoint or {})
        recommendation_ids = list(checkpoint.get("recommendation_ids") or [])
        if recommendation.id not in recommendation_ids:
            recommendation_ids.append(recommendation.id)
        checkpoint.update(
            {
                "completed": index,
                "recommendation_ids": recommendation_ids,
            }
        )
        job.checkpoint = checkpoint
        job.progress = int(index / len(priorities) * 100)
        session.commit()
    job.state = "completed"
    job.progress = 100
    job.completed_at = datetime.now(UTC)
    session.commit()


def _job_payload(job: Job) -> dict[str, object]:
    checkpoint = job.checkpoint if isinstance(job.checkpoint, dict) else {}
    return {
        "id": job.id,
        "project_id": job.project_id,
        "job_type": job.job_type,
        "state": job.state,
        "progress": job.progress,
        "limit": checkpoint.get("limit"),
        "total": checkpoint.get("total", 0),
        "completed": checkpoint.get("completed", 0),
        "recommendation_ids": checkpoint.get("recommendation_ids", []),
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def _wordpress_context(
    session: Session,
    project_id: str,
    page: WordPressPage,
) -> dict[str, object]:
    client = _wordpress_client(session, project_id)
    if client is None:
        return {"seo_plugin": None, "current_values": {}}
    try:
        state = client.current_state(page.wordpress_object_id)
    except Exception:
        return {"seo_plugin": None, "current_values": {}}
    connection = session.scalar(
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
    )
    return {
        "seo_plugin": connection.seo_plugin if connection else None,
        "current_values": state.get("values", {}),
    }


def _wordpress_client(
    session: Session,
    project_id: str,
) -> WordPressClient | DemoWordPressClient | None:
    settings = get_settings()
    if settings.environment == "development" and settings.demo_mode:
        return DemoWordPressClient()
    connection = session.scalar(
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
    )
    if connection is None:
        return None
    try:
        return WordPressClient(
            connection.site_url,
            decrypt_text(connection.encrypted_secret),
        )
    except Exception:
        return None


@router.get("/projects/{project_id}/recommendations")
def list_recommendations(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, list[dict]]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    rows = list(
        session.execute(
            select(SeoRecommendation, WordPressPage)
            .join(
                WordPressPage,
                SeoRecommendation.wordpress_page_id == WordPressPage.id,
            )
            .where(SeoRecommendation.project_id == project_id)
            .order_by(SeoRecommendation.created_at.desc())
            .limit(limit)
        )
    )
    return {
        "items": [
            _recommendation_payload(recommendation, page, include_created_at=True)
            for recommendation, page in rows
        ]
    }


def _recommendation_payload(
    recommendation: SeoRecommendation,
    page: WordPressPage,
    *,
    include_created_at: bool = False,
) -> dict[str, object]:
    presentation = _recommendation_presentation(recommendation)
    generation = _recommendation_generation(recommendation)
    payload: dict[str, object] = {
        "id": recommendation.id,
        "wordpress_page_id": page.id,
        "url": page.url,
        "action_type": recommendation.action_type,
        "priority": recommendation.priority,
        "action_title": presentation["action_title"],
        "explanation": presentation["explanation"],
        "recommendation": recommendation.recommendation,
        "priority_score": _recommendation_priority_score(recommendation),
        "approval_state": recommendation.approval_state,
        "evidence": recommendation.evidence,
        "provider": recommendation.provider,
        "model": recommendation.model,
        "generation_status": generation["status"],
        "fallback_reason": generation["fallback_reason"],
        "prompt_version": recommendation.prompt_version,
    }
    if include_created_at:
        payload["created_at"] = recommendation.created_at
    return payload


def _recommendation_priority_score(recommendation: SeoRecommendation) -> int | None:
    evidence = (
        recommendation.evidence
        if isinstance(recommendation.evidence, dict)
        else {}
    )
    score = evidence.get("priority_score")
    return score if isinstance(score, int) else None


def _recommendation_generation(
    recommendation: SeoRecommendation,
) -> dict[str, str | None]:
    evidence = (
        recommendation.evidence
        if isinstance(recommendation.evidence, dict)
        else {}
    )
    fallback_reason = evidence.get("fallback_reason")
    if isinstance(fallback_reason, str) and fallback_reason.strip():
        return {
            "status": "fallback",
            "fallback_reason": fallback_reason.strip(),
        }
    return {
        "status": "rules" if recommendation.provider == "rules" else "ai",
        "fallback_reason": None,
    }


def _recommendation_presentation(
    recommendation: SeoRecommendation,
) -> dict[str, str]:
    evidence = (
        recommendation.evidence
        if isinstance(recommendation.evidence, dict)
        else {}
    )
    presentation = evidence.get("presentation")
    if isinstance(presentation, dict):
        action_title = str(presentation.get("action_title") or "").strip()
        explanation = str(presentation.get("explanation") or "").strip()
        if action_title and explanation:
            return {
                "action_title": action_title,
                "explanation": explanation,
            }
    return {
        "action_title": _fallback_action_title(recommendation.action_type),
        "explanation": str(evidence.get("rationale") or "").strip()
        or _fallback_action_explanation(recommendation.action_type),
    }


def _fallback_action_title(action_type: str) -> str:
    return {
        "seo_title": "Maak de SEO-title specifieker",
        "meta_description": "Verbeter de meta description",
        "canonical": "Controleer de canonical URL",
        "noindex": "Controleer de indexeerbaarheid",
        "content": "Verbeter de pagina-inhoud",
        "internal_links": "Verbeter interne links",
        "redirect": "Controleer redirect",
    }.get(action_type, "Verbeter de pagina")


def _fallback_action_explanation(action_type: str) -> str:
    return {
        "seo_title": (
            "Maak de titel concreter zodat zoekmachine en bezoeker de pagina "
            "sneller begrijpen."
        ),
        "meta_description": (
            "Verbeter de snippet zodat bezoekers sneller zien waarom deze pagina "
            "relevant is."
        ),
        "content": (
            "Verbeter de inhoud zodat de pagina meer context, bewijs en een "
            "duidelijke vervolgstap bevat."
        ),
        "internal_links": (
            "Verbeter interne links zodat belangrijke pagina's beter vindbaar "
            "worden."
        ),
    }.get(action_type, "Bekijk deze aanbeveling voordat je publiceert.")


def _company_context(profile: CompanyProfile | None) -> str:
    if profile is None:
        return ""
    return "\n".join(
        [
            f"Bedrijf: {profile.company_name}",
            f"Omschrijving: {profile.description}",
            f"Doelgroep: {profile.audience}",
            f"Diensten: {', '.join(profile.services)}",
            f"Tone of voice: {profile.tone_of_voice}",
            f"Extra instructie: {profile.custom_prompt}",
        ]
    )[:10_000]


def _prompt_version(
    profile: CompanyProfile | None,
    policy: ProjectAiPolicy | None = None,
) -> str | None:
    if profile is None and policy is None:
        return None
    payload = {
        "company_profile": {
            "company_name": profile.company_name if profile else "",
            "description": profile.description if profile else "",
            "audience": profile.audience if profile else "",
            "services": profile.services if profile else [],
            "tone_of_voice": profile.tone_of_voice if profile else "",
            "custom_prompt": profile.custom_prompt if profile else "",
        },
        "ai_policy": {
            "primary_connection_id": policy.primary_connection_id if policy else None,
            "primary_model": policy.primary_model if policy else None,
            "fallback_connection_id": policy.fallback_connection_id
            if policy
            else None,
            "fallback_model": policy.fallback_model if policy else None,
        },
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
