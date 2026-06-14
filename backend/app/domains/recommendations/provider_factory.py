from openai import OpenAI

from app.core.crypto import decrypt_text
from app.domains.recommendations.anthropic_provider import (
    AnthropicRecommendationGenerator,
)
from app.domains.recommendations.gemini_provider import (
    GeminiRecommendationGenerator,
)
from app.domains.recommendations.models import AiConnection
from app.domains.recommendations.openai_compatible_provider import (
    OpenAICompatibleRecommendationGenerator,
)
from app.domains.recommendations.openai_provider import (
    OpenAIRecommendationGenerator,
)
from app.domains.recommendations.provider import ProviderGenerationError


def build_generator(
    connection: AiConnection,
    model: str,
    company_context: str,
):
    if not connection.enabled:
        raise ProviderGenerationError("AI connection is disabled")
    api_key = decrypt_text(connection.encrypted_api_key)
    if connection.provider == "openai":
        return OpenAIRecommendationGenerator(
            OpenAI(
                api_key=api_key,
                base_url=connection.base_url,
                max_retries=3,
            ),
            model,
            company_context=company_context,
        )
    if connection.provider == "anthropic":
        return AnthropicRecommendationGenerator(
            connection.base_url,
            api_key,
            model,
            company_context=company_context,
        )
    if connection.provider == "gemini":
        return GeminiRecommendationGenerator(
            connection.base_url,
            api_key,
            model,
            company_context=company_context,
        )
    if connection.provider == "openai_compatible":
        return OpenAICompatibleRecommendationGenerator(
            connection.base_url,
            api_key,
            model,
            company_context=company_context,
        )
    raise ProviderGenerationError("Unsupported AI provider")
