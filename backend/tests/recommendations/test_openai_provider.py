from types import SimpleNamespace

import pytest

from app.domains.recommendations.openai_provider import (
    OpenAIRecommendationGenerator,
)
from app.domains.recommendations.provider import ProviderGenerationError
from app.domains.recommendations.schemas import (
    EvidenceItem,
    GeneratedRecommendation,
    PageFacts,
)
from tests.page_packages.test_generation import (
    snapshot_context,
    valid_snapshot_text_package,
)


def facts() -> PageFacts:
    return PageFacts(
        url="https://example.com/revisie",
        title="Revisie",
        priority_score=88,
        components={"gsc_ctr": 18},
        evidence=[
            EvidenceItem(
                id="gsc:1",
                source="search_console",
                excerpt="10.000 impressies en een CTR van 1%.",
            )
        ],
    )


def test_company_context_is_included_in_openai_prompt() -> None:
    captured = {}
    parsed = GeneratedRecommendation(
        action_type="snippet",
        priority="high",
        recommendation="Verbeter de title.",
        rationale="De CTR is laag.",
        evidence=["gsc:1"],
    )

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_parsed=parsed,
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    generator = OpenAIRecommendationGenerator(
        client,
        "gpt-test",
        company_context="Bedrijf: Transmissiespecialist.",
    )

    generator.generate(facts())

    assert "Transmissiespecialist" in captured["input"][0]["content"]


def test_openai_generator_preserves_proposed_state_and_usage() -> None:
    parsed = GeneratedRecommendation(
        action_type="snippet",
        priority="high",
        recommendation="Verbeter de title.",
        rationale="De CTR is laag.",
        evidence=["gsc:1"],
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=lambda **kwargs: SimpleNamespace(
                output_parsed=parsed,
                usage=SimpleNamespace(input_tokens=120, output_tokens=45),
            )
        )
    )

    result = OpenAIRecommendationGenerator(client, "gpt-test").generate(facts())

    assert result.approval_state == "proposed"
    assert result.provider == "openai"
    assert result.input_tokens == 120
    assert result.output_tokens == 45


def test_openai_generator_rejects_unknown_evidence() -> None:
    parsed = GeneratedRecommendation(
        action_type="snippet",
        priority="high",
        recommendation="Verbeter de title.",
        rationale="Niet onderbouwd.",
        evidence=["unknown:1"],
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=lambda **kwargs: SimpleNamespace(
                output_parsed=parsed,
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        )
    )

    with pytest.raises(ProviderGenerationError, match="unknown evidence"):
        OpenAIRecommendationGenerator(client, "gpt-test").generate(facts())


def test_openai_generator_translates_provider_failures() -> None:
    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("secret"))
        )
    )

    with pytest.raises(
        ProviderGenerationError,
        match="OpenAI generation failed: secret",
    ):
        OpenAIRecommendationGenerator(client, "gpt-test").generate(facts())


def test_openai_snapshot_generation_uses_only_field_id_contract() -> None:
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_parsed=kwargs["text_format"].model_validate(
                valid_snapshot_text_package()
            ),
            usage=SimpleNamespace(input_tokens=8, output_tokens=13),
        )

    result = OpenAIRecommendationGenerator(
        SimpleNamespace(responses=SimpleNamespace(parse=parse)),
        "gpt-test",
    ).generate_page_package(snapshot_context())

    full_prompt = "\n".join(message["content"] for message in captured["input"])
    assert (
        '{"text_replacements":{"known-field-id":{"value":"candidate text"}}}'
        in full_prompt
    )
    for forbidden in (
        "complete nederlandse seo-landingspagina",
        "paginavorm",
        '"landing_page"',
        '"package"',
        '"hero_title"',
        '"sections"',
        '"faq"',
        '"cta"',
        '"blueprint_schema"',
    ):
        assert forbidden not in full_prompt.lower()
    assert set(captured["text_format"].model_fields) == {"text_replacements"}
    assert set(result.package.model_dump()) == {"text_replacements"}
