import json

from app.domains.recommendations.provider import (
    ProviderGenerationError,
    system_prompt,
    validated_result,
)
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
        try:
            response = self.client.responses.parse(
                model=self.model,
                reasoning={"effort": "low"},
                input=[
                    {
                        "role": "system",
                        "content": system_prompt(self.company_context),
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
                raise ProviderGenerationError(
                    "OpenAI returned no structured recommendation"
                )
            usage = response.usage
            return validated_result(
                parsed,
                facts,
                provider="openai",
                model=self.model,
                input_tokens=getattr(usage, "input_tokens", 0),
                output_tokens=getattr(usage, "output_tokens", 0),
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError("OpenAI generation failed") from error
