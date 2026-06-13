from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(frozen=True)
class AuditPageInput:
    title: str
    slug: str
    status: str
    post_type: str
    url: str
    site_url: str


@dataclass(frozen=True)
class AuditIssueResult:
    issue_type: str
    severity: str
    message: str


@dataclass(frozen=True)
class AuditResult:
    score: int
    page_type_label: str
    issues: list[AuditIssueResult] = field(default_factory=list)


def _page_type(page: AuditPageInput) -> str:
    normalized_url = page.url.rstrip("/")
    normalized_site_url = page.site_url.rstrip("/")
    slug = page.slug.lower()
    path = urlparse(page.url).path.lower()

    if normalized_url == normalized_site_url:
        return "homepage"
    if page.status.lower() == "private":
        return "private"
    if any(term in slug or term in path for term in ("thank", "bedank")):
        return "thankyou"
    if page.post_type == "post" or slug == "blog" or "/blog/" in path:
        return "blog"
    return "page"


def audit_page(page: AuditPageInput) -> AuditResult:
    title = page.title.strip()
    slug = page.slug.strip()
    issues: list[AuditIssueResult] = []

    if not title:
        issues.append(
            AuditIssueResult(
                issue_type="missing_title",
                severity="critical",
                message="Voeg een duidelijke SEO-title toe.",
            )
        )
    elif len(title) < 30:
        issues.append(
            AuditIssueResult(
                issue_type="title_too_short",
                severity="medium",
                message="Maak de title minimaal 30 tekens.",
            )
        )
    elif len(title) > 60:
        issues.append(
            AuditIssueResult(
                issue_type="title_too_long",
                severity="medium",
                message="Kort de title in tot maximaal 60 tekens.",
            )
        )

    if not slug and page.url.rstrip("/") != page.site_url.rstrip("/"):
        issues.append(
            AuditIssueResult(
                issue_type="missing_slug",
                severity="critical",
                message="Voeg een korte en beschrijvende slug toe.",
            )
        )
    elif len(slug) > 75:
        issues.append(
            AuditIssueResult(
                issue_type="slug_too_long",
                severity="medium",
                message="Kort de slug in tot maximaal 75 tekens.",
            )
        )

    page_type_label = _page_type(page)
    if page_type_label == "private":
        issues.append(
            AuditIssueResult(
                issue_type="private_page",
                severity="high",
                message="Controleer of deze pagina bewust privé is.",
            )
        )
    if page_type_label == "thankyou":
        issues.append(
            AuditIssueResult(
                issue_type="thankyou_page",
                severity="medium",
                message="Zet deze bedankpagina op noindex.",
            )
        )

    penalties = {"critical": 30, "high": 20, "medium": 10, "low": 5}
    score = max(
        0,
        100 - sum(penalties[issue.severity] for issue in issues),
    )
    return AuditResult(
        score=score,
        page_type_label=page_type_label,
        issues=issues,
    )

