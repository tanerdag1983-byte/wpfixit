from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import get_settings
from app.core.security import get_current_user


def test_current_user_verifies_supabase_jwt_with_jwks(
    monkeypatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.co")
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    captured: dict = {}

    class SigningKey:
        key = "public-key"

    class JwksClient:
        def __init__(self, url: str) -> None:
            captured["url"] = url

        def get_signing_key_from_jwt(self, token: str) -> SigningKey:
            captured["token"] = token
            return SigningKey()

    def decode(token: str, key: str, **options):
        captured["decode"] = (token, key, options)
        return {
            "sub": "user-1",
            "email": "owner@example.com",
        }

    monkeypatch.setattr("app.core.security.jwt.PyJWKClient", JwksClient)
    monkeypatch.setattr("app.core.security.jwt.decode", decode)

    user = get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="jwt-token"),
    )

    assert user.id == "user-1"
    assert captured["url"] == (
        "https://project.supabase.co/auth/v1/.well-known/jwks.json"
    )
    assert captured["decode"][2]["algorithms"] == ["ES256", "RS256"]
    assert captured["decode"][2]["audience"] == "authenticated"
    assert captured["decode"][2]["issuer"] == (
        "https://project.supabase.co/auth/v1"
    )
