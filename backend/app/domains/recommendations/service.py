import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.audits.models import SeoRecommendation
from app.domains.projects.models import Project
from app.domains.recommendations.provider import publishable_action_type
from app.domains.recommendations.schemas import (
    PageFacts,
    RecommendationResult,
)
from app.domains.subscriptions.models import UsageEvent
from app.domains.wordpress.models import WordPressPage

RECOMMENDATION_ENGINE_VERSION = "rules-v2-publishable-content"


class RuleBasedRecommendationGenerator:
    def generate(self, facts: PageFacts) -> RecommendationResult:
        strongest = max(facts.components, key=facts.components.get)
        options = {
            "audit": (
                "content",
                _content_recommendation(facts),
            ),
            "gsc_ctr": (
                "meta_description",
                _meta_description_recommendation(facts),
            ),
            "ranking": (
                "content",
                _content_recommendation(facts),
            ),
            "conversion": (
                "content",
                _content_recommendation(facts),
            ),
            "trend": (
                "content",
                _content_recommendation(facts),
            ),
            "importance": (
                "content",
                _content_recommendation(facts),
            ),
            "confidence": (
                "content",
                _content_recommendation(facts),
            ),
        }
        action_type, recommendation = options[strongest]
        priority = "critical" if facts.priority_score >= 85 else "high"
        return RecommendationResult(
            action_type=action_type,
            priority=priority,
            action_title=_action_title(action_type, facts),
            explanation=_action_explanation(action_type, facts),
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
    *,
    prompt_version: str | None = None,
) -> SeoRecommendation:
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "facts": facts.model_dump(),
                "prompt_version": prompt_version,
                "recommendation_engine_version": RECOMMENDATION_ENGINE_VERSION,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = session.scalar(
        select(SeoRecommendation).where(SeoRecommendation.evidence_hash == fingerprint)
    )
    if existing is not None:
        return existing
    fallback_reason = None
    try:
        generated = generator.generate(facts)
    except Exception as error:
        fallback_reason = str(error) or error.__class__.__name__
        generated = RuleBasedRecommendationGenerator().generate(facts)
    recommendation = SeoRecommendation(
        id=str(uuid4()),
        project_id=project.id,
        wordpress_page_id=page.id,
        action_type=publishable_action_type(generated.action_type),
        priority=generated.priority,
        recommendation=generated.recommendation,
        approval_state="proposed",
        evidence={
            "ids": generated.evidence,
            "rationale": generated.rationale,
            "facts": [item.model_dump() for item in facts.evidence],
            "presentation": _presentation(generated),
            **({"fallback_reason": fallback_reason[:500]} if fallback_reason else {}),
        },
        provider=generated.provider,
        model=generated.model,
        prompt_version=prompt_version,
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


def _meta_description_recommendation(facts: PageFacts) -> str:
    base = facts.current_values.get("meta_description") or facts.title
    text = str(base).strip()[:110]
    if not text:
        text = "Ontdek hoe onze specialisten je helpen met diagnose en revisie."
    return f"{text} - vraag vandaag nog deskundig advies aan.".strip()[:155]


def _presentation(generated: RecommendationResult) -> dict[str, str]:
    action_type = publishable_action_type(generated.action_type)
    return {
        "action_title": generated.action_title.strip() or _action_title(action_type),
        "explanation": generated.explanation.strip()
        or generated.rationale.strip()
        or _action_explanation(action_type),
    }


def _action_title(action_type: str, facts: PageFacts | None = None) -> str:
    page_label = _page_label(facts) if facts else ""
    if action_type == "content" and page_label:
        return f"Verbeter {page_label}"
    return {
        "seo_title": "Maak de SEO-title specifieker",
        "meta_description": "Verbeter de meta description",
        "canonical": "Controleer de canonical URL",
        "noindex": "Controleer de indexeerbaarheid",
        "content": "Verbeter de pagina-inhoud",
        "internal_links": "Verbeter interne links",
        "redirect": "Controleer redirect",
    }.get(action_type, "Verbeter de pagina")


def _action_explanation(action_type: str, facts: PageFacts | None = None) -> str:
    page_label = _page_label(facts) if facts else "deze pagina"
    return {
        "seo_title": (
            f"Een specifieke title helpt Google en bezoekers sneller begrijpen "
            f"waar {page_label} over gaat."
        ),
        "meta_description": (
            f"Een concrete meta description voor {page_label} kan de klikratio vanuit "
            "zoekresultaten verbeteren."
        ),
        "canonical": (
            f"Een correcte canonical voorkomt dat zoekmachines {page_label} "
            "verkeerd clusteren."
        ),
        "noindex": (
            f"Indexeerbaarheid bepaalt of {page_label} organisch "
            "vindbaar kan worden."
        ),
        "content": (
            f"Sterkere inhoud op {page_label} helpt bezoekers sneller kiezen "
            "en geeft zoekmachines meer context."
        ),
        "internal_links": (
            f"Betere interne links helpen bezoekers en zoekmachines {page_label} "
            "vinden."
        ),
        "redirect": (
            f"Een correcte redirect voor {page_label} voorkomt verlies van waarde "
            "en slechte gebruikerservaring."
        ),
    }.get(action_type, "Deze aanbeveling verbetert de SEO-basis van de pagina.")


def _content_recommendation(facts: PageFacts) -> str:
    current = str(facts.current_values.get("content") or "").strip()
    service_name = facts.title.strip() or "deze dienst"
    addition = (
        "\n\n<h2>Waarom deze pagina belangrijk is</h2>\n"
        f"<p>{service_name} helpt bezoekers snel te begrijpen welke oplossing "
        "past bij hun situatie. Onze specialisten beoordelen de klacht, leggen "
        "de mogelijke vervolgstappen helder uit en adviseren welke aanpak het "
        "beste aansluit.</p>\n"
        "<p>Neem contact op voor een gerichte diagnose of plan direct een "
        "afspraak met een specialist.</p>"
    )
    if current:
        return f"{current}{addition}"
    return (
        "<h2>Waarom deze pagina belangrijk is</h2>\n"
        f"<p>{service_name} helpt bezoekers snel te begrijpen welke oplossing "
        "past bij hun situatie. Onze specialisten beoordelen de klacht, leggen "
        "de mogelijke vervolgstappen helder uit en adviseren welke aanpak het "
        "beste aansluit.</p>\n"
        "<p>Neem contact op voor een gerichte diagnose of plan direct een "
        "afspraak met een specialist.</p>"
    )


def _page_label(facts: PageFacts | None) -> str:
    if facts is None:
        return ""
    title = facts.title.strip()
    for separator in (" - ", " | ", " – ", " — "):
        if separator in title:
            title = title.split(separator, 1)[0].strip()
            break
    return title or _path_label(facts.url) or "deze pagina"


def _path_label(url: str) -> str:
    path = url.rstrip("/").rsplit("/", 1)[-1]
    return " ".join(part for part in path.replace("-", " ").split() if part).title()
