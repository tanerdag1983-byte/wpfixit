from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domains.audits.engine import AuditPageInput, audit_page
from app.domains.audits.models import PageAudit, SeoIssue, SeoRecommendation
from app.domains.projects.models import Project
from app.domains.wordpress.models import WordPressPage

ISSUE_RECOMMENDATIONS = {
    "missing_title": (
        "seo_title",
        "critical",
        "Schrijf een duidelijke SEO-title met het primaire zoekwoord.",
    ),
    "title_too_short": (
        "seo_title",
        "medium",
        "Maak de SEO-title specifieker en minimaal 30 tekens.",
    ),
    "title_too_long": (
        "seo_title",
        "medium",
        "Kort de SEO-title in tot maximaal 60 tekens.",
    ),
    "missing_slug": (
        "slug",
        "critical",
        "Voeg een korte en beschrijvende slug toe.",
    ),
    "slug_too_long": (
        "slug",
        "medium",
        "Kort de slug in tot maximaal 75 tekens.",
    ),
    "private_page": (
        "visibility",
        "high",
        "Controleer of deze pagina bewust privé is.",
    ),
    "thankyou_page": (
        "noindex",
        "medium",
        "Zet deze bedankpagina op noindex.",
    ),
}


def audit_project(session: Session, project: Project) -> int:
    pages = list(
        session.scalars(
            select(WordPressPage).where(WordPressPage.project_id == project.id)
        )
    )
    session.execute(delete(SeoRecommendation).where(
        SeoRecommendation.project_id == project.id
    ))
    session.execute(delete(SeoIssue).where(SeoIssue.project_id == project.id))
    session.execute(delete(PageAudit).where(PageAudit.project_id == project.id))

    for page in pages:
        result = audit_page(
            AuditPageInput(
                title=page.title,
                slug=page.slug,
                status=page.status,
                post_type=page.post_type,
                url=page.url,
                site_url=project.domain,
            )
        )
        audit = PageAudit(
            id=str(uuid4()),
            project_id=project.id,
            wordpress_page_id=page.id,
            score=result.score,
            page_type_label=result.page_type_label,
            facts={
                "title_length": len(page.title.strip()),
                "slug_length": len(page.slug.strip()),
            },
        )
        session.add(audit)
        for issue_result in result.issues:
            session.add(
                SeoIssue(
                    id=str(uuid4()),
                    project_id=project.id,
                    page_audit_id=audit.id,
                    issue_type=issue_result.issue_type,
                    severity=issue_result.severity,
                    message=issue_result.message,
                )
            )
            action, priority, recommendation = ISSUE_RECOMMENDATIONS[
                issue_result.issue_type
            ]
            session.add(
                SeoRecommendation(
                    id=str(uuid4()),
                    project_id=project.id,
                    wordpress_page_id=page.id,
                    action_type=action,
                    priority=priority,
                    recommendation=recommendation,
                    evidence={"issue_type": issue_result.issue_type},
                )
            )

    session.commit()
    return len(pages)

