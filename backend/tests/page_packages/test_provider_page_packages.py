import json
from types import SimpleNamespace

import pytest

from app.domains.page_packages.schemas import PagePackageContext
from app.domains.recommendations.anthropic_provider import (
    AnthropicRecommendationGenerator,
)
from app.domains.recommendations.gemini_provider import GeminiRecommendationGenerator
from app.domains.recommendations.openai_compatible_provider import (
    OpenAICompatibleRecommendationGenerator,
)
from app.domains.recommendations.openai_provider import OpenAIRecommendationGenerator
from tests.page_packages.test_generation import valid_package


def context() -> PagePackageContext:
    return PagePackageContext(
        keyword="dsg revisie",
        search_volume=200,
        intent="commercial",
        company_context="Bedrijf: SHM Transmissie",
        project_domain="https://example.com",
        internal_link_candidates=[
            {"anchor": "contact", "url": "https://example.com/contact/"}
        ],
        template_slots={"hero_title": "hero.title"},
    )


def test_openai_generates_structured_page_package() -> None:
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_parsed=kwargs["text_format"].model_validate(valid_package()),
            usage=SimpleNamespace(input_tokens=20, output_tokens=40),
        )

    generator = OpenAIRecommendationGenerator(
        SimpleNamespace(responses=SimpleNamespace(parse=parse)), "gpt-test"
    )

    result = generator.generate_page_package(context())

    assert result.package.focus_keyword == "dsg versnellingsbak reviseren"
    assert result.provider == "openai"
    assert captured["text_format"].__name__ == "GeneratedPagePackage"


@pytest.mark.parametrize("provider", ["openai_compatible", "openrouter"])
def test_openai_compatible_models_generate_page_packages(monkeypatch, provider) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": json.dumps(valid_package())}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 30},
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    generator = OpenAICompatibleRecommendationGenerator(
        "https://gateway.example/v1",
        "secret",
        "model-test",
        provider=provider,
    )

    result = generator.generate_page_package(context())

    assert result.provider == provider
    assert result.output_tokens == 30


def test_anthropic_generates_page_package(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [{"text": json.dumps(valid_package())}],
                "usage": {"input_tokens": 11, "output_tokens": 31},
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    result = AnthropicRecommendationGenerator(
        "https://api.anthropic.com/v1", "secret", "claude-test"
    ).generate_page_package(context())

    assert result.provider == "anthropic"
    assert result.package.title.startswith("DSG")


def test_gemini_generates_page_package(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(valid_package())}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 12,
                    "candidatesTokenCount": 32,
                },
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    result = GeminiRecommendationGenerator(
        "https://generativelanguage.googleapis.com/v1beta",
        "secret",
        "gemini-test",
    ).generate_page_package(context())

    assert result.provider == "gemini"
    assert result.input_tokens == 12
