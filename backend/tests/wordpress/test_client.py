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
