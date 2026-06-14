from app.domains.recommendations.schemas import EvidenceItem, PageFacts


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


VALID_RESULT = {
    "action_type": "snippet",
    "priority": "high",
    "recommendation": "Verbeter de title.",
    "rationale": "De CTR is laag.",
    "evidence": ["gsc:1"],
}
