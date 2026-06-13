from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Ga4PageRow:
    date: datetime
    page_path: str
    sessions: int
    active_users: int
    engagement_rate: float
    key_events: int
    revenue: float | None


def _optional_float(value: str) -> float | None:
    return float(value) if value.strip() else None


def map_page_report_row(
    *,
    dimension_values: list[str],
    metric_values: list[str],
) -> Ga4PageRow:
    return Ga4PageRow(
        date=datetime.strptime(dimension_values[0], "%Y%m%d"),
        page_path=dimension_values[1],
        sessions=int(float(metric_values[0] or 0)),
        active_users=int(float(metric_values[1] or 0)),
        engagement_rate=float(metric_values[2] or 0),
        key_events=int(float(metric_values[3] or 0)),
        revenue=_optional_float(metric_values[4]),
    )

