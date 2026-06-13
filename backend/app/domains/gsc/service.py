from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.gsc.models import GscPagePerformance, GscQuery


def import_query_rows(
    session: Session,
    project_id: str,
    property_uri: str,
    rows: list[dict],
) -> int:
    for row in rows:
        page_url = str(row.get("page_url") or "")
        record = session.scalar(
            select(GscQuery).where(
                GscQuery.project_id == project_id,
                GscQuery.property_uri == property_uri,
                GscQuery.date == row["date"],
                GscQuery.query == row["query"],
                GscQuery.page_url == page_url,
            )
        )
        if record is None:
            record = GscQuery(
                id=str(uuid4()),
                project_id=project_id,
                property_uri=property_uri,
                date=row["date"],
                query=str(row["query"]),
                page_url=page_url,
                clicks=int(row["clicks"]),
                impressions=int(row["impressions"]),
                ctr=float(row["ctr"]),
                average_position=float(row["position"]),
            )
            session.add(record)
        else:
            record.clicks = int(row["clicks"])
            record.impressions = int(row["impressions"])
            record.ctr = float(row["ctr"])
            record.average_position = float(row["position"])
    session.commit()
    return len(rows)


def import_page_rows(
    session: Session,
    project_id: str,
    property_uri: str,
    rows: list[dict],
) -> int:
    for row in rows:
        record = session.scalar(
            select(GscPagePerformance).where(
                GscPagePerformance.project_id == project_id,
                GscPagePerformance.property_uri == property_uri,
                GscPagePerformance.date == row["date"],
                GscPagePerformance.page_url == row["page_url"],
            )
        )
        if record is None:
            record = GscPagePerformance(
                id=str(uuid4()),
                project_id=project_id,
                property_uri=property_uri,
                date=row["date"],
                page_url=str(row["page_url"]),
                clicks=int(row["clicks"]),
                impressions=int(row["impressions"]),
                ctr=float(row["ctr"]),
                average_position=float(row["position"]),
            )
            session.add(record)
        else:
            record.clicks = int(row["clicks"])
            record.impressions = int(row["impressions"])
            record.ctr = float(row["ctr"])
            record.average_position = float(row["position"])
    session.commit()
    return len(rows)

