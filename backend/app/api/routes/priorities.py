from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.priorities.service import project_priorities
from app.domains.projects.service import get_project
from app.domains.recommendations.models import (
    CompanyProfile,
    OrganizationAiSettings,
)
from app.domains.recommendations.schemas import PageFacts
from app.domains.recommendations.service import (
    RuleBasedRecommendationGenerator,
    persist_recommendation,
)

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
    ai_settings = session.get(
        OrganizationAiSettings,
        project.organization_id,
    )
    company_profile = session.get(CompanyProfile, project.id)
    company_context = _company_context(company_profile)
    if ai_settings is not None:
        from openai import OpenAI

        from app.domains.recommendations.openai_provider import (
            OpenAIRecommendationGenerator,
        )

        return OpenAIRecommendationGenerator(
            OpenAI(
                api_key=decrypt_text(ai_settings.encrypted_api_key),
                base_url=ai_settings.base_url,
                max_retries=3,
            ),
            ai_settings.model,
            company_context=company_context,
        )
    settings = get_settings()
    if not settings.openai_api_key:
        return RuleBasedRecommendationGenerator()
    from openai import OpenAI

    from app.domains.recommendations.openai_provider import (
        OpenAIRecommendationGenerator,
    )

    return OpenAIRecommendationGenerator(
        OpenAI(api_key=settings.openai_api_key, max_retries=3),
        settings.openai_model,
        company_context=company_context,
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
    items = []
    for page, result, evidence in project_priorities(session, project_id)[:limit]:
        recommendation = persist_recommendation(
            session,
            project,
            page,
            PageFacts(
                url=page.url,
                title=page.title,
                priority_score=result.priority_score,
                components=result.components,
                evidence=evidence,
            ),
            generator,
        )
        items.append(
            {
                "id": recommendation.id,
                "url": page.url,
                "action_type": recommendation.action_type,
                "priority": recommendation.priority,
                "recommendation": recommendation.recommendation,
                "approval_state": recommendation.approval_state,
                "evidence": recommendation.evidence,
                "provider": recommendation.provider,
                "model": recommendation.model,
            }
        )
    return {"items": items}


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
