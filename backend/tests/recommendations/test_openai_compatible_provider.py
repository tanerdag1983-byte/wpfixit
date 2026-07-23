import json

from app.domains.recommendations.openai_compatible_provider import (
    OpenAICompatibleRecommendationGenerator,
)
from tests.page_packages.test_generation import (
    snapshot_context,
    valid_snapshot_text_package,
)
from tests.recommendations.provider_contract import VALID_RESULT, facts


def test_openai_compatible_provider_contract(monkeypatch) -> None:
    captured = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [{"message": {"content": json.dumps(VALID_RESULT)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6},
            }

    def post(url: str, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("requests.post", post)
    result = OpenAICompatibleRecommendationGenerator(
        "https://gateway.example/v1",
        "secret",
        "compatible-test",
        company_context="Bedrijf: Specialist",
    ).generate(facts())

    assert result.provider == "openai_compatible"
    assert result.approval_state == "proposed"
    assert result.output_tokens == 6
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["allow_redirects"] is False


def test_openai_compatible_snapshot_generation_keeps_exact_top_level_shape(
    monkeypatch,
) -> None:
    captured = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(valid_snapshot_text_package())
                        }
                    }
                ],
                "usage": {},
            }

    def post(url: str, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("requests.post", post)
    result = OpenAICompatibleRecommendationGenerator(
        "https://gateway.example/v1",
        "secret",
        "compatible-test",
    ).generate_page_package(snapshot_context())

    prompt = captured["json"]["messages"][0]["content"]
    assert '"text_replacements"' in prompt
    assert '"replacements"' not in prompt
    assert set(result.package.model_dump()) == {"text_replacements"}
