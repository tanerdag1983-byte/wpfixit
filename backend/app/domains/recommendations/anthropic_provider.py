import json

import requests

from app.domains.page_packages.generation import (
    generation_result,
    page_package_system_prompt,
)
from app.domains.page_packages.schemas import GeneratedPagePackage, PagePackageContext
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


class AnthropicRecommendationGenerator:
    provider = "anthropic"

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
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.model,
                    "max_tokens": 800,
                    "system": system_prompt(self.company_context),
                    "messages": [
                        {
                            "role": "user",
                            "content": json.dumps(
                                facts.model_dump(), ensure_ascii=False
                            ),
                        }
                    ],
                },
                timeout=60,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            generated = GeneratedRecommendation.model_validate_json(
                payload["content"][0]["text"]
            )
            usage = payload.get("usage", {})
            return validated_result(
                generated,
                facts,
                provider="anthropic",
                model=self.model,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError("Anthropic generation failed") from error

    def generate_page_package(self, context: PagePackageContext):
        try:
            response = requests.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.model,
                    "max_tokens": 5000,
                    "system": page_package_system_prompt(context.company_context),
                    "messages": [
                        {
                            "role": "user",
                            "content": json.dumps(
                                context.model_dump(), ensure_ascii=False
                            ),
                        }
                    ],
                },
                timeout=120,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            package = GeneratedPagePackage.model_validate_json(
                payload["content"][0]["text"]
            )
            usage = payload.get("usage", {})
            return generation_result(
                package,
                provider=self.provider,
                model=self.model,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError("Anthropic page generation failed") from error
