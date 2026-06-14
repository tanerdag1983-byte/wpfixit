import json

from app.domains.recommendations.gemini_provider import (
    GeminiRecommendationGenerator,
)
from tests.recommendations.provider_contract import VALID_RESULT, facts


def test_gemini_provider_contract(monkeypatch) -> None:
    captured = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(VALID_RESULT)}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 9,
                    "candidatesTokenCount": 5,
                },
            }

    def post(url: str, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("requests.post", post)
    result = GeminiRecommendationGenerator(
        "https://generativelanguage.googleapis.com/v1beta",
        "secret",
        "gemini-test",
        company_context="Bedrijf: Specialist",
    ).generate(facts())

    assert result.provider == "gemini"
    assert result.approval_state == "proposed"
    assert result.input_tokens == 9
    assert captured["headers"]["x-goog-api-key"] == "secret"
    assert "responseSchema" in captured["json"]["generationConfig"]
    assert captured["allow_redirects"] is False
