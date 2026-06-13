import json

from app.domains.recommendations.schemas import (
    GeneratedRecommendation,
    PageFacts,
    RecommendationResult,
)


class OpenAIRecommendationGenerator:
    def __init__(
        self,
        client,
        model: str,
        *,
        company_context: str = "",
    ) -> None:
        self.client = client
        self.model = model
        self.company_context = company_context[:10_000]

    def generate(self, facts: PageFacts) -> RecommendationResult:
        response = self.client.responses.parse(
            model=self.model,
            reasoning={"effort": "low"},
            input=[
                {
                    "role": "system",
                    "content": (
                        "Formuleer één concreet Nederlands SEO-advies. Baseer ieder "
                        "feit uitsluitend op de meegeleverde evidence-ID's. Stel nooit "
                        "voor om een wijziging automatisch te publiceren.\n\n"
                        f"Bedrijfscontext:\n{self.company_context or 'Niet ingesteld.'}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(facts.model_dump(), ensure_ascii=False),
                },
            ],
            text_format=GeneratedRecommendation,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("OpenAI returned no structured recommendation")
        valid_evidence = {item.id for item in facts.evidence}
        if not set(parsed.evidence).issubset(valid_evidence):
            raise ValueError("Recommendation references unknown evidence")
        usage = response.usage
        return RecommendationResult(
            **parsed.model_dump(),
            approval_state="proposed",
            provider="openai",
            model=self.model,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
        )
