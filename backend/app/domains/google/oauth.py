import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.google.models import GoogleOAuthState

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]


class InvalidOAuthState(ValueError):
    pass


@dataclass(frozen=True)
class GoogleAuthorization:
    url: str
    state: str


@dataclass(frozen=True)
class ConsumedOAuthState:
    project_id: str
    code_verifier: str
    expires_at: datetime


class GoogleOAuthService:
    def __init__(
        self,
        *,
        session: Session,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        now=lambda: datetime.now(UTC),
    ) -> None:
        self.session = session
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.now = now

    def create_authorization(
        self,
        user_id: str,
        project_id: str,
    ) -> GoogleAuthorization:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        self.session.add(
            GoogleOAuthState(
                id=str(uuid4()),
                state_hash=hashlib.sha256(state.encode()).hexdigest(),
                user_id=user_id,
                project_id=project_id,
                code_verifier=verifier,
                expires_at=self.now() + timedelta(minutes=10),
            )
        )
        self.session.commit()
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": " ".join(GOOGLE_SCOPES),
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return GoogleAuthorization(
            url=f"{GOOGLE_AUTHORIZATION_URL}?{query}",
            state=state,
        )

    def consume_state(self, state: str, user_id: str) -> ConsumedOAuthState:
        oauth_state = self.session.scalar(
            select(GoogleOAuthState).where(
                GoogleOAuthState.state_hash
                == hashlib.sha256(state.encode()).hexdigest()
            )
        )
        now = self.now()
        if oauth_state is None or oauth_state.consumed:
            raise InvalidOAuthState("OAuth state is invalid")
        expires_at = oauth_state.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if oauth_state.user_id != user_id or expires_at <= now:
            raise InvalidOAuthState("OAuth state is invalid")

        oauth_state.consumed = True
        self.session.commit()
        return ConsumedOAuthState(
            project_id=oauth_state.project_id,
            code_verifier=oauth_state.code_verifier,
            expires_at=expires_at,
        )

