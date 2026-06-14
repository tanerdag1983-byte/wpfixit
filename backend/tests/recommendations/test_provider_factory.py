import pytest
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.core.crypto import encrypt_text
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
from app.domains.recommendations.provider_factory import build_generator


@pytest.mark.parametrize(
    ("provider", "expected_type"),
    [
        ("openai", OpenAIRecommendationGenerator),
        ("anthropic", AnthropicRecommendationGenerator),
        ("gemini", GeminiRecommendationGenerator),
        ("openai_compatible", OpenAICompatibleRecommendationGenerator),
    ],
)
def test_factory_builds_explicit_provider(
    provider: str,
    expected_type: type,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        get_settings(), "encryption_key", Fernet.generate_key().decode()
    )
    connection = AiConnection(
        id="connection",
        organization_id="organization",
        name="Provider",
        provider=provider,
        base_url="https://provider.example/v1",
        encrypted_api_key=encrypt_text("secret"),
        enabled=True,
    )

    generator = build_generator(connection, "model-id", "company context")

    assert isinstance(generator, expected_type)
    assert generator.model == "model-id"
