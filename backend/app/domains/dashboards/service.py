from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.audits.models import PageAudit, SeoIssue, SeoRecommendation
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
    }

