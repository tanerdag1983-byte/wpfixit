from functools import lru_cache

from pydantic import Field
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
