import secrets
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.page_packages.models import PagePackageProposal
from app.domains.projects.models import Project
from app.domains.projects.service import get_membership, get_project
from app.domains.wordpress.draft_jobs import (
    claim_next_draft_job,
    complete_draft_job,
    create_or_get_draft_job,
    fail_draft_job,
    hash_project_key,
    new_project_key,
    normalize_site_url,
)
from app.domains.wordpress.models import (
    WordPressDraftJob,
    WordPressOutboundCredential,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["wordpress-draft-jobs"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]

ALLOWED_FAILURE_CODES = {
    "blueprint_drift",
    "draft_not_persisted",
    "metadata_write_failed",
    "unknown_field",
    "unsupported_contract",
    "url_not_approved",
    "wordpress_error",
}


class CredentialWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    site_url: str = Field(min_length=1, max_length=2048)


class DraftJobCompleteWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_token: str = Field(min_length=20, max_length=128)
    wordpress_object_id: int = Field(gt=0)
    wordpress_edit_url: str | None = Field(default=None, max_length=2048)


class DraftJobFailWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_token: str = Field(min_length=20, max_length=128)
    error_code: str = Field(min_length=1, max_length=64)
    error_message: str = Field(default="", max_length=500)


def require_outbound_credential(
    project_id: str,
    session: SessionDependency,
    authorization: Annotated[str | None, Header()] = None,
    site_url: Annotated[str | None, Header(alias="X-WP-FixPilot-Site")] = None,
) -> WordPressOutboundCredential:
    if authorization is None or site_url is None:
        raise HTTPException(status_code=401, detail="Invalid WordPress project key")
    scheme, separator, raw_key = authorization.partition(" ")
    if separator != " " or scheme.casefold() != "bearer" or not raw_key.strip():
        raise HTTPException(status_code=401, detail="Invalid WordPress project key")
    credential = session.scalar(
        select(WordPressOutboundCredential).where(
            WordPressOutboundCredential.project_id == project_id,
            WordPressOutboundCredential.revoked_at.is_(None),
        )
    )
    if credential is None or not secrets.compare_digest(
        credential.key_hash, hash_project_key(raw_key.strip())
    ):
        raise HTTPException(status_code=401, detail="Invalid WordPress project key")
    try:
        normalized_site_url = normalize_site_url(site_url)
    except ValueError as error:
        raise HTTPException(
            status_code=403, detail="WordPress site mismatch"
        ) from error
    if normalized_site_url != credential.site_url:
        raise HTTPException(status_code=403, detail="WordPress site mismatch")
    return credential


PluginCredential = Annotated[
    WordPressOutboundCredential, Depends(require_outbound_credential)
]


@router.post(
    "/wordpress-outbound-credential",
    status_code=status.HTTP_201_CREATED,
)
def create_outbound_credential(
    project_id: str,
    payload: CredentialWrite,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _manager_project(session, user, project_id)
    existing = session.scalar(
        select(WordPressOutboundCredential).where(
            WordPressOutboundCredential.project_id == project.id
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="WordPress outbound credential already exists; rotate it instead",
        )
    try:
        site_url = normalize_site_url(payload.site_url)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    raw_key, key_hash = new_project_key()
    credential = WordPressOutboundCredential(
        id=f"wpcred_{uuid4().hex}",
        project_id=project.id,
        key_hash=key_hash,
        site_url=site_url,
    )
    session.add(credential)
    session.commit()
    session.refresh(credential)
    return {**_credential_payload(credential), "key": raw_key}


@router.get("/wordpress-outbound-credential")
def get_outbound_credential(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _manager_project(session, user, project_id)
    credential = session.scalar(
        select(WordPressOutboundCredential).where(
            WordPressOutboundCredential.project_id == project.id
        )
    )
    if credential is None:
        raise HTTPException(status_code=404, detail="WordPress credential not found")
    return _credential_payload(credential)


@router.post("/wordpress-outbound-credential/rotate")
def rotate_outbound_credential(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _manager_project(session, user, project_id)
    credential = session.scalar(
        select(WordPressOutboundCredential)
        .where(WordPressOutboundCredential.project_id == project.id)
        .with_for_update()
    )
    if credential is None:
        raise HTTPException(status_code=404, detail="WordPress credential not found")
    raw_key, key_hash = new_project_key()
    credential.key_hash = key_hash
    credential.revoked_at = None
    session.commit()
    session.refresh(credential)
    return {**_credential_payload(credential), "key": raw_key}


@router.delete(
    "/wordpress-outbound-credential",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_outbound_credential(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> Response:
    project = _manager_project(session, user, project_id)
    credential = session.scalar(
        select(WordPressOutboundCredential).where(
            WordPressOutboundCredential.project_id == project.id
        )
    )
    if credential is None:
        raise HTTPException(status_code=404, detail="WordPress credential not found")
    credential.revoked_at = datetime.now(UTC)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/page-proposals/{proposal_id}/draft-job", status_code=201)
def create_draft_job(
    project_id: str,
    proposal_id: str,
    response: Response,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    proposal = session.scalar(
        select(PagePackageProposal)
        .where(
            PagePackageProposal.id == proposal_id,
            PagePackageProposal.project_id == project_id,
        )
        .with_for_update()
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Page proposal not found")
    existing = session.scalar(
        select(WordPressDraftJob).where(
            WordPressDraftJob.proposal_version_id == proposal.id
        )
    )
    try:
        job = create_or_get_draft_job(session, proposal)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    session.commit()
    response.status_code = 200 if existing is not None else 201
    return _job_payload(job)


@router.get("/wordpress-draft-jobs/{job_id}")
def get_draft_job(
    project_id: str,
    job_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    return _job_payload(_project_job(session, project_id, job_id))


@router.post("/wordpress-draft-jobs/verify")
def verify_outbound_connection(
    credential: PluginCredential,
    session: SessionDependency,
) -> dict:
    credential.last_seen_at = datetime.now(UTC)
    session.commit()
    return {"connected": True, "project_id": credential.project_id}


@router.post("/wordpress-draft-jobs/claim", response_model=None)
def claim_draft_job(
    project_id: str,
    response: Response,
    credential: PluginCredential,
    session: SessionDependency,
) -> dict | Response:
    claimed = claim_next_draft_job(session, project_id, credential.site_url)
    if claimed is None:
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    session.commit()
    response.status_code = status.HTTP_200_OK
    return {
        "job": _job_payload(claimed.job, include_payload=True),
        "claim_token": claimed.claim_token,
    }


@router.post("/wordpress-draft-jobs/{job_id}/complete")
def complete_claimed_draft_job(
    project_id: str,
    job_id: str,
    payload: DraftJobCompleteWrite,
    credential: PluginCredential,
    session: SessionDependency,
) -> dict:
    _project_job(session, project_id, job_id)
    _validate_edit_url(payload.wordpress_edit_url, credential.site_url)
    try:
        job = complete_draft_job(
            session,
            job_id,
            payload.claim_token,
            wordpress_object_id=payload.wordpress_object_id,
            wordpress_edit_url=payload.wordpress_edit_url,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    session.commit()
    return _job_payload(job)


@router.post("/wordpress-draft-jobs/{job_id}/fail")
def fail_claimed_draft_job(
    project_id: str,
    job_id: str,
    payload: DraftJobFailWrite,
    _credential: PluginCredential,
    session: SessionDependency,
) -> dict:
    _project_job(session, project_id, job_id)
    if payload.error_code not in ALLOWED_FAILURE_CODES:
        raise HTTPException(status_code=422, detail="Unsupported draft job error code")
    try:
        job = fail_draft_job(
            session,
            job_id,
            payload.claim_token,
            error_code=payload.error_code,
            error_message=payload.error_message,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    session.commit()
    return _job_payload(job)


def _manager_project(
    session: Session, user: CurrentUser, project_id: str
) -> Project:
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    membership = get_membership(session, user.id, project.organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")
    return project


def _project_job(session: Session, project_id: str, job_id: str) -> WordPressDraftJob:
    job = session.scalar(
        select(WordPressDraftJob).where(
            WordPressDraftJob.id == job_id,
            WordPressDraftJob.project_id == project_id,
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Draft job not found")
    return job


def _validate_edit_url(value: str | None, site_url: str) -> None:
    if value is None:
        return
    parsed = urlsplit(value)
    try:
        origin = normalize_site_url(f"{parsed.scheme}://{parsed.netloc}")
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="Invalid WordPress edit URL"
        ) from error
    if origin != site_url or not parsed.path.startswith("/wp-admin/"):
        raise HTTPException(status_code=422, detail="Invalid WordPress edit URL")


def _credential_payload(credential: WordPressOutboundCredential) -> dict:
    return {
        "id": credential.id,
        "project_id": credential.project_id,
        "site_url": credential.site_url,
        "revoked_at": credential.revoked_at,
        "last_seen_at": credential.last_seen_at,
        "created_at": credential.created_at,
        "updated_at": credential.updated_at,
    }


def _job_payload(job: WordPressDraftJob, *, include_payload: bool = False) -> dict:
    payload = {
        "id": job.id,
        "project_id": job.project_id,
        "proposal_version_id": job.proposal_version_id,
        "contract_version": job.contract_version,
        "state": job.state,
        "claim_expires_at": job.claim_expires_at,
        "wordpress_object_id": job.wordpress_object_id,
        "wordpress_edit_url": job.wordpress_edit_url,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "attempt_count": job.attempt_count,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
    if include_payload:
        payload["payload"] = job.payload
        payload["payload_hash"] = job.payload_hash
    return payload
