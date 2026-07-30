from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.wordpress_draft_jobs import PluginCredential
from app.core.database import get_session
from app.domains.wordpress.models import WordPressSnapshotCaptureJob
from app.domains.wordpress.snapshot_jobs import (
    SnapshotJobError,
    claim_next_snapshot_job,
    complete_snapshot_job,
    fail_snapshot_job,
)

router = APIRouter(
    prefix="/projects/{project_id}/wordpress-snapshot-jobs",
    tags=["wordpress-snapshot-jobs"],
)
SessionDependency = Annotated[Session, Depends(get_session)]
ALLOWED_FAILURE_CODES = {
    "builder_unsupported",
    "snapshot_invalid",
    "wordpress_error",
}


class SnapshotResultWrite(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    snapshot_id: int = Field(gt=0, strict=True)
    snapshot_version: int = Field(gt=0, strict=True)
    structure_hash: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(pattern="^snapshot-text-v1$")
    snapshot_schema: dict = Field(alias="schema")
    snapshot_kind: str = Field(pattern="^optimization_source$")
    source_post_id: int = Field(gt=0, strict=True)
    source_url: str = Field(min_length=1, max_length=2048)
    source_content_hash: str = Field(min_length=1, max_length=128)
    captured_at: str = Field(min_length=1, max_length=64)


class SnapshotJobCompleteWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_token: str = Field(min_length=20, max_length=128)
    result: SnapshotResultWrite


class SnapshotJobFailWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_token: str = Field(min_length=20, max_length=128)
    error_code: str = Field(min_length=1, max_length=64)
    error_message: str = Field(default="", max_length=500)


@router.post("/claim", response_model=None)
def claim_snapshot_job(
    project_id: str,
    response: Response,
    credential: PluginCredential,
    session: SessionDependency,
) -> dict | Response:
    try:
        claimed = claim_next_snapshot_job(session, project_id, credential.site_url)
    except SnapshotJobError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if claimed is None:
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    session.commit()
    response.status_code = status.HTTP_200_OK
    return {
        "job": {
            "id": claimed.job.id,
            "project_id": claimed.job.project_id,
            "wordpress_page_id": claimed.job.wordpress_page_id,
            "source_post_id": claimed.source_post_id,
            "source_url": claimed.source_url,
            "source_content_hash": claimed.source_content_hash,
        },
        "claim_token": claimed.claim_token,
    }


@router.post("/{job_id}/complete")
def complete_claimed_snapshot_job(
    project_id: str,
    job_id: str,
    payload: SnapshotJobCompleteWrite,
    _credential: PluginCredential,
    session: SessionDependency,
) -> dict:
    _project_job(session, project_id, job_id)
    try:
        job = complete_snapshot_job(
            session,
            job_id,
            payload.claim_token,
            payload.result.model_dump(mode="json", by_alias=True),
        )
    except SnapshotJobError as error:
        raise _snapshot_conflict(error) from error
    session.commit()
    return _job_payload(job)


@router.post("/{job_id}/fail")
def fail_claimed_snapshot_job(
    project_id: str,
    job_id: str,
    payload: SnapshotJobFailWrite,
    _credential: PluginCredential,
    session: SessionDependency,
) -> dict:
    _project_job(session, project_id, job_id)
    if payload.error_code not in ALLOWED_FAILURE_CODES:
        raise HTTPException(
            status_code=422,
            detail="Unsupported snapshot job error code",
        )
    try:
        job = fail_snapshot_job(
            session,
            job_id,
            payload.claim_token,
            error_code=payload.error_code,
            error_message=payload.error_message,
        )
    except SnapshotJobError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    session.commit()
    return _job_payload(job)


def _project_job(
    session: Session, project_id: str, job_id: str
) -> WordPressSnapshotCaptureJob:
    job = session.scalar(
        select(WordPressSnapshotCaptureJob).where(
            WordPressSnapshotCaptureJob.id == job_id,
            WordPressSnapshotCaptureJob.project_id == project_id,
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Snapshot job not found")
    return job


def _job_payload(job: WordPressSnapshotCaptureJob) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "wordpress_page_id": job.wordpress_page_id,
        "state": job.state,
        "attempt_count": job.attempt_count,
    }


def _snapshot_conflict(error: SnapshotJobError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": error.code},
    )
