from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.crawls.demo import DemoCrawlerProvider
from app.domains.crawls.firecrawl import MAX_CRAWL_URLS, FirecrawlProvider
from app.domains.crawls.models import CrawlIssue, CrawlPage, CrawlRun
from app.domains.crawls.provider import CrawlerProvider
from app.domains.crawls.service import (
    complete_run,
    import_page,
    record_webhook_event,
)
from app.domains.projects.service import get_project

router = APIRouter(tags=["crawls"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]


class StartCrawlRequest(BaseModel):
    limit: int = Field(default=500, ge=1)


def crawler_provider() -> CrawlerProvider:
    settings = get_settings()
    if settings.environment == "development" and settings.demo_mode:
        return DemoCrawlerProvider()
    return FirecrawlProvider(
        settings.firecrawl_api_key,
        webhook_url=settings.firecrawl_webhook_url,
        webhook_secret=settings.firecrawl_webhook_secret,
    )


def _run_payload(run: CrawlRun) -> dict:
    return {
        "id": run.id,
        "provider_crawl_id": run.provider_crawl_id,
        "root_url": run.root_url,
        "url_limit": run.url_limit,
        "state": run.state,
        "page_count": run.page_count,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
    }


@router.post(
    "/projects/{project_id}/crawls",
    status_code=status.HTTP_202_ACCEPTED,
)
def start_crawl(
    project_id: str,
    payload: StartCrawlRequest,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    limit = min(payload.limit, MAX_CRAWL_URLS)
    run = CrawlRun(
        id=str(uuid4()),
        project_id=project.id,
        provider="firecrawl",
        root_url=project.domain,
        url_limit=limit,
        state="starting",
    )
    session.add(run)
    session.flush()
    try:
        result = crawler_provider().start(
            project.domain,
            limit=limit,
            metadata={"project_id": project.id, "crawl_run_id": run.id},
        )
    except Exception as error:
        session.rollback()
        raise HTTPException(
            status_code=502,
            detail="External crawler could not be started",
        ) from error
    run.provider_crawl_id = str(result["id"])
    documents = list(result.get("data") or [])
    if documents:
        for document in documents:
            import_page(session, run, document)
        complete_run(session, run)
    else:
        run.state = "running"
        session.commit()
    return _run_payload(run)


@router.get("/projects/{project_id}/crawls")
def list_crawls(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict[str, list[dict]]:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    runs = session.scalars(
        select(CrawlRun)
        .where(CrawlRun.project_id == project_id)
        .order_by(CrawlRun.created_at.desc())
    )
    return {"items": [_run_payload(run) for run in runs]}


@router.get("/projects/{project_id}/crawls/{run_id}")
def crawl_results(
    project_id: str,
    run_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    run = session.scalar(
        select(CrawlRun).where(
            CrawlRun.id == run_id,
            CrawlRun.project_id == project_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Crawl not found")
    pages = list(
        session.scalars(select(CrawlPage).where(CrawlPage.crawl_run_id == run.id))
    )
    issues = list(
        session.scalars(select(CrawlIssue).where(CrawlIssue.crawl_run_id == run.id))
    )
    return {
        "run": _run_payload(run),
        "pages": [
            {
                "id": page.id,
                "url": page.url,
                "status_code": page.status_code,
                "title": page.title,
                "canonical_url": page.canonical_url,
                "indexable": page.indexable,
            }
            for page in pages
        ],
        "issues": [
            {
                "id": issue.id,
                "crawl_page_id": issue.crawl_page_id,
                "issue_type": issue.issue_type,
                "severity": issue.severity,
                "message": issue.message,
                "evidence": issue.evidence,
            }
            for issue in issues
        ],
    }


@router.delete(
    "/projects/{project_id}/crawls/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_crawl(
    project_id: str,
    run_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> None:
    if get_project(session, user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    run = session.scalar(
        select(CrawlRun).where(
            CrawlRun.id == run_id,
            CrawlRun.project_id == project_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Crawl not found")
    if run.provider_crawl_id and run.state not in {"completed", "failed", "cancelled"}:
        crawler_provider().cancel(run.provider_crawl_id)
    run.state = "cancelled"
    session.commit()


@router.post("/webhooks/firecrawl", status_code=status.HTTP_202_ACCEPTED)
async def firecrawl_webhook(
    request: Request,
    session: SessionDependency,
) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("X-Firecrawl-Signature")
    if not crawler_provider().verify_webhook(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    payload = await request.json()
    webhook_id = str(payload.get("webhookId") or "")
    if not webhook_id:
        raise HTTPException(status_code=400, detail="Missing webhook ID")
    if not record_webhook_event(session, webhook_id, payload):
        return {"status": "duplicate"}
    run = session.scalar(
        select(CrawlRun).where(
            CrawlRun.provider_crawl_id == str(payload.get("id") or "")
        )
    )
    if run is None:
        session.rollback()
        raise HTTPException(status_code=404, detail="Crawl not found")
    event_type = payload.get("type")
    if not payload.get("success", True):
        run.state = "failed"
        session.commit()
    elif event_type == "crawl.page":
        for document in payload.get("data") or []:
            import_page(session, run, document)
    elif event_type == "crawl.completed":
        for document in payload.get("data") or []:
            import_page(session, run, document)
        complete_run(session, run)
    elif event_type == "crawl.failed":
        run.state = "failed"
        session.commit()
    else:
        session.commit()
    return {"status": "accepted"}
