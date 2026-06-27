from typing import Any

import requests
from requests.auth import HTTPBasicAuth


class DataForSeoProvider:
    def __init__(
        self,
        login: str,
        password: str,
        *,
        base_url: str = "https://api.dataforseo.com/v3",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = HTTPBasicAuth(login, password)

    def test_connection(self) -> None:
        response = requests.get(
            f"{self.base_url}/appendix/user_data",
            auth=self.auth,
            timeout=20,
        )
        self._raise_for_failure(response)

    def keyword_ideas(
        self,
        seeds: list[str],
        *,
        location_code: int = 2528,
        language_code: str = "nl",
        limit: int = 50,
    ) -> list[dict]:
        valid_seeds = self._valid_keyword_seeds(seeds)
        if not valid_seeds:
            raise ValueError("No valid keyword seeds are available")
        response = requests.post(
            f"{self.base_url}/dataforseo_labs/google/keyword_ideas/live",
            auth=self.auth,
            json=[
                {
                    "keywords": valid_seeds,
                    "location_code": location_code,
                    "language_code": language_code,
                    "limit": limit,
                    "closely_variants": True,
                    "include_serp_info": False,
                }
            ],
            timeout=60,
        )
        self._raise_for_failure(response)
        return self._parse_keyword_items(response.json())

    @staticmethod
    def _valid_keyword_seeds(seeds: list[str], *, limit: int = 20) -> list[str]:
        valid: list[str] = []
        seen: set[str] = set()
        for seed in seeds:
            words = str(seed or "").strip().split()
            limited_words: list[str] = []
            for word in words[:10]:
                candidate = " ".join([*limited_words, word])
                if len(candidate) > 80:
                    break
                limited_words.append(word)
            normalized = " ".join(limited_words)
            key = normalized.casefold()
            if len(normalized) < 3 or key in seen:
                continue
            seen.add(key)
            valid.append(normalized)
            if len(valid) == limit:
                break
        return valid

    @staticmethod
    def _raise_for_failure(response: requests.Response) -> None:
        if not 200 <= response.status_code < 300:
            raise RuntimeError(DataForSeoProvider._failure_message(response))
        try:
            body = response.json()
        except Exception as error:
            raise RuntimeError("Provider returned an invalid response") from error
        if not isinstance(body, dict):
            raise RuntimeError("Provider returned an invalid response")
        if body.get("status_code") not in {None, 20000}:
            raise RuntimeError(DataForSeoProvider._body_failure_message(body))
        for task in body.get("tasks") or []:
            if isinstance(task, dict) and task.get("status_code") not in {
                None,
                20000,
            }:
                raise RuntimeError(DataForSeoProvider._body_failure_message(task))

    @staticmethod
    def _failure_message(response: requests.Response) -> str:
        try:
            body = response.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            message = DataForSeoProvider._body_failure_message(body)
            if message != "DataForSEO task failed":
                return message
            tasks = body.get("tasks")
            if isinstance(tasks, list) and tasks:
                task = tasks[0]
                if isinstance(task, dict):
                    return DataForSeoProvider._body_failure_message(task)
        return f"Provider returned HTTP {response.status_code}"

    @staticmethod
    def _body_failure_message(body: dict) -> str:
        message = body.get("status_message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        code = body.get("status_code")
        return f"DataForSEO task failed{f' ({code})' if code else ''}"

    @staticmethod
    def _parse_keyword_items(body: Any) -> list[dict]:
        if not isinstance(body, dict):
            return []
        parsed: list[dict] = []
        for task in body.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            task_data = task.get("data")
            defaults = task_data if isinstance(task_data, dict) else {}
            for result in task.get("result") or []:
                if not isinstance(result, dict):
                    continue
                for item in result.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    keyword_data = item.get("keyword_data")
                    keyword_data = (
                        keyword_data if isinstance(keyword_data, dict) else item
                    )
                    keyword_info = keyword_data.get("keyword_info")
                    keyword_info = (
                        keyword_info if isinstance(keyword_info, dict) else {}
                    )
                    properties = keyword_data.get("keyword_properties")
                    properties = properties if isinstance(properties, dict) else {}
                    intent_info = keyword_data.get("search_intent_info")
                    intent_info = intent_info if isinstance(intent_info, dict) else {}
                    keyword = keyword_data.get("keyword") or item.get("keyword")
                    if not isinstance(keyword, str) or not keyword.strip():
                        continue
                    parsed.append(
                        {
                            "keyword": keyword.strip(),
                            "location_code": (
                                keyword_data.get("location_code")
                                or defaults.get("location_code")
                                or 2528
                            ),
                            "language_code": (
                                keyword_data.get("language_code")
                                or defaults.get("language_code")
                                or "nl"
                            ),
                            "search_volume": keyword_info.get("search_volume"),
                            "cpc": keyword_info.get("cpc"),
                            "competition": keyword_info.get("competition"),
                            "competition_level": keyword_info.get(
                                "competition_level"
                            ),
                            "keyword_difficulty": properties.get(
                                "keyword_difficulty"
                            ),
                            "intent": intent_info.get("main_intent"),
                            "raw_payload": item,
                        }
                    )
        return parsed
