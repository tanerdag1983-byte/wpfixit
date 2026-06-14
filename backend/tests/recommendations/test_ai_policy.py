import pytest

from app.domains.recommendations.policy import PolicyRecommendationGenerator
from app.domains.recommendations.provider import ProviderGenerationError
from tests.recommendations.provider_contract import facts


class Generator:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def generate(self, page_facts):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_policy_uses_primary_without_calling_fallback() -> None:
    primary = Generator(result="primary")
    fallback = Generator(result="fallback")

    result = PolicyRecommendationGenerator(primary, fallback).generate(facts())

    assert result == "primary"
    assert fallback.calls == 0


def test_policy_uses_fallback_only_for_provider_failure() -> None:
    primary = Generator(error=ProviderGenerationError("unavailable"))
    fallback = Generator(result="fallback")

    assert PolicyRecommendationGenerator(primary, fallback).generate(facts()) == (
        "fallback"
    )
    assert fallback.calls == 1


def test_policy_does_not_hide_programming_errors() -> None:
    primary = Generator(error=ValueError("bug"))
    fallback = Generator(result="fallback")

    with pytest.raises(ValueError, match="bug"):
        PolicyRecommendationGenerator(primary, fallback).generate(facts())
    assert fallback.calls == 0
