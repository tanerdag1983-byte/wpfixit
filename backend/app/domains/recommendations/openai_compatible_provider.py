import json

import requests
from pydantic import ValidationError

from app.domains.page_packages.generation import (
    generation_result,
    page_package_contract,
    page_package_system_prompt,
)
from app.domains.page_packages.schemas import PagePackageContext
from app.domains.recommendations.provider import (
    ProviderGenerationError,
    provider_error_message,
    system_prompt,
    validated_result,
)
from app.domains.recommendations.schemas import (
    GeneratedRecommendation,
    PageFacts,
    RecommendationResult,
)


def _parse_page_package_content(content: str, context: PagePackageContext):
    contract = page_package_contract(context)
    try:
        return contract.model_validate_json(content)
    except ValidationError:
        if context.blueprint_schema is None:
            raise
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise
        for key in ("landing_page", "page_package", "blueprint_package"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return contract.model_validate(nested)
        raise


class OpenAICompatibleRecommendationGenerator:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        company_context: str = "",
        provider: str = "openai_compatible",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.company_context = company_context
        self.provider = provider

    def generate_page_package(self, context: PagePackageContext):
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": page_package_system_prompt(context),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                context.model_dump(), ensure_ascii=False
                            ),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=120,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            package = _parse_page_package_content(
                payload["choices"][0]["message"]["content"],
                context,
            )
            usage = payload.get("usage", {})
            return generation_result(
                package,
                provider=self.provider,
                model=self.model,
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                context=context,
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError(
                provider_error_message(
                    "OpenAI-compatible page generation failed",
                    error,
                )
            ) from error

    def generate(self, facts: PageFacts) -> RecommendationResult:
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt(self.company_context),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                facts.model_dump(), ensure_ascii=False
                            ),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            generated = GeneratedRecommendation.model_validate_json(
                payload["choices"][0]["message"]["content"]
            )
            usage = payload.get("usage", {})
            return validated_result(
                generated,
                facts,
                provider=self.provider,
                model=self.model,
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError(
                provider_error_message(
                    "OpenAI-compatible generation failed",
                    error,
                )
            ) from error
