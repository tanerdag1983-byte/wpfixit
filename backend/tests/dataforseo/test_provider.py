import pytest

from app.domains.dataforseo.provider import DataForSeoProvider


class Response:
    status_code = 200

    def __init__(self, body: dict) -> None:
        self.body = body

    def json(self) -> dict:
        return self.body


def test_provider_rejects_failed_task_inside_successful_http_response() -> None:
    response = Response(
        {
            "status_code": 20000,
            "tasks": [
                {
                    "status_code": 40101,
                    "status_message": "Authentication failed",
                }
            ],
        }
    )

    with pytest.raises(RuntimeError, match="Authentication failed"):
        DataForSeoProvider._raise_for_failure(response)  # type: ignore[arg-type]


def test_provider_parses_keyword_metrics() -> None:
    rows = DataForSeoProvider._parse_keyword_items(
        {
            "tasks": [
                {
                    "data": {"location_code": 2528, "language_code": "nl"},
                    "result": [
                        {
                            "items": [
                                {
                                    "keyword_data": {
                                        "keyword": "automatische transmissie revisie",
                                        "keyword_info": {
                                            "search_volume": 320,
                                            "cpc": 4.25,
                                            "competition": 0.42,
                                            "competition_level": "MEDIUM",
                                        },
                                        "keyword_properties": {
                                            "keyword_difficulty": 38
                                        },
                                        "search_intent_info": {
                                            "main_intent": "commercial"
                                        },
                                    }
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    )

    assert rows[0]["keyword"] == "automatische transmissie revisie"
    assert rows[0]["search_volume"] == 320
    assert rows[0]["keyword_difficulty"] == 38
    assert rows[0]["intent"] == "commercial"


def test_keyword_ideas_sanitizes_seeds_to_dataforseo_limits(monkeypatch) -> None:
    captured: dict = {}

    def post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response(
            {
                "status_code": 20000,
                "tasks": [
                    {
                        "status_code": 20000,
                        "data": {"location_code": 2528, "language_code": "nl"},
                        "result": [{"items": []}],
                    }
                ],
            }
        )

    monkeypatch.setattr("app.domains.dataforseo.provider.requests.post", post)
    long_seed = (
        "versnellingsbak revisie handgeschakelde automatische transmissies "
        "diagnose onderhoud reparatie koppeling specialist schiedam extra"
    )

    DataForSeoProvider("login", "password").keyword_ideas(
        [long_seed, "ab", "  koppeling vervangen  ", "koppeling vervangen"]
    )

    task = captured["json"][0]
    assert task["keywords"] == [
        "versnellingsbak revisie handgeschakelde automatische transmissies "
        "diagnose",
        "koppeling vervangen",
    ]
    assert all(len(seed) <= 80 for seed in task["keywords"])
    assert all(len(seed.split()) <= 10 for seed in task["keywords"])
    assert task["closely_variants"] is True
    assert "include_seed_keyword" not in task


def test_keyword_ideas_rejects_request_without_valid_seeds(monkeypatch) -> None:
    def unexpected_post(*args, **kwargs):
        raise AssertionError("DataForSEO should not be called")

    monkeypatch.setattr(
        "app.domains.dataforseo.provider.requests.post",
        unexpected_post,
    )

    with pytest.raises(ValueError, match="valid keyword seeds"):
        DataForSeoProvider("login", "password").keyword_ideas(["", "ab"])
