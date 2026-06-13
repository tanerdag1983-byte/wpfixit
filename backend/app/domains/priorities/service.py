from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.audits.models import PageAudit, SeoIssue
from app.domains.ga4.models import Ga4PagePerformance
from app.domains.gsc.models import GscPagePerformance
from app.domains.priorities.scoring import PageSignals, PriorityResult, score_pages
from app.domains.recommendations.schemas import EvidenceItem
from app.domains.wordpress.models import WordPressPage

SEVERITY_WEIGHT = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}


def project_priorities(
    session: Session,
    project_id: str,
    *,
    today: date | None = None,
) -> list[tuple[WordPressPage, PriorityResult, list[EvidenceItem]]]:
    current_day = today or date.today()
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
    audits_by_page: dict[str, PageAudit] = {}
    for audit in audits:
        audits_by_page.setdefault(audit.wordpress_page_id, audit)

    issues_by_audit: dict[str, list[SeoIssue]] = defaultdict(list)
    for issue in session.scalars(
        select(SeoIssue).where(SeoIssue.project_id == project_id)
    ):
        issues_by_audit[issue.page_audit_id].append(issue)

    gsc_by_url: dict[str, list[GscPagePerformance]] = defaultdict(list)
    for row in session.scalars(
        select(GscPagePerformance).where(
            GscPagePerformance.project_id == project_id,
            GscPagePerformance.date >= current_day - timedelta(days=90),
        )
    ):
        gsc_by_url[row.page_url.rstrip("/")].append(row)

    ga4_by_path: dict[str, list[Ga4PagePerformance]] = defaultdict(list)
    for row in session.scalars(
        select(Ga4PagePerformance).where(
            Ga4PagePerformance.project_id == project_id,
            Ga4PagePerformance.date >= current_day - timedelta(days=90),
        )
    ):
        ga4_by_path[_normalize_path(row.page_path)].append(row)

    scored: list[tuple[WordPressPage, PriorityResult, list[EvidenceItem]]] = []
    for page in pages:
        audit = audits_by_page.get(page.id)
        gsc_rows = gsc_by_url[page.url.rstrip("/")]
        ga4_rows = ga4_by_path[_normalize_path(urlsplit(page.url).path)]
        impressions = sum(row.impressions for row in gsc_rows)
        clicks = sum(row.clicks for row in gsc_rows)
        sessions = sum(row.sessions for row in ga4_rows)
        conversions = sum(row.key_events for row in ga4_rows)
        average_position = (
            sum(row.average_position * row.impressions for row in gsc_rows)
            / impressions
            if impressions
            else 0
        )
        ctr = clicks / impressions if impressions else 0
        cutoff = current_day - timedelta(days=14)
        recent_sessions = sum(
            row.sessions for row in ga4_rows if row.date >= cutoff
        )
        previous_sessions = sum(
            row.sessions for row in ga4_rows if row.date < cutoff
        )
        trend = (
            (recent_sessions - previous_sessions) / previous_sessions
            if previous_sessions
            else 0
        )
        audit_issues = issues_by_audit[audit.id] if audit else []
        issue_severity = max(
            (SEVERITY_WEIGHT.get(issue.severity, 0) for issue in audit_issues),
            default=0,
        )
        signals = PageSignals(
            url=page.url,
            seo_score=audit.score if audit else 100,
            clicks=clicks,
            impressions=impressions,
            ctr=ctr,
            average_position=average_position,
            sessions=sessions,
            conversions=conversions,
            trend=trend,
            importance=float((audit.facts if audit else {}).get("importance", 0.5)),
            issue_severity=issue_severity,
        )
        result = score_pages([signals])[0]
        evidence = _evidence(page, audit, audit_issues, result)
        scored.append((page, result, evidence))
    return sorted(
        scored,
        key=lambda item: item[1].priority_score,
        reverse=True,
    )


def _normalize_path(path: str) -> str:
    return "/" + path.strip("/") if path.strip("/") else "/"


def _evidence(
    page: WordPressPage,
    audit: PageAudit | None,
    issues: list[SeoIssue],
    result: PriorityResult,
) -> list[EvidenceItem]:
    signals = result.signals
    assert signals is not None
    evidence = [
        EvidenceItem(
            id=f"page:{page.id}",
            source="wordpress",
            excerpt=f"{page.title} ({page.status})",
        )
    ]
    if audit:
        evidence.append(
            EvidenceItem(
                id=f"audit:{audit.id}",
                source="wordpress_audit",
                excerpt=(
                    f"SEO-score {audit.score}; "
                    "issues: "
                    f"{', '.join(issue.issue_type for issue in issues) or 'geen'}"
                ),
            )
        )
    if signals.impressions:
        evidence.append(
            EvidenceItem(
                id=f"gsc:{page.id}",
                source="search_console",
                excerpt=(
                    f"{signals.clicks} clicks, {signals.impressions} impressies, "
                    f"CTR {signals.ctr:.2%}, positie {signals.average_position:.1f}"
                ),
            )
        )
    if signals.sessions:
        evidence.append(
            EvidenceItem(
                id=f"ga4:{page.id}",
                source="ga4",
                excerpt=(
                    f"{signals.sessions} sessies, {signals.conversions} conversies, "
                    f"trend {signals.trend:.1%}"
                ),
            )
        )
    return evidence
