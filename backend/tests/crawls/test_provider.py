from app.domains.crawls.firecrawl import FirecrawlProvider


def test_provider_never_exceeds_project_limit() -> None:
    provider = FirecrawlProvider(api_key="test-key")

    request = provider.build_start_request(
        "https://example.com",
        limit=9_000,
    )

    assert request["limit"] == 5_000
    assert request["url"] == "https://example.com"
    assert request["allowExternalLinks"] is False
    assert request["allowSubdomains"] is False
    assert request["ignoreQueryParameters"] is True


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_status_collects_all_paginated_documents() -> None:
    provider = FirecrawlProvider(api_key="test-key")
    responses = iter(
        [
            FakeResponse(
                {
                    "status": "completed",
                    "data": [{"metadata": {"sourceURL": "https://example.com"}}],
                    "next": "https://api.firecrawl.dev/v2/crawl/id?skip=1",
                }
            ),
            FakeResponse(
                {
                    "status": "completed",
                    "data": [
                        {"metadata": {"sourceURL": "https://example.com/about"}}
                    ],
                    "next": None,
                }
            ),
        ]
    )
    provider.session.get = lambda *args, **kwargs: next(responses)  # type: ignore[method-assign]

    result = provider.status("id")

    assert len(result["data"]) == 2
    assert result["next"] is None
