from app.domains.wordpress.demo import DemoWordPressClient


def test_demo_wordpress_client_applies_and_tracks_changes() -> None:
    client = DemoWordPressClient()

    before = client.current_state(42)
    after = client.apply_change(
        42,
        {
            "change_type": "seo_title",
            "value": "Nieuwe SEO-title",
            "expected_content_hash": before["content_hash"],
        },
    )

    assert after["values"]["seo_title"] == "Nieuwe SEO-title"
    assert after["content_hash"] != before["content_hash"]
