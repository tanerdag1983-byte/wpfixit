import json

import requests

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


class GeminiRecommendationGenerator:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        company_context: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.company_context = company_context

    def generate(self, facts: PageFacts) -> RecommendationResult:
        try:
            response = requests.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json={
                    "systemInstruction": {
                        "parts": [{"text": system_prompt(self.company_context)}]
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": json.dumps(
                                        facts.model_dump(),
                                        ensure_ascii=False,
                                    )
                                }
                            ],
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseSchema": (GeneratedRecommendation.model_json_schema()),
                    },
                },
                timeout=60,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            generated = GeneratedRecommendation.model_validate_json(text)
            usage = payload.get("usageMetadata", {})
            return validated_result(
                generated,
                facts,
                provider="gemini",
                model=self.model,
                input_tokens=int(usage.get("promptTokenCount", 0)),
                output_tokens=int(usage.get("candidatesTokenCount", 0)),
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError("Gemini generation failed") from error
