from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes import wordpress as wordpress_routes
from app.domains.wordpress.client import WordPressHealth
from app.domains.wordpress.models import (
    PageObservedVersion,
    PageScoreSnapshot,
    WordPressConnection,
)


def test_sync_pages_records_current_state_monitoring(
    client: TestClient, session, auth_as, projects, monkeypatch
) -> None:
    auth_as(projects.member)
    session.add(
        WordPressConnection(
            id="monitoring-sync-connection",
            project_id=projects.member_project.id,
            site_url="https://member.example",
            encrypted_secret="encrypted",
            health_state="connected",
        )
    )
    session.commit()

    class FakeSyncClient:
        def __init__(self, site_url: str, secret: str) -> None:
            assert site_url == "https://member.example"
            assert secret == "secret"

        def health(self) -> WordPressHealth:
            return WordPressHealth(
                site_url="https://member.example",
                wordpress_version="6.8",
                plugin_version="0.2.1",
                seo_plugin="yoast",
            )

        def inventory(self) -> list[dict]:
            return [
                {
                    "id": 701,
                    "type": "page",
                    "status": "publish",
                    "title": "Transmissie revisie",
                    "slug": "transmissie-revisie",
                    "url": "https://member.example/transmissie-revisie",
                    "modified": "2026-07-30T10:00:00+00:00",
                    "content_hash": "sync-hash",
                }
            ]

        def current_state(self, object_id: int) -> dict:
            assert object_id == 701
            return {
                "content_hash": "sync-hash",
                "values": {
                    "seo_title": "Transmissie revisie",
                    "meta_description": "Deskundige transmissie revisie.",
                    "focus_keyword": "transmissie revisie",
                    "canonical": "https://member.example/transmissie-revisie",
                    "noindex": False,
                    "content": "<h1>Transmissie revisie</h1><p>Heldere uitleg.</p>",
                },
            }

    monkeypatch.setattr(wordpress_routes, "decrypt_text", lambda _: "secret")
    monkeypatch.setattr(wordpress_routes, "WordPressClient", FakeSyncClient)

    response = client.post(f"/projects/{projects.member_project.id}/sync-pages")

    assert response.status_code == 200
    assert session.scalar(select(func.count(PageObservedVersion.id))) == 1
    assert session.scalar(select(func.count(PageScoreSnapshot.id))) == 1
