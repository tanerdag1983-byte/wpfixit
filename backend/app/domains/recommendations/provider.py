from typing import Protocol

from app.domains.recommendations.schemas import (
    GeneratedRecommendation,
    PageFacts,
    RecommendationResult,
)


class ProviderGenerationError(RuntimeError):
    pass


class RecommendationGenerator(Protocol):
    def generate(self, facts: PageFacts) -> RecommendationResult: ...


PUBLISHABLE_ACTION_TYPES = {
    "seo_title",
    "meta_description",
    "canonical",
    "noindex",
    "content",
    "internal_links",
    "redirect",
}

ACTION_TYPE_ALIASES = {
    "snippet": "meta_description",
    "technical_seo": "content",
    "conversion": "content",
    "investigate_decline": "content",
    "priority_review": "content",
    "data_quality": "content",
}


def publishable_action_type(action_type: str) -> str:
    if action_type in PUBLISHABLE_ACTION_TYPES:
        return action_type
    return ACTION_TYPE_ALIASES.get(action_type, "content")


def system_prompt(company_context: str) -> str:
    return (
        "Formuleer één concrete Nederlandse SEO-wijziging als JSON. Baseer ieder "
        "feit uitsluitend op de meegeleverde evidence-ID's en current_values. "
        "Gebruik action_type alleen als één van: seo_title, meta_description, "
        "canonical, noindex, content, internal_links, redirect. Geef action_title "
        "als korte dashboardtitel zonder HTML. Geef explanation als één korte "
        "zin waarom deze wijziging nodig is. Het veld recommendation moet de "
        "exacte nieuwe waarde zijn die na menselijke goedkeuring naar WordPress "
        "kan worden geschreven, geen algemene instructie. Voor content mag "
        "recommendation veilige HTML bevatten; action_title en explanation nooit. "
        "Stel nooit voor om een wijziging automatisch te publiceren.\n\n"
        f"Bedrijfscontext:\n{company_context[:10_000] or 'Niet ingesteld.'}"
    )


def validated_result(
    generated: GeneratedRecommendation,
    facts: PageFacts,
    *,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> RecommendationResult:
    valid_evidence = {item.id for item in facts.evidence}
    if not set(generated.evidence).issubset(valid_evidence):
        raise ProviderGenerationError("Provider referenced unknown evidence")
    payload = generated.model_dump()
    payload["action_type"] = publishable_action_type(generated.action_type)
    return RecommendationResult(
        **payload,
        approval_state="proposed",
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
