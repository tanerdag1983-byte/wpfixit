import json

import requests

from app.domains.page_packages.generation import (
    generation_result,
    page_package_contract,
    page_package_system_prompt,
)
from app.domains.page_packages.schemas import PagePackageContext
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
    provider = "gemini"

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

    def generate_page_package(self, context: PagePackageContext):
        try:
            response = requests.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json={
                    "systemInstruction": {
                        "parts": [
                            {
                                "text": page_package_system_prompt(context)
                            }
                        ]
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": json.dumps(
                                        context.model_dump(), ensure_ascii=False
                                    )
                                }
                            ],
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseSchema": page_package_contract(
                            context
                        ).model_json_schema(),
                    },
                },
                timeout=120,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            package = page_package_contract(context).model_validate_json(
                payload["candidates"][0]["content"]["parts"][0]["text"]
            )
            usage = payload.get("usageMetadata", {})
            return generation_result(
                package,
                provider=self.provider,
                model=self.model,
                input_tokens=int(usage.get("promptTokenCount", 0)),
                output_tokens=int(usage.get("candidatesTokenCount", 0)),
                context=context,
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError("Gemini page generation failed") from error
