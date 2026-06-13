import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.audits.models import SeoRecommendation
from app.domains.projects.models import Project
from app.domains.recommendations.schemas import (
    PageFacts,
    RecommendationResult,
)
from app.domains.subscriptions.models import UsageEvent
from app.domains.wordpress.models import WordPressPage


class RuleBasedRecommendationGenerator:
    def generate(self, facts: PageFacts) -> RecommendationResult:
        strongest = max(facts.components, key=facts.components.get)
        options = {
            "audit": (
                "technical_seo",
                "Los de belangrijkste technische en on-page fouten op.",
            ),
            "gsc_ctr": (
                "snippet",
                "Herschrijf de SEO-title en meta description voor een hogere CTR.",
            ),
            "ranking": (
                "content",
                "Verdiep de content en voeg relevante interne links toe.",
            ),
            "conversion": (
                "conversion",
                "Maak de propositie en primaire CTA duidelijker.",
            ),
            "trend": (
                "investigate_decline",
                "Vergelijk recente wijzigingen en herstel de prestatiedaling.",
            ),
            "importance": (
                "priority_review",
                "Plan een volledige SEO-review voor deze belangrijke pagina.",
            ),
            "confidence": (
                "data_quality",
                "Koppel ontbrekende databronnen voordat je grote wijzigingen doet.",
            ),
        }
        action_type, recommendation = options[strongest]
        priority = "critical" if facts.priority_score >= 85 else "high"
        return RecommendationResult(
            action_type=action_type,
            priority=priority,
            recommendation=recommendation,
            rationale=(
                f"De component '{strongest}' heeft de grootste invloed op de "
                f"prioriteitsscore van {facts.priority_score}."
            ),
            evidence=[item.id for item in facts.evidence],
            provider="rules",
            model=None,
        )


def persist_recommendation(
    session: Session,
    project: Project,
    page: WordPressPage,
    facts: PageFacts,
    generator,
) -> SeoRecommendation:
    fingerprint = hashlib.sha256(
        json.dumps(facts.model_dump(), sort_keys=True).encode()
    ).hexdigest()
    existing = session.scalar(
        select(SeoRecommendation).where(
            SeoRecommendation.evidence_hash == fingerprint
        )
    )
    if existing is not None:
        return existing
    try:
        generated = generator.generate(facts)
    except Exception:
        generated = RuleBasedRecommendationGenerator().generate(facts)
    recommendation = SeoRecommendation(
        id=str(uuid4()),
        project_id=project.id,
        wordpress_page_id=page.id,
        action_type=generated.action_type,
        priority=generated.priority,
        recommendation=generated.recommendation,
        approval_state="proposed",
        evidence={
            "ids": generated.evidence,
            "rationale": generated.rationale,
            "facts": [item.model_dump() for item in facts.evidence],
        },
        provider=generated.provider,
        model=generated.model,
        evidence_hash=fingerprint,
        input_tokens=generated.input_tokens,
        output_tokens=generated.output_tokens,
    )
    session.add(recommendation)
    token_count = generated.input_tokens + generated.output_tokens
    if token_count:
        session.add(
            UsageEvent(
                id=str(uuid4()),
                organization_id=project.organization_id,
                project_id=project.id,
                event_type="openai_tokens",
                quantity=token_count,
            )
        )
    session.commit()
    return recommendation
