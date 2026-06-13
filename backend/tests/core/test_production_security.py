import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app


def test_app_restricts_cors_and_trusted_hosts(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "cors_origins", "https://app.example.com")
    monkeypatch.setattr(settings, "trusted_hosts", "api.example.com")
    client = TestClient(create_app())

    allowed = client.options(
        "/health",
        headers={
            "Host": "api.example.com",
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    blocked_host = client.get(
        "/health",
        headers={"Host": "attacker.example"},
    )

    assert allowed.headers["access-control-allow-origin"] == (
        "https://app.example.com"
    )
    assert blocked_host.status_code == 400


def test_production_settings_report_missing_required_secrets(
    monkeypatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "encryption_key", "")

    assert settings.production_configuration_errors() == [
        "WP_FIXPILOT_SUPABASE_URL",
        "WP_FIXPILOT_ENCRYPTION_KEY",
    ]

    with pytest.raises(RuntimeError, match="WP_FIXPILOT_SUPABASE_URL"):
        create_app()


def test_render_postgres_url_uses_installed_psycopg_driver() -> None:
    settings = Settings(
        database_url="postgresql://user:password@db.example.com/app",
    )

    assert settings.database_url == (
        "postgresql+psycopg://user:password@db.example.com/app"
    )
