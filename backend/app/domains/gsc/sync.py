from datetime import date

from sqlalchemy.orm import Session

from app.domains.google.models import GoogleConnection
from app.domains.google.provider import GoogleProvider
from app.domains.google.token_store import valid_access_token
from app.domains.gsc.models import GscConnection
from app.domains.gsc.service import import_page_rows, import_query_rows


def _page_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "date": date.fromisoformat(row["keys"][0]),
            "page_url": row["keys"][1],
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0),
            "position": row.get("position", 0),
        }
        for row in rows
    ]


def _query_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "date": date.fromisoformat(row["keys"][0]),
            "query": row["keys"][1],
            "page_url": row["keys"][2],
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0),
            "position": row.get("position", 0),
        }
        for row in rows
    ]


def sync_search_console(
    session: Session,
    binding: GscConnection,
    google_connection: GoogleConnection,
    provider: GoogleProvider,
    *,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    token = valid_access_token(session, google_connection, provider)
    base_payload = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dataState": "all",
    }
    pages = provider.search_analytics(
        token,
        binding.property_uri,
        {**base_payload, "dimensions": ["date", "page"]},
    )
    queries = provider.search_analytics(
        token,
        binding.property_uri,
        {**base_payload, "dimensions": ["date", "query", "page"]},
    )
    return {
        "page_rows": import_page_rows(
            session,
            binding.project_id,
            binding.property_uri,
            _page_rows(pages),
        ),
        "query_rows": import_query_rows(
            session,
            binding.project_id,
            binding.property_uri,
            _query_rows(queries),
        ),
    }

