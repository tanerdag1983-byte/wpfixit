from collections import Counter, defaultdict
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.audits.models import PageAudit, SeoIssue, SeoRecommendation
from app.domains.ga4.models import Ga4PagePerformance, Ga4TrafficSource
from app.domains.gsc.models import GscPagePerformance, GscQuery
from app.domains.priorities.service import project_priorities
from app.domains.wordpress.models import WordPressPage

PRIORITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def dashboard_overview(
    session: Session,
    project_id: str,
    *,
    query: str | None = None,
    priority: str | None = None,
    page_type: str | None = None,
    status: str | None = None,
    max_score: int = 100,
) -> dict[str, object]:
    pages = list(
        session.scalars(
            select(WordPressPage).where(WordPressPage.project_id == project_id)
        )
    )
    audits = list(
        session.scalars(
            select(PageAudit)
            .where(PageAudit.project_id == project_id)
            .order_by(PageAudit.created_at.desc())
        )
    )
    recommendations = list(
        session.scalars(
            select(SeoRecommendation).where(
                SeoRecommendation.project_id == project_id
            )
        )
    )
    issues = list(
        session.scalars(
            select(SeoIssue).where(SeoIssue.project_id == project_id)
        )
    )
    gsc_pages = list(
        session.scalars(
            select(GscPagePerformance).where(
                GscPagePerformance.project_id == project_id
            )
        )
    )
    ga4_pages = list(
        session.scalars(
            select(Ga4PagePerformance).where(
                Ga4PagePerformance.project_id == project_id
            )
        )
    )

    audits_by_page: dict[str, PageAudit] = {}
    for audit in audits:
        audits_by_page.setdefault(audit.wordpress_page_id, audit)

    recommendations_by_page: dict[str, list[SeoRecommendation]] = {}
    for recommendation in recommendations:
        recommendations_by_page.setdefault(
            recommendation.wordpress_page_id,
            [],
        ).append(recommendation)

    rows = []
    normalized_query = (query or "").strip().lower()
    for page in pages:
        audit = audits_by_page.get(page.id)
        if audit is None:
            continue
        page_recommendations = recommendations_by_page.get(page.id, [])
        highest_priority = max(
            (item.priority for item in page_recommendations),
            key=lambda item: PRIORITY_ORDER.get(item, 0),
            default="low",
        )
        haystack = " ".join([page.title, page.slug, page.url]).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        if priority and highest_priority != priority:
            continue
        if page_type and audit.page_type_label != page_type:
            continue
        if status and page.status != status:
            continue
        if audit.score > max_score:
            continue

        rows.append(
            {
                "wordpress_page_id": page.id,
                "title": page.title,
                "url": page.url,
                "slug": page.slug,
                "post_type": page.post_type,
                "status": page.status,
                "score": audit.score,
                "page_type_label": audit.page_type_label,
                "priority": highest_priority,
                "recommendations": [
                    item.recommendation for item in page_recommendations
                ],
            }
        )

    rows.sort(
        key=lambda item: (
            -PRIORITY_ORDER.get(str(item["priority"]), 0),
            int(item["score"]),
        )
    )
    issue_counts = Counter(issue.issue_type for issue in issues)
    trends: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "clicks": 0,
            "impressions": 0,
            "sessions": 0,
            "conversions": 0,
        }
    )
    page_performance: dict[str, dict[str, int]] = defaultdict(
        lambda: {"clicks": 0, "impressions": 0, "sessions": 0, "conversions": 0}
    )
    urls_by_path = {
        urlsplit(page.url).path.rstrip("/") or "/": page.url for page in pages
    }
    for row in gsc_pages:
        day = row.date.isoformat()
        trends[day]["clicks"] += row.clicks
        trends[day]["impressions"] += row.impressions
        page_performance[row.page_url]["clicks"] += row.clicks
        page_performance[row.page_url]["impressions"] += row.impressions
    for row in ga4_pages:
        day = row.date.isoformat()
        trends[day]["sessions"] += row.sessions
        trends[day]["conversions"] += row.key_events
        url = urls_by_path.get(row.page_path.rstrip("/") or "/", row.page_path)
        page_performance[url]["sessions"] += row.sessions
        page_performance[url]["conversions"] += row.key_events
    top_queries = list(
        session.scalars(
            select(GscQuery)
            .where(GscQuery.project_id == project_id)
            .order_by(GscQuery.clicks.desc())
            .limit(20)
        )
    )
    traffic_sources = list(
        session.scalars(
            select(Ga4TrafficSource)
            .where(Ga4TrafficSource.project_id == project_id)
            .order_by(Ga4TrafficSource.sessions.desc())
            .limit(20)
        )
    )
    priority_rows = project_priorities(session, project_id)
    ranked_pages = sorted(
        (
            {"url": url, **metrics}
            for url, metrics in page_performance.items()
        ),
        key=lambda item: (item["clicks"] + item["sessions"]),
        reverse=True,
    )
    return {
        "summary": {
            "total_pages": len(pages),
            "audited_pages": len(audits_by_page),
            "low_score_pages": sum(
                1 for audit in audits_by_page.values() if audit.score < 70
            ),
            "open_issues": sum(1 for issue in issues if issue.status == "open"),
            "recommendations": len(recommendations),
        },
        "issue_counts": dict(issue_counts),
        "pages": rows,
        "trends": [
            {"date": day, **metrics}
            for day, metrics in sorted(trends.items())
        ],
        "top_pages": ranked_pages[:20],
        "weak_pages": [
            {
                "url": page.url,
                "title": page.title,
                "priority_score": result.priority_score,
                "action": result.action,
            }
            for page, result, _ in priority_rows[:20]
        ],
        "top_queries": [
            {
                "query": row.query,
                "page_url": row.page_url,
                "clicks": row.clicks,
                "impressions": row.impressions,
                "ctr": row.ctr,
                "average_position": row.average_position,
            }
            for row in top_queries
        ],
        "traffic_sources": [
            {
                "source": row.source,
                "medium": row.medium,
                "sessions": row.sessions,
                "conversions": row.key_events,
            }
            for row in traffic_sources
        ],
        "priorities": [
            {
                "url": page.url,
                "title": page.title,
                "priority_score": result.priority_score,
                "components": result.components,
                "action": result.action,
            }
            for page, result, _ in priority_rows[:20]
        ],
    }
