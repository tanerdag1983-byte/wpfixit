from app.domains.priorities.scoring import PageSignals, score_pages


def test_high_impressions_low_ctr_and_low_seo_score_rank_first() -> None:
    results = score_pages(
        [
            PageSignals(
                url="https://example.com/a",
                seo_score=45,
                impressions=20_000,
                clicks=200,
                ctr=0.01,
                average_position=4.6,
                sessions=1_500,
                conversions=8,
                trend=-0.12,
                importance=0.9,
            ),
            PageSignals(
                url="https://example.com/b",
                seo_score=80,
                impressions=400,
                clicks=32,
                ctr=0.08,
                average_position=3.2,
                sessions=120,
                conversions=8,
                trend=0.08,
                importance=0.4,
            ),
        ]
    )

    assert results[0].url == "https://example.com/a"
    assert results[0].priority_score > results[1].priority_score
    assert 0 <= results[0].priority_score <= 100
    assert results[0].components["gsc_ctr"] > results[1].components["gsc_ctr"]


def test_score_explains_low_conversion_and_decline() -> None:
    result = score_pages(
        [
            PageSignals(
                url="https://example.com/service",
                seo_score=72,
                sessions=2_000,
                conversions=3,
                trend=-0.25,
                importance=1,
            )
        ]
    )[0]

    assert result.components["conversion"] > 10
    assert result.components["trend"] > 5
    assert result.confidence > 0
    assert result.action
