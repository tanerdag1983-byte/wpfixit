from types import SimpleNamespace

import pytest

from app.domains.wordpress.publishing import (
    PublishConflict,
    Publisher,
    PublishNotApproved,
)


class FakeWordPress:
    def __init__(self, current_hash: str = "base-hash") -> None:
        self.hash = current_hash
        self.changes: list[dict] = []

    def current_state(self, object_id: int) -> dict:
        return {
            "content_hash": self.hash,
            "values": {"seo_title": "Oude title"},
        }

    def apply_change(self, object_id: int, payload: dict) -> dict:
        self.changes.append(payload)
        self.hash = "new-hash"
        return {
            "content_hash": self.hash,
            "values": {"seo_title": payload["value"]},
        }


def proposal(**overrides):
    values = {
        "id": "proposal-1",
        "wordpress_object_id": 42,
        "change_type": "seo_title",
        "before_value": "Oude title",
        "after_value": "Nieuwe title",
        "base_content_hash": "base-hash",
        "approval_state": "approved",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_publish_rejects_changed_wordpress_base() -> None:
    publisher = Publisher(FakeWordPress(current_hash="changed"))

    with pytest.raises(PublishConflict):
        publisher.publish(proposal())


def test_publish_requires_explicit_approval() -> None:
    publisher = Publisher(FakeWordPress())

    with pytest.raises(PublishNotApproved):
        publisher.publish(proposal(approval_state="proposed"))


def test_publish_rejects_incorrect_before_value() -> None:
    publisher = Publisher(FakeWordPress())

    with pytest.raises(PublishConflict, match="before value"):
        publisher.publish(proposal(before_value="Andere title"))


def test_publish_and_rollback_preserve_before_and_after_values() -> None:
    wordpress = FakeWordPress()
    publisher = Publisher(wordpress)

    published = publisher.publish(proposal())
    rolled_back = publisher.rollback(
        proposal(
            approval_state="published",
            base_content_hash=published.content_hash,
        ),
        published,
        confirmed=True,
    )

    assert published.before_value == "Oude title"
    assert published.after_value == "Nieuwe title"
    assert rolled_back.mutation_type == "rollback"
    assert rolled_back.before_value == "Nieuwe title"
    assert rolled_back.after_value == "Oude title"
