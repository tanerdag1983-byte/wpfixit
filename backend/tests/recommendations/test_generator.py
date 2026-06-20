from app.domains.recommendations.provider import validated_result
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
    assert recommendation.action_title == "Verbeter de pagina-inhoud"
    assert "score van 88" in recommendation.explanation
