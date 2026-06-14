from app.domains.crawls.demo import DemoCrawlerProvider


def test_demo_crawler_returns_inline_pages_with_a_detectable_issue() -> None:
    result = DemoCrawlerProvider().start(
        "https://shmtransmissie.nl",
        limit=20,
        metadata={"project_id": "shm"},
    )

    assert result["id"].startswith("demo-")
    assert len(result["data"]) >= 3
    assert any(not item["metadata"].get("title") for item in result["data"])
