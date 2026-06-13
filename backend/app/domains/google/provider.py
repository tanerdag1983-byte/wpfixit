from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import requests

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SEARCH_CONSOLE_API = "https://searchconsole.googleapis.com/webmasters/v3"


@dataclass(frozen=True)
class GoogleTokenResult:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scopes: str
    subject: str
    email: str


class GoogleProvider:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def exchange_code(self, code: str, code_verifier: str) -> GoogleTokenResult:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
            },
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()
        user_response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
            timeout=30,
        )
        user_response.raise_for_status()
        user = user_response.json()
        return GoogleTokenResult(
            access_token=str(token_data["access_token"]),
            refresh_token=token_data.get("refresh_token"),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=int(token_data.get("expires_in", 3600))),
            scopes=str(token_data.get("scope", "")),
            subject=str(user["sub"]),
            email=str(user["email"]),
        )

    def refresh_access_token(self, refresh_token: str) -> tuple[str, datetime]:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()
        return (
            str(token_data["access_token"]),
            datetime.now(UTC)
            + timedelta(seconds=int(token_data.get("expires_in", 3600))),
        )

    def list_search_console_properties(self, access_token: str) -> list[dict]:
        response = requests.get(
            f"{SEARCH_CONSOLE_API}/sites",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        response.raise_for_status()
        return list(response.json().get("siteEntry", []))

    def search_analytics(
        self,
        access_token: str,
        property_uri: str,
        payload: dict,
    ) -> list[dict]:
        rows: list[dict] = []
        start_row = 0
        while True:
            request_payload = {
                **payload,
                "rowLimit": 25_000,
                "startRow": start_row,
            }
            response = requests.post(
                f"{SEARCH_CONSOLE_API}/sites/"
                f"{quote(property_uri, safe='')}/searchAnalytics/query",
                headers={"Authorization": f"Bearer {access_token}"},
                json=request_payload,
                timeout=60,
            )
            response.raise_for_status()
            page = list(response.json().get("rows", []))
            rows.extend(page)
            if len(page) < 25_000:
                return rows
            start_row += len(page)

