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


def system_prompt(company_context: str) -> str:
    return (
        "Formuleer één concreet Nederlands SEO-advies. Baseer ieder feit "
        "uitsluitend op de meegeleverde evidence-ID's. Stel nooit voor om een "
        "wijziging automatisch te publiceren.\n\n"
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
    return RecommendationResult(
        **generated.model_dump(),
        approval_state="proposed",
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
