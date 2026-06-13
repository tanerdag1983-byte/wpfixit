from app.domains.ga4.mapping import map_page_report_row


def test_page_report_maps_key_events_and_optional_revenue() -> None:
    row = map_page_report_row(
        dimension_values=["20260601", "/revisie"],
        metric_values=["42", "31", "0.63", "4", ""],
    )

    assert row.sessions == 42
    assert row.active_users == 31
    assert row.engagement_rate == 0.63
    assert row.key_events == 4
    assert row.revenue is None
