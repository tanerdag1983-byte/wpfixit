from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt_text
from app.domains.google.models import GoogleConnection
from app.domains.google.provider import GoogleProvider


def provider_from_settings() -> GoogleProvider:
    settings = get_settings()
    return GoogleProvider(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
    )


def valid_access_token(
    session: Session,
    connection: GoogleConnection,
    provider: GoogleProvider,
) -> str:
    expires_at = connection.token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at > datetime.now(UTC):
        return decrypt_text(connection.encrypted_access_token)
    if connection.encrypted_refresh_token is None:
        raise RuntimeError("Google refresh token is unavailable")

    access_token, token_expires_at = provider.refresh_access_token(
        decrypt_text(connection.encrypted_refresh_token)
    )
    connection.encrypted_access_token = encrypt_text(access_token)
    connection.token_expires_at = token_expires_at
    session.commit()
    return access_token

