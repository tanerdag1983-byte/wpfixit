from app.domains.recommendations.schemas import EvidenceItem, PageFacts
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


def test_evidence_excerpt_is_bounded() -> None:
    evidence = EvidenceItem(
        id="audit:1",
        source="audit",
        excerpt="x" * 2_000,
    )

    assert len(evidence.excerpt) == 500
