import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import requests

from app.core.config import get_settings


@dataclass(frozen=True)
class WordPressHealth:
    site_url: str
    wordpress_version: str | None
    plugin_version: str | None
    seo_plugin: str | None


class WordPressClient:
    def __init__(self, site_url: str, secret: str) -> None:
        self.site_url = site_url.rstrip("/")
        self.secret = secret
        self.verify_ssl = get_settings().verify_wordpress_ssl

    def _headers(self, method: str, route: str, body: str = "") -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        canonical = "\n".join(
            [
                method.upper(),
                route,
                timestamp,
                nonce,
                hashlib.sha256(body.encode()).hexdigest(),
            ]
        )
        signature = hmac.new(
            self.secret.encode(),
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "x-wp-fixpilot-timestamp": timestamp,
            "x-wp-fixpilot-nonce": nonce,
            "x-wp-fixpilot-signature": signature,
        }

    def _get(self, endpoint: str) -> dict:
        route = f"/wpfixpilot/v1/{endpoint}"
        response = requests.get(
            f"{self.site_url}/wp-json{route}",
            headers=self._headers("GET", route),
            timeout=30,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> WordPressHealth:
        data = self._get("health")
        return WordPressHealth(
            site_url=str(data["site_url"]),
            wordpress_version=data.get("wordpress_version"),
            plugin_version=data.get("plugin_version"),
            seo_plugin=data.get("seo_plugin"),
        )

    def inventory(self) -> list[dict]:
        return list(self._get("inventory").get("items", []))

