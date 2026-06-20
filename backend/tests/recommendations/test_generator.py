from app.domains.recommendations.provider import system_prompt, validated_result
from app.domains.recommendations.schemas import (
    EvidenceItem,
    GeneratedRecommendation,
    PageFacts,
)
from app.domains.recommendations.service import RuleBasedRecommendationGenerator


def test_recommendation_requires_evidence_and_never_auto_approves() -> None:
    generator = RuleBasedRecommendationGenerator()
    recommendation = generator.generate(
        PageFacts(
            url="https://example.com/revisie",
            title="Transmissie revisie",
            priority_score=91,
            components={"audit": 14, "gsc_ctr": 18, "conversion": 16},
            evidence=[
                EvidenceItem(
                    id="gsc:revisie",
                    source="search_console",
                    excerpt="12.400 impressies, CTR 1,2%, positie 4,6",
                )
            ],
        )
    )

    assert recommendation.evidence
    assert recommendation.approval_state == "proposed"
    assert recommendation.provider == "rules"
    assert recommendation.action_type == "meta_description"


def test_evidence_excerpt_is_bounded() -> None:
    evidence = EvidenceItem(
        id="audit:1",
        source="audit",
        excerpt="x" * 2_000,
    )

    assert len(evidence.excerpt) == 500


def test_provider_output_is_normalized_to_publishable_action_type() -> None:
    result = validated_result(
        GeneratedRecommendation(
            action_type="snippet",
            priority="high",
            recommendation="Nieuwe meta description.",
            rationale="De CTR is laag.",
            evidence=["gsc:revisie"],
        ),
        PageFacts(
            url="https://example.com/revisie",
            title="Transmissie revisie",
            priority_score=91,
            components={"gsc_ctr": 18},
            evidence=[
                EvidenceItem(
                    id="gsc:revisie",
                    source="search_console",
                    excerpt="12.400 impressies, CTR 1,2%, positie 4,6",
                )
            ],
        ),
        provider="test",
        model="model",
    )

    assert result.action_type == "meta_description"


def test_provider_output_sanitizes_presentation_and_non_content_values() -> None:
    result = validated_result(
        GeneratedRecommendation(
            action_type="seo_title",
            priority="high",
            action_title="<h2>Maak de titel concreet</h2>",
            explanation="<p>De huidige titel mist de belangrijkste dienst.</p>",
            recommendation="<strong>SHM Transmissie | Versnellingsbak revisie</strong>",
            rationale="De title bevat te weinig zoekintentie.",
            evidence=["audit:title"],
        ),
        PageFacts(
            url="https://example.com/revisie",
            title="Transmissie revisie",
            priority_score=76,
            components={"audit": 20},
            evidence=[
                EvidenceItem(
                    id="audit:title",
                    source="audit",
                    excerpt="SEO-title is te algemeen.",
                )
            ],
        ),
        provider="test",
        model="model",
    )

    assert result.action_title == "Maak de titel concreet"
    assert result.explanation == "De huidige titel mist de belangrijkste dienst."
    assert result.recommendation == "SHM Transmissie | Versnellingsbak revisie"


def test_system_prompt_prioritizes_project_prompt_with_publishable_guardrails() -> None:
    prompt = system_prompt("Extra instructie: Gebruik lokale bewijsvoering.")

    assert "volg de projectprompt" in prompt.lower()
    assert "publiceerbare-outputcontract" in prompt.lower()
    assert "Gebruik lokale bewijsvoering" in prompt


def test_rule_based_content_recommendation_is_publishable_copy() -> None:
    generator = RuleBasedRecommendationGenerator()

    recommendation = generator.generate(
        PageFacts(
            url="https://example.com/automaatbak-revisie",
            title="Automaatbak revisie",
            priority_score=88,
            components={"audit": 16, "conversion": 18},
            evidence=[
                EvidenceItem(
                    id="audit:content",
                    source="audit",
                    excerpt="De pagina mist duidelijke service-informatie.",
                )
            ],
        )
    )

    assert recommendation.action_type == "content"
    assert "Leg de dienst" not in recommendation.recommendation
    assert "benoem bewijs" not in recommendation.recommendation
    assert "duidelijke vervolgstap" not in recommendation.recommendation
    assert "Automaatbak revisie" in recommendation.recommendation
    assert recommendation.action_title == "Verbeter Automaatbak revisie"
    assert "Automaatbak revisie" in recommendation.explanation
    assert "score" not in recommendation.explanation.lower()


def test_rule_based_recommendation_uses_page_context_without_internal_jargon() -> None:
    generator = RuleBasedRecommendationGenerator()

    recommendation = generator.generate(
        PageFacts(
            url="https://example.com/over-ons",
            title="Over SHM Transmissie - Professionals sinds 1975",
            priority_score=68,
            components={"audit": 20, "confidence": 12},
            current_values={
                "seo_title": "Over SHM Transmissie - Professionals sinds 1975",
            },
            evidence=[
                EvidenceItem(
                    id="audit:title",
                    source="audit",
                    excerpt="Maak de SEO-title specifieker en minimaal 30 tekens.",
                )
            ],
        )
    )

    assert recommendation.action_title == "Verbeter Over SHM Transmissie"
    assert "component" not in recommendation.explanation.lower()
    assert "audit" not in recommendation.explanation.lower()
    assert "Over SHM Transmissie" in recommendation.explanation
