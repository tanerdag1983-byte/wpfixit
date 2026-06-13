import hashlib
import hmac

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

FIRECRAWL_API = "https://api.firecrawl.dev/v2"
MAX_CRAWL_URLS = 5_000


class FirecrawlProvider:
    def __init__(
        self,
        api_key: str,
        *,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        retries = Retry(
            total=4,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("DELETE", "GET", "POST"),
        )
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def build_start_request(
        self,
        url: str,
        *,
        limit: int,
        metadata: dict | None = None,
    ) -> dict:
        payload = {
            "url": url.rstrip("/"),
            "limit": min(max(limit, 1), MAX_CRAWL_URLS),
            "crawlEntireDomain": True,
            "allowExternalLinks": False,
            "allowSubdomains": False,
            "ignoreQueryParameters": True,
            "ignoreRobotsTxt": False,
            "scrapeOptions": {
                "formats": ["markdown", "links"],
                "onlyMainContent": False,
            },
            "excludePaths": [
                "wp-admin/.*",
                r"wp-login\.php.*",
                r".*[?&]s=.*",
                r".*[?&]replytocom=.*",
            ],
        }
        if self.webhook_url:
            payload["webhook"] = {
                "url": self.webhook_url,
                "events": ["started", "page", "completed", "failed"],
                "metadata": metadata or {},
            }
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def start(self, url: str, *, limit: int, metadata: dict) -> dict:
        response = self.session.post(
            f"{FIRECRAWL_API}/crawl",
            headers=self._headers(),
            json=self.build_start_request(url, limit=limit, metadata=metadata),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def status(self, crawl_id: str) -> dict:
        response = self.session.get(
            f"{FIRECRAWL_API}/crawl/{crawl_id}",
            headers=self._headers(),
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        documents = list(result.get("data") or [])
        next_url = result.get("next")
        while next_url:
            if not str(next_url).startswith(f"{FIRECRAWL_API}/crawl/"):
                raise ValueError("Unexpected Firecrawl pagination URL")
            next_response = self.session.get(
                next_url,
                headers=self._headers(),
                timeout=60,
            )
            next_response.raise_for_status()
            page = next_response.json()
            documents.extend(page.get("data") or [])
            next_url = page.get("next")
        result["data"] = documents
        result["next"] = None
        return result

    def cancel(self, crawl_id: str) -> None:
        response = self.session.delete(
            f"{FIRECRAWL_API}/crawl/{crawl_id}",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

    def verify_webhook(self, body: bytes, signature: str | None) -> bool:
        if not self.webhook_secret or not signature:
            return False
        expected = (
            "sha256="
            + hmac.new(
                self.webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(expected, signature)
