import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.audits.models import SeoRecommendation
from app.domains.priorities.service import project_priorities
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
        assert signals is not None
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


@router.post("/projects/{project_id}/recommendations/generate")
def generate_recommendations(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> dict[str, list[dict]]:
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    generator = _recommendation_generator(session, project)
    prompt_version = _prompt_version(session.get(CompanyProfile, project.id))
    items = []
    for page, result, evidence in project_priorities(session, project_id)[:limit]:
        wordpress_context = _wordpress_context(session, project_id, page)
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
        items.append(
            {
                "id": recommendation.id,
                "wordpress_page_id": page.id,
                "url": page.url,
                "action_type": recommendation.action_type,
                "priority": recommendation.priority,
                "recommendation": recommendation.recommendation,
                "approval_state": recommendation.approval_state,
                "evidence": recommendation.evidence,
                "provider": recommendation.provider,
                "model": recommendation.model,
                "prompt_version": recommendation.prompt_version,
            }
        )
    return {"items": items}


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
            {
                "id": recommendation.id,
                "wordpress_page_id": page.id,
                "url": page.url,
                "action_type": recommendation.action_type,
                "priority": recommendation.priority,
                "recommendation": recommendation.recommendation,
                "approval_state": recommendation.approval_state,
                "evidence": recommendation.evidence,
                "provider": recommendation.provider,
                "model": recommendation.model,
                "prompt_version": recommendation.prompt_version,
                "created_at": recommendation.created_at,
            }
            for recommendation, page in rows
        ]
    }


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


def _prompt_version(profile: CompanyProfile | None) -> str | None:
    if profile is None:
        return None
    payload = {
        "company_name": profile.company_name,
        "description": profile.description,
        "audience": profile.audience,
        "services": profile.services,
        "tone_of_voice": profile.tone_of_voice,
        "custom_prompt": profile.custom_prompt,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
