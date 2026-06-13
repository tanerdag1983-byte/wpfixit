from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WP_FIXPILOT_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://wpfixpilot:wpfixpilot@localhost:55432/wpfixpilot"
    )
    redis_url: str = "redis://localhost:56379/0"
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = ""
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
    encryption_key: str = ""
    verify_wordpress_ssl: bool = True
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = (
        "http://localhost:5173/auth/google/callback"
    )
    firecrawl_api_key: str = ""
    firecrawl_webhook_secret: str = ""
    firecrawl_webhook_url: str = "http://localhost:8000/webhooks/firecrawl"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    def cors_origin_list(self) -> list[str]:
        value = self.cors_origins or self.frontend_url
        return [item.strip() for item in value.split(",") if item.strip()]

    def trusted_host_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.trusted_hosts.split(",")
            if item.strip()
        ]

    def production_configuration_errors(self) -> list[str]:
        if self.environment != "production":
            return []
        required = {
            "WP_FIXPILOT_SUPABASE_URL": self.supabase_url,
            "WP_FIXPILOT_ENCRYPTION_KEY": self.encryption_key,
        }
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
