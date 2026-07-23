from unittest.mock import Mock

from app.domains.wordpress import client as wordpress_client
from app.domains.wordpress.client import WordPressClient


def test_blueprint_capture_allows_large_pages_more_time(monkeypatch):
    response = Mock()
    response.json.return_value = {"status": "ready"}
    post = Mock(return_value=response)
    monkeypatch.setattr(wordpress_client.requests, "post", post)

    client = WordPressClient("https://example.com", "secret")
    client.capture_blueprint({"source_page_id": 19})

    _, kwargs = post.call_args
    assert kwargs["timeout"] == 120


def test_snapshot_methods_use_authenticated_blueprint_compatibility_routes(
    monkeypatch,
):
    client = WordPressClient("https://example.com", "secret")
    post = Mock(return_value={"wordpress_snapshot_id": 91})
    get = Mock(return_value={"wordpress_snapshot_id": 91})
    delete = Mock(return_value={"deleted": True})
    monkeypatch.setattr(client, "_post", post)
    monkeypatch.setattr(client, "_get", get)
    monkeypatch.setattr(client, "_delete", delete)

    assert client.capture_snapshot({"source_page_id": 19}) == {
        "wordpress_snapshot_id": 91
    }
    assert client.snapshot(91) == {"wordpress_snapshot_id": 91}
    assert client.delete_snapshot(91) == {"deleted": True}
    post.assert_called_once_with(
        "blueprints",
        {"source_page_id": 19},
        timeout=120,
    )
    get.assert_called_once_with("blueprints/91")
    delete.assert_called_once_with("blueprints/91")
