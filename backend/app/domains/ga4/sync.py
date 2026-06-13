from datetime import date

from sqlalchemy.orm import Session

from app.domains.ga4.models import Ga4Connection
from app.domains.ga4.service import import_page_report, import_source_report
from app.domains.google.models import GoogleConnection
from app.domains.google.provider import GoogleProvider
from app.domains.google.token_store import valid_access_token

METRICS = [
    {"name": "sessions"},
    {"name": "activeUsers"},
    {"name": "engagementRate"},
    {"name": "keyEvents"},
    {"name": "totalRevenue"},
]


def sync_ga4(
    session: Session,
    binding: Ga4Connection,
    google_connection: GoogleConnection,
    provider: GoogleProvider,
    *,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    token = valid_access_token(session, google_connection, provider)
    base_payload = {
        "dateRanges": [
            {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
            }
        ],
        "metrics": METRICS,
    }
    page_rows = provider.run_ga4_report(
        token,
        binding.property_id,
        {
            **base_payload,
            "dimensions": [{"name": "date"}, {"name": "pagePath"}],
        },
    )
    source_rows = provider.run_ga4_report(
        token,
        binding.property_id,
        {
            **base_payload,
            "dimensions": [
                {"name": "date"},
                {"name": "sessionSource"},
                {"name": "sessionMedium"},
                {"name": "sessionCampaignName"},
            ],
        },
    )
    return {
        "page_rows": import_page_report(
            session,
            binding.project_id,
            binding.property_id,
            page_rows,
        ),
        "source_rows": import_source_report(
            session,
            binding.project_id,
            binding.property_id,
            source_rows,
        ),
    }

