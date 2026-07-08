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
from tests.page_packages.test_generation import (
    blueprint_context,
    blueprint_package,
    valid_package,
)


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


def test_openai_uses_blueprint_replacement_contract() -> None:
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_parsed=kwargs["text_format"].model_validate(
                blueprint_package().model_dump()
            ),
            usage=SimpleNamespace(input_tokens=20, output_tokens=40),
        )

    result = OpenAIRecommendationGenerator(
        SimpleNamespace(responses=SimpleNamespace(parse=parse)), "gpt-test"
    ).generate_page_package(blueprint_context())

    assert captured["text_format"].__name__ == "GeneratedBlueprintPackage"
    assert "bewaar iedere block- en field-id" in captured["input"][0]["content"].lower()
    assert result.package.replacements[0].field_id == "acf-title"


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


@pytest.mark.parametrize("provider", ["openai_compatible", "openrouter"])
def test_openai_compatible_uses_blueprint_contract(monkeypatch, provider) -> None:
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": blueprint_package().model_dump_json()
                        }
                    }
                ],
                "usage": {},
            }

    def post(*args, **kwargs):
        captured.update(kwargs.get("json", {}))
        return Response()

    monkeypatch.setattr("requests.post", post)
    result = OpenAICompatibleRecommendationGenerator(
        "https://gateway.example/v1", "secret", "model-test", provider=provider
    ).generate_page_package(blueprint_context())

    system_content = captured["messages"][0]["content"].lower()
    assert "contractschema" in system_content
    assert '"replacements"' in system_content
    assert "herhaal nooit de inputcontext" in system_content
    assert result.package.replacements[0].field_id == "acf-title"


@pytest.mark.parametrize("provider", ["openai_compatible", "openrouter"])
def test_openai_compatible_unwraps_landing_page_blueprint_payload(
    monkeypatch, provider
) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "landing_page": blueprint_package().model_dump()
                                }
                            )
                        }
                    }
                ],
                "usage": {},
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    result = OpenAICompatibleRecommendationGenerator(
        "https://gateway.example/v1", "secret", "model-test", provider=provider
    ).generate_page_package(blueprint_context())

    assert result.package.title == "DSG revisie specialist Schiedam"
    assert result.package.replacements[0].field_id == "acf-title"


@pytest.mark.parametrize("provider", ["openai_compatible", "openrouter"])
def test_openai_compatible_accepts_blueprint_package_with_extra_metadata(
    monkeypatch, provider
) -> None:
    payload = blueprint_package().model_dump()
    payload.update(
        {
            "keyword": "dsg revisie schiedam",
            "search_volume": 320,
            "intent": "commercial",
        }
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(payload)
                        }
                    }
                ],
                "usage": {},
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    result = OpenAICompatibleRecommendationGenerator(
        "https://gateway.example/v1", "secret", "model-test", provider=provider
    ).generate_page_package(blueprint_context())

    assert result.package.title == "DSG revisie specialist Schiedam"
    assert result.package.replacements[0].field_id == "acf-title"


@pytest.mark.parametrize("provider", ["openai_compatible", "openrouter"])
def test_openai_compatible_unwraps_generic_nested_blueprint_package(
    monkeypatch, provider
) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "keyword": "dsg revisie schiedam",
                                    "search_volume": 320,
                                    "package": blueprint_package().model_dump(),
                                }
                            )
                        }
                    }
                ],
                "usage": {},
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    result = OpenAICompatibleRecommendationGenerator(
        "https://gateway.example/v1", "secret", "model-test", provider=provider
    ).generate_page_package(blueprint_context())

    assert result.package.title == "DSG revisie specialist Schiedam"
    assert result.package.replacements[0].field_id == "acf-title"


def test_anthropic_uses_blueprint_contract(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [{"text": blueprint_package().model_dump_json()}],
                "usage": {},
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    result = AnthropicRecommendationGenerator(
        "https://api.anthropic.com/v1", "secret", "claude-test"
    ).generate_page_package(blueprint_context())

    assert result.package.replacements[0].field_id == "acf-title"


def test_gemini_uses_blueprint_contract(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": blueprint_package().model_dump_json()}
                            ]
                        }
                    }
                ],
                "usageMetadata": {},
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    result = GeminiRecommendationGenerator(
        "https://generativelanguage.googleapis.com/v1beta",
        "secret",
        "gemini-test",
    ).generate_page_package(blueprint_context())

    assert result.package.replacements[0].field_id == "acf-title"
