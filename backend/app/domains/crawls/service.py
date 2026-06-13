import hashlib
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.crawls.models import (
    CrawlIssue,
    CrawlPage,
    CrawlRun,
    CrawlWebhookEvent,
)


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            parts.query,
            "",
        )
    )


def record_webhook_event(
    session: Session,
    webhook_id: str,
    payload: dict,
) -> bool:
    existing = session.scalar(
        select(CrawlWebhookEvent).where(CrawlWebhookEvent.webhook_id == webhook_id)
    )
    if existing is not None:
        return False
    session.add(
        CrawlWebhookEvent(
            id=str(uuid4()),
            webhook_id=webhook_id,
            payload=payload,
        )
    )
    session.flush()
    return True


def import_page(
    session: Session,
    run: CrawlRun,
    document: dict,
) -> CrawlPage:
    metadata = document.get("metadata") or {}
    source_url = str(metadata.get("sourceURL") or metadata.get("url") or "")
    page = session.scalar(
        select(CrawlPage).where(
            CrawlPage.crawl_run_id == run.id,
            CrawlPage.url == source_url,
        )
    )
    markdown = str(document.get("markdown") or "")
    robots = str(metadata.get("robots") or "")
    if page is None:
        page = CrawlPage(
            id=str(uuid4()),
            crawl_run_id=run.id,
            project_id=run.project_id,
            url=source_url,
            normalized_url=normalize_url(source_url),
        )
        session.add(page)
        run.page_count += 1
    page.status_code = metadata.get("statusCode")
    page.title = metadata.get("title")
    page.description = metadata.get("description")
    page.canonical_url = metadata.get("canonicalUrl")
    page.robots = robots or None
    page.markdown = markdown
    page.content_hash = hashlib.sha256(markdown.encode()).hexdigest()
    page.indexable = "noindex" not in robots.lower()
    page.raw_metadata = metadata
    session.flush()
    _replace_links(session, page, document.get("links") or [])
    redirect_chain = metadata.get("redirectChain") or []

    if page.status_code and page.status_code >= 400:
        _add_issue(
            session,
            run,
            page,
            "http_error",
            "high",
            f"Pagina retourneert HTTP {page.status_code}.",
            {"status_code": page.status_code},
        )
    elif page.status_code and 300 <= page.status_code < 400:
        _add_issue(
            session,
            run,
            page,
            "redirect",
            "medium",
            f"Pagina retourneert een redirect ({page.status_code}).",
            {"status_code": page.status_code},
        )
    if len(redirect_chain) > 1:
        _add_issue(
            session,
            run,
            page,
            "redirect_chain",
            "medium",
            "De URL doorloopt meerdere redirects.",
            {"redirect_chain": redirect_chain},
        )
    if not page.title:
        _add_issue(
            session,
            run,
            page,
            "missing_title",
            "high",
            "De gecrawlde pagina heeft geen title.",
            {},
        )
    if page.canonical_url and normalize_url(
        urljoin(source_url, page.canonical_url)
    ) != normalize_url(source_url):
        _add_issue(
            session,
            run,
            page,
            "canonical_conflict",
            "medium",
            "Canonical verwijst naar een andere URL.",
            {"canonical_url": page.canonical_url},
        )
    if not page.indexable:
        _add_issue(
            session,
            run,
            page,
            "noindex",
            "medium",
            "De gecrawlde pagina is uitgesloten met noindex.",
            {"robots": page.robots},
        )
    session.commit()
    return page


def complete_run(session: Session, run: CrawlRun) -> None:
    analyze_run(session, run)
    run.state = "completed"
    run.completed_at = datetime.now(UTC)
    session.commit()


def analyze_run(session: Session, run: CrawlRun) -> None:
    pages = list(
        session.scalars(select(CrawlPage).where(CrawlPage.crawl_run_id == run.id))
    )
    pages_by_url = {page.normalized_url: page for page in pages}
    for field, issue_type in (
        (CrawlPage.title, "duplicate_title"),
        (CrawlPage.description, "duplicate_description"),
    ):
        duplicates = dict(
            session.execute(
                select(field, func.count(CrawlPage.id))
                .where(
                    CrawlPage.crawl_run_id == run.id,
                    field.is_not(None),
                    field != "",
                )
                .group_by(field)
                .having(func.count(CrawlPage.id) > 1)
            ).all()
        )
        for page in pages:
            value = page.title if issue_type == "duplicate_title" else page.description
            if value in duplicates:
                _add_issue(
                    session,
                    run,
                    page,
                    issue_type,
                    "medium",
                    "Deze metadata komt op meerdere pagina's voor.",
                    {"value": value, "count": duplicates[value]},
                )

    from app.domains.crawls.models import CrawlLink

    links = list(
        session.scalars(
            select(CrawlLink)
            .join(CrawlPage, CrawlPage.id == CrawlLink.crawl_page_id)
            .where(CrawlPage.crawl_run_id == run.id)
        )
    )
    inbound = {page.normalized_url: 0 for page in pages}
    for link in links:
        normalized_target = normalize_url(link.target_url)
        target_page = pages_by_url.get(normalized_target)
        if target_page is not None:
            inbound[normalized_target] += 1
            if target_page.status_code and target_page.status_code >= 400:
                source_page = session.get(CrawlPage, link.crawl_page_id)
                if source_page is not None:
                    _add_issue(
                        session,
                        run,
                        source_page,
                        "broken_internal_link",
                        "high",
                        "Interne link verwijst naar een foutpagina.",
                        {
                            "target_url": link.target_url,
                            "status_code": target_page.status_code,
                        },
                    )
    root = normalize_url(run.root_url)
    for page in pages:
        if page.normalized_url != root and inbound[page.normalized_url] == 0:
            _add_issue(
                session,
                run,
                page,
                "orphan_candidate",
                "medium",
                "Geen interne inkomende link gevonden tijdens deze crawl.",
                {},
            )
    session.flush()


def _replace_links(session: Session, page: CrawlPage, links: list) -> None:
    from app.domains.crawls.models import CrawlLink

    existing_targets = set(
        session.scalars(
            select(CrawlLink.target_url).where(CrawlLink.crawl_page_id == page.id)
        )
    )
    source_host = urlsplit(page.url).netloc.lower()
    for item in links:
        target = item if isinstance(item, str) else item.get("url")
        if not target:
            continue
        target_url = urljoin(page.url, str(target))
        if target_url in existing_targets:
            continue
        target_parts = urlsplit(target_url)
        if target_parts.scheme not in {"http", "https"}:
            continue
        session.add(
            CrawlLink(
                id=str(uuid4()),
                crawl_page_id=page.id,
                source_url=page.url,
                target_url=target_url,
                anchor=item.get("text") if isinstance(item, dict) else None,
                internal=target_parts.netloc.lower() == source_host,
                follow=not (
                    isinstance(item, dict)
                    and "nofollow" in str(item.get("rel") or "").lower()
                ),
            )
        )
        existing_targets.add(target_url)


def _add_issue(
    session: Session,
    run: CrawlRun,
    page: CrawlPage,
    issue_type: str,
    severity: str,
    message: str,
    evidence: dict,
) -> None:
    existing = session.scalar(
        select(CrawlIssue).where(
            CrawlIssue.crawl_run_id == run.id,
            CrawlIssue.crawl_page_id == page.id,
            CrawlIssue.issue_type == issue_type,
        )
    )
    if existing is None:
        session.add(
            CrawlIssue(
                id=str(uuid4()),
                crawl_run_id=run.id,
                crawl_page_id=page.id,
                issue_type=issue_type,
                severity=severity,
                message=message,
                evidence=evidence,
            )
        )
