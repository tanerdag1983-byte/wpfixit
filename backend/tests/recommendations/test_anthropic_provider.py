import json

import pytest

from app.domains.recommendations.anthropic_provider import (
    AnthropicRecommendationGenerator,
)
from app.domains.recommendations.provider import ProviderGenerationError
from tests.page_packages.test_generation import (
    snapshot_context,
    valid_snapshot_text_package,
)
from tests.recommendations.provider_contract import VALID_RESULT, facts


class Response:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "content": [{"text": json.dumps(VALID_RESULT)}],
            "usage": {"input_tokens": 12, "output_tokens": 7},
        }


def test_anthropic_provider_contract(monkeypatch) -> None:
    captured = {}

    def post(url: str, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("requests.post", post)
    result = AnthropicRecommendationGenerator(
        "https://api.anthropic.com/v1",
        "secret",
        "claude-test",
        company_context="Bedrijf: Specialist",
    ).generate(facts())

    assert result.provider == "anthropic"
    assert result.approval_state == "proposed"
    assert result.evidence == ["gsc:1"]
    assert result.input_tokens == 12
    assert "Specialist" in captured["json"]["system"]
    assert captured["allow_redirects"] is False


def test_anthropic_rejects_unknown_evidence(monkeypatch) -> None:
    invalid = {**VALID_RESULT, "evidence": ["unknown"]}
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"content": [{"text": json.dumps(invalid)}]},
            },
        )(),
    )

    with pytest.raises(ProviderGenerationError, match="unknown evidence"):
        AnthropicRecommendationGenerator(
            "https://api.anthropic.com/v1", "secret", "claude-test"
        ).generate(facts())


def test_anthropic_snapshot_generation_accepts_only_field_id_output(
    monkeypatch,
) -> None:
    captured = {}

    class SnapshotResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "content": [
                    {"text": json.dumps(valid_snapshot_text_package())}
                ],
                "usage": {},
            }

    def post(url: str, **kwargs):
        captured.update(url=url, **kwargs)
        return SnapshotResponse()

    monkeypatch.setattr("requests.post", post)
    result = AnthropicRecommendationGenerator(
        "https://api.anthropic.com/v1",
        "secret",
        "claude-test",
    ).generate_page_package(snapshot_context())

    user_prompt = json.loads(captured["json"]["messages"][0]["content"])
    assert '"text_replacements"' in captured["json"]["system"]
    assert '"replacements"' not in captured["json"]["system"]
    assert "field_definitions" in user_prompt
    assert "blueprint_schema" not in user_prompt
    assert set(result.package.model_dump()) == {"text_replacements"}
