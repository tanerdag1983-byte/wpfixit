from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.ga4.mapping import map_page_report_row
from app.domains.ga4.models import Ga4PagePerformance, Ga4TrafficSource


def _values(row: dict, key: str) -> list[str]:
    return [str(item.get("value", "")) for item in row.get(key, [])]


def import_page_report(
    session: Session,
    project_id: str,
    property_id: str,
    rows: list[dict],
) -> int:
    for row in rows:
        mapped = map_page_report_row(
            dimension_values=_values(row, "dimensionValues"),
            metric_values=_values(row, "metricValues"),
        )
        record = session.scalar(
            select(Ga4PagePerformance).where(
                Ga4PagePerformance.project_id == project_id,
                Ga4PagePerformance.property_id == property_id,
                Ga4PagePerformance.date == mapped.date.date(),
                Ga4PagePerformance.page_path == mapped.page_path,
            )
        )
        if record is None:
            record = Ga4PagePerformance(
                id=str(uuid4()),
                project_id=project_id,
                property_id=property_id,
                date=mapped.date.date(),
                page_path=mapped.page_path,
                sessions=mapped.sessions,
                active_users=mapped.active_users,
                engagement_rate=mapped.engagement_rate,
                key_events=mapped.key_events,
                revenue=mapped.revenue,
            )
            session.add(record)
        else:
            record.sessions = mapped.sessions
            record.active_users = mapped.active_users
            record.engagement_rate = mapped.engagement_rate
            record.key_events = mapped.key_events
            record.revenue = mapped.revenue
    session.commit()
    return len(rows)


def import_source_report(
    session: Session,
    project_id: str,
    property_id: str,
    rows: list[dict],
) -> int:
    for row in rows:
        dimensions = _values(row, "dimensionValues")
        metrics = _values(row, "metricValues")
        report_date = datetime.strptime(dimensions[0], "%Y%m%d").date()
        campaign = dimensions[3] if len(dimensions) > 3 else ""
        record = session.scalar(
            select(Ga4TrafficSource).where(
                Ga4TrafficSource.project_id == project_id,
                Ga4TrafficSource.property_id == property_id,
                Ga4TrafficSource.date == report_date,
                Ga4TrafficSource.source == dimensions[1],
                Ga4TrafficSource.medium == dimensions[2],
                Ga4TrafficSource.campaign == campaign,
            )
        )
        values = {
            "sessions": int(float(metrics[0] or 0)),
            "active_users": int(float(metrics[1] or 0)),
            "engagement_rate": float(metrics[2] or 0),
            "key_events": int(float(metrics[3] or 0)),
            "revenue": float(metrics[4]) if metrics[4].strip() else None,
        }
        if record is None:
            record = Ga4TrafficSource(
                id=str(uuid4()),
                project_id=project_id,
                property_id=property_id,
                date=report_date,
                source=dimensions[1],
                medium=dimensions[2],
                campaign=campaign,
                **values,
            )
            session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
    session.commit()
    return len(rows)

