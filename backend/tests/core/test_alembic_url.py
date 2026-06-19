from app.core.alembic_url import escape_configparser_url


def test_escape_configparser_url_handles_url_encoded_password() -> None:
    url = (
        "postgresql+psycopg://postgres.example:"
        "Tren1135%21%21%40@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"
    )

    assert escape_configparser_url(url) == (
        "postgresql+psycopg://postgres.example:"
        "Tren1135%%21%%21%%40@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"
    )
