import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import crawls as crawl_routes
from app.domains.crawls.models import CrawlPage, CrawlRun, CrawlWebhookEvent
from tests.projects.conftest import ProjectFixtures


class FakeCrawler:
    def start(self, url: str, *, limit: int, metadata: dict) -> dict:
        assert url == "https://member.example"
        assert limit == 5_000
        assert metadata["project_id"] == "project-member"
        return {"id": "provider-crawl-1"}

    def status(self, crawl_id: str) -> dict:
        return {"id": crawl_id, "status": "scraping"}

    def cancel(self, crawl_id: str) -> None:
        return None

    def verify_webhook(self, body: bytes, signature: str | None) -> bool:
        if signature is None:
            return False
        expected = (
            "sha256="
            + hmac.new(
                b"webhook-secret",
                body,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(expected, signature)


class InlineCrawler(FakeCrawler):
    def start(self, url: str, *, limit: int, metadata: dict) -> dict:
        return {
            "id": "demo-crawl-1",
            "data": [
                {
                    "markdown": "# Home",
                    "links": [f"{url}/contact"],
                    "metadata": {
                        "sourceURL": url,
                        "statusCode": 200,
                        "title": "Home",
                    },
                },
                {
                    "markdown": "# Contact",
                    "links": [],
                    "metadata": {
                        "sourceURL": f"{url}/contact",
                        "statusCode": 200,
                        "title": "",
                    },
                },
            ],
        }


def test_member_can_start_crawl_with_application_cap(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    monkeypatch.setattr(crawl_routes, "crawler_provider", lambda: FakeCrawler())

    response = client.post(
        f"/projects/{projects.member_project.id}/crawls",
        json={"limit": 9_000},
    )

    assert response.status_code == 202
    assert response.json()["provider_crawl_id"] == "provider-crawl-1"
    assert response.json()["url_limit"] == 5_000


def test_inline_crawler_imports_results_and_completes_run(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    auth_as(projects.member)
    monkeypatch.setattr(crawl_routes, "crawler_provider", lambda: InlineCrawler())

    response = client.post(
        f"/projects/{projects.member_project.id}/crawls",
        json={"limit": 20},
    )

    assert response.status_code == 202
    assert response.json()["state"] == "completed"
    assert response.json()["page_count"] == 2
    results = client.get(
        f"/projects/{projects.member_project.id}/crawls/{response.json()['id']}"
    ).json()
    assert len(results["pages"]) == 2
    assert results["issues"][0]["issue_type"] == "missing_title"


def test_outsider_cannot_list_project_crawls(
    client: TestClient,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.outsider)

    response = client.get(f"/projects/{projects.member_project.id}/crawls")

    assert response.status_code == 404


def test_signed_page_webhook_is_idempotent(
    client: TestClient,
    session: Session,
    monkeypatch,
    projects: ProjectFixtures,
) -> None:
    run = CrawlRun(
        id="run-1",
        project_id=projects.member_project.id,
        provider="firecrawl",
        provider_crawl_id="provider-crawl-1",
        root_url=projects.member_project.domain,
        url_limit=500,
        state="running",
    )
    session.add(run)
    session.commit()
    monkeypatch.setattr(crawl_routes, "crawler_provider", lambda: FakeCrawler())
    payload = {
        "webhookId": "event-1",
        "type": "crawl.page",
        "id": "provider-crawl-1",
        "data": [
            {
                "markdown": "# Home",
                "links": ["https://member.example/contact"],
                "metadata": {
                    "sourceURL": "https://member.example/",
                    "statusCode": 200,
                    "title": "Home",
                },
            }
        ],
    }
    body = json.dumps(payload).encode()
    signature = (
        "sha256="
        + hmac.new(
            b"webhook-secret",
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    first = client.post(
        "/webhooks/firecrawl",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Firecrawl-Signature": signature,
        },
    )
    second = client.post(
        "/webhooks/firecrawl",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Firecrawl-Signature": signature,
        },
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert session.scalar(select(func.count(CrawlWebhookEvent.id))) == 1
    assert session.scalar(select(func.count(CrawlPage.id))) == 1
