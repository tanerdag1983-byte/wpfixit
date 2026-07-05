import hashlib
import json


class DemoWordPressClient:
    def __init__(self) -> None:
        self._states: dict[int, dict] = {}

    def current_state(self, object_id: int) -> dict:
        return self._states.setdefault(
            object_id,
            {
                "content_hash": "demo-base-hash",
                "values": {"seo_title": "Oude SEO-title"},
            },
        )

    def apply_change(self, object_id: int, payload: dict) -> dict:
        current = self.current_state(object_id)
        if current["content_hash"] != payload["expected_content_hash"]:
            raise RuntimeError("Demo WordPress content hash conflict")
        values = {
            **current["values"],
            payload["change_type"]: payload["value"],
        }
        content_hash = hashlib.sha256(
            json.dumps(values, sort_keys=True).encode()
        ).hexdigest()
        state = {"content_hash": content_hash, "values": values}
        self._states[object_id] = state
        return state
