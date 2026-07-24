from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

import requests
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.schemas import BlueprintSchema, SnapshotTextSchema
from app.domains.page_blueprints.service import (
    SNAPSHOT_MIGRATION_JOB_TYPE,
    SnapshotMigrationResult,
    create_blueprint_version,
    legacy_blueprint_candidates,
    lock_blueprint_successor,
    lock_current_blueprint_proposals,
    lock_legacy_blueprint,
    migrate_unapproved_proposals,
    prepare_snapshot_migration,
    set_default_blueprint,
    snapshot_migration_job_id,
    snapshot_schema_from_capture,
    transition_snapshot_migration,
)
from app.domains.page_packages.models import PagePackageProposal
from app.domains.projects.service import get_membership, get_project
from app.domains.wordpress.client import WordPressClient
from app.domains.wordpress.models import WordPressConnection, WordPressPage

router = APIRouter(prefix="/projects/{project_id}", tags=["page-blueprints"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]
SemanticRole = Literal[
    "hero", "introduction", "benefits", "process", "faq", "cta", "content"
]
PageType = Literal["service", "brand", "location", "blog", "generic"]
SUPPORTED_BUILDERS = {"acf", "elementor", "wpbakery", "bricks", "gutenberg"}
SUPPORTED_SEO_PLUGINS = {"none", "yoast", "rank_math", "aioseo"}
MUTATING_PROPOSAL_STATES = {"generating", "draft_in_progress"}


class BlueprintCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    page_type: PageType
    source_wordpress_page_id: str = Field(min_length=1, max_length=64)


class BlueprintUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    page_type: PageType | None = None
    semantic_roles: dict[str, SemanticRole] | None = None


def _project_or_404(session: Session, user: CurrentUser, project_id: str):
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_manager(session: Session, user: CurrentUser, organization_id: str) -> None:
    membership = get_membership(session, user.id, organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")


def _manager_project(session: Session, user: CurrentUser, project_id: str):
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    return project


def _blueprint_or_404(
    session: Session,
    project_id: str,
    blueprint_id: str,
    *,
    for_update: bool = False,
) -> PageBlueprint:
    statement = select(PageBlueprint).where(
        PageBlueprint.id == blueprint_id,
        PageBlueprint.project_id == project_id,
    )
    if for_update:
        statement = statement.with_for_update()
    blueprint = session.scalar(statement)
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return blueprint


def _bridge(session: Session, project_id: str) -> WordPressClient:
    connection = session.scalar(
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="WordPress connection not found")
    return WordPressClient(
        connection.site_url,
        decrypt_text(connection.encrypted_secret),
    )


def _validated_capture(
    data: dict,
    *,
    wordpress_snapshot_id: int,
    source_page_id: int,
    page_type: str,
    version: int,
    expected_builder: str | None = None,
) -> tuple[SnapshotTextSchema, str]:
    try:
        schema = snapshot_schema_from_capture(data)
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise HTTPException(
            status_code=502, detail="WordPress returned an invalid snapshot schema"
        ) from error
    state = str(data.get("status", ""))
    if state != "ready":
        raise HTTPException(
            status_code=409, detail="Captured WordPress blueprint is not ready"
        )
    expected = {
        "wordpress_snapshot_id": wordpress_snapshot_id,
        "snapshot_version": version,
        "schema_version": "snapshot-text-v1",
        "source_page_id": source_page_id,
        "page_type": page_type,
    }
    if any(data.get(key) != value for key, value in expected.items()):
        raise HTTPException(
            status_code=502,
            detail="WordPress returned a mismatched blueprint identity",
        )
    captured_builder = str(data.get("builder") or "")
    if captured_builder not in SUPPORTED_BUILDERS or (
        expected_builder is not None and captured_builder != expected_builder
    ):
        raise HTTPException(
            status_code=502, detail="WordPress returned an invalid blueprint builder"
        )
    if str(data.get("seo_plugin") or "") not in SUPPORTED_SEO_PLUGINS:
        raise HTTPException(
            status_code=502,
            detail="WordPress returned an invalid SEO plugin identity",
        )
    if not str(data.get("structure_hash") or ""):
        raise HTTPException(
            status_code=502, detail="WordPress returned an empty blueprint hash"
        )
    return schema, state


def _schema_with_stored_roles(
    inspected: BlueprintSchema | SnapshotTextSchema,
    stored: BlueprintSchema | SnapshotTextSchema,
) -> dict:
    stored_roles = {block.id: block.semantic_role for block in stored.blocks}
    if {block.id for block in inspected.blocks} != set(stored_roles):
        return inspected.model_dump(mode="python")
    for block in inspected.blocks:
        block.semantic_role = stored_roles[block.id]
    return inspected.model_dump(mode="python")


def _delete_remote_snapshot(bridge: WordPressClient, wordpress_id: int) -> None:
    try:
        if hasattr(bridge, "delete_snapshot"):
            bridge.delete_snapshot(wordpress_id)
        else:
            bridge.delete_blueprint(wordpress_id)
    except requests.HTTPError as error:
        if error.response is None or error.response.status_code != 404:
            raise


def _new_capture_snapshot_id(
    session: Session,
    project_id: str,
    captured: dict,
) -> int:
    wordpress_id = captured.get("wordpress_snapshot_id")
    if (
        captured.get("created") is not True
        or isinstance(wordpress_id, bool)
        or not isinstance(wordpress_id, int)
        or wordpress_id < 1
        or captured.get("wordpress_blueprint_id") != wordpress_id
        or captured.get("post_type") != "wpfixpilot_snapshot"
        or not isinstance(captured.get("adapter_version"), str)
        or not captured["adapter_version"]
    ):
        raise HTTPException(
            status_code=502,
            detail="WordPress returned an untrusted snapshot identity",
        )
    existing = session.scalar(
        select(PageBlueprint.id).where(
            PageBlueprint.project_id == project_id,
            PageBlueprint.wordpress_snapshot_id == wordpress_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="WordPress snapshot identity is already registered",
        )
    return wordpress_id


def _capture_snapshot(bridge: WordPressClient, payload: dict) -> dict:
    try:
        if hasattr(bridge, "capture_snapshot"):
            return bridge.capture_snapshot(payload)
        return bridge.capture_blueprint(payload)
    except requests.Timeout as error:
        raise HTTPException(
            status_code=504,
            detail=(
                "WordPress had meer tijd nodig om deze pagina vast te leggen. "
                "Probeer opnieuw."
            ),
        ) from error


def _read_snapshot(bridge: WordPressClient, wordpress_snapshot_id: int) -> dict:
    if hasattr(bridge, "snapshot"):
        return bridge.snapshot(wordpress_snapshot_id)
    return bridge.blueprint(wordpress_snapshot_id)


def _adapter_version(captured: dict) -> str:
    return str(captured["adapter_version"])


def _payload(blueprint: PageBlueprint) -> dict:
    return {
        "id": blueprint.id,
        "project_id": blueprint.project_id,
        "name": blueprint.name,
        "page_type": blueprint.page_type,
        "source_wordpress_page_id": blueprint.source_wordpress_page_id,
        "wordpress_blueprint_id": blueprint.wordpress_blueprint_id,
        "wordpress_snapshot_id": blueprint.wordpress_snapshot_id,
        "snapshot_version": blueprint.snapshot_version,
        "schema_version": blueprint.schema_version,
        "adapter_version": blueprint.adapter_version,
        "capture_state": blueprint.capture_state,
        "migration_state": blueprint.migration_state,
        "verified_at": blueprint.verified_at,
        "builder": blueprint.builder,
        "seo_plugin": blueprint.seo_plugin,
        "version": blueprint.version,
        "structure_hash": blueprint.structure_hash,
        "content_schema": blueprint.content_schema,
        "state": blueprint.state,
        "is_default_for_page_type": blueprint.is_default_for_page_type,
        "supersedes_id": blueprint.supersedes_id,
        "created_at": blueprint.created_at,
        "updated_at": blueprint.updated_at,
    }


def _verify_native_snapshot(
    session: Session,
    bridge: WordPressClient,
    blueprint: PageBlueprint,
) -> dict:
    source = session.get(WordPressPage, blueprint.source_wordpress_page_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Snapshot lineage is unavailable")
    inspected = _read_snapshot(bridge, blueprint.wordpress_snapshot_id)
    if str(inspected.get("status")) != "ready":
        blueprint.state = "invalid"
        blueprint.is_default_for_page_type = False
        session.commit()
        raise HTTPException(status_code=409, detail="WordPress snapshot is not ready")
    try:
        schema = snapshot_schema_from_capture(inspected)
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        blueprint.state = "invalid"
        blueprint.is_default_for_page_type = False
        session.commit()
        raise HTTPException(
            status_code=409,
            detail="Snapshot schema is invalid",
        ) from error

    expected_identity = {
        "wordpress_snapshot_id": blueprint.wordpress_snapshot_id,
        "wordpress_blueprint_id": blueprint.wordpress_snapshot_id,
        "snapshot_version": blueprint.snapshot_version,
        "schema_version": blueprint.schema_version,
        "source_page_id": source.wordpress_object_id,
        "builder": blueprint.builder,
        "seo_plugin": blueprint.seo_plugin,
        "page_type": blueprint.page_type,
        "post_type": "wpfixpilot_snapshot",
        "adapter_version": blueprint.adapter_version,
    }
    stored_schema = SnapshotTextSchema.model_validate(blueprint.content_schema)
    schema_matches = (
        _schema_with_stored_roles(schema, stored_schema) == blueprint.content_schema
    )
    if (
        any(inspected.get(key) != value for key, value in expected_identity.items())
        or str(inspected.get("structure_hash")) != blueprint.structure_hash
        or not schema_matches
    ):
        blueprint.state = "stale"
        blueprint.is_default_for_page_type = False
        session.commit()
        raise HTTPException(status_code=409, detail="Snapshot structure has changed")

    blueprint.state = "ready"
    blueprint.verified_at = datetime.now(UTC)
    session.commit()
    session.refresh(blueprint)
    return _payload(blueprint)


def _migration_payload(result: SnapshotMigrationResult) -> dict:
    item = {"blueprint_id": result.blueprint_id, "state": result.state}
    if result.action != "none":
        item["action"] = result.action
    return item


@router.get("/page-blueprints")
def list_blueprints(
    project_id: str, session: SessionDependency, user: UserDependency
) -> dict:
    _manager_project(session, user, project_id)
    items = session.scalars(
        select(PageBlueprint)
        .where(PageBlueprint.project_id == project_id)
        .order_by(PageBlueprint.created_at, PageBlueprint.id)
    ).all()
    migration_results = []
    migration_jobs = session.scalars(
        select(Job).where(
            Job.project_id == project_id,
            Job.job_type == SNAPSHOT_MIGRATION_JOB_TYPE,
        )
    ).all()
    for job in migration_jobs:
        blueprint_id = job.checkpoint.get("blueprint_id")
        state = "pending" if job.state == "migrating" else job.state
        action = job.checkpoint.get("action", "none")
        if (
            isinstance(blueprint_id, str)
            and state in {"pending", "migrated", "incompatible", "failed"}
            and action in {"none", "new_proposal", "recapture", "cleanup", "wait"}
        ):
            migration_results.append(
                _migration_payload(
                    SnapshotMigrationResult(
                        blueprint_id=blueprint_id,
                        state=state,
                        action=action,
                    )
                )
            )
    migration_results.sort(key=lambda item: item["blueprint_id"])
    return {
        "items": [_payload(item) for item in items],
        "migration_results": migration_results,
        "legacy_candidates": [
            {
                "source_wordpress_page_id": candidate.source_wordpress_page_id,
                "builder": candidate.builder,
                "seo_plugin": candidate.seo_plugin,
                "state": candidate.state,
            }
            for candidate in legacy_blueprint_candidates(session, project_id)
        ],
    }


@router.post("/page-blueprints", status_code=status.HTTP_201_CREATED)
def create_blueprint(
    project_id: str,
    payload: BlueprintCreate,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    source = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == payload.source_wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Reference page not found")
    bridge = _bridge(session, project_id)
    captured = _capture_snapshot(
        bridge,
        {
            "source_page_id": source.wordpress_object_id,
            "name": payload.name,
            "page_type": payload.page_type,
            "version": 1,
        }
    )
    cleanup_snapshot_id: int | None = None
    try:
        snapshot_id = _new_capture_snapshot_id(session, project_id, captured)
        cleanup_snapshot_id = snapshot_id
        schema, state = _validated_capture(
            captured,
            wordpress_snapshot_id=snapshot_id,
            source_page_id=source.wordpress_object_id,
            page_type=payload.page_type,
            version=1,
        )
        blueprint = PageBlueprint(
            id=str(uuid4()),
            project_id=project_id,
            name=payload.name,
            page_type=payload.page_type,
            source_wordpress_page_id=source.id,
            wordpress_blueprint_id=snapshot_id,
            wordpress_snapshot_id=snapshot_id,
            snapshot_version=1,
            schema_version="snapshot-text-v1",
            adapter_version=_adapter_version(captured),
            capture_state=state,
            migration_state="native",
            verified_at=datetime.now(UTC),
            builder=str(captured["builder"]),
            seo_plugin=str(captured.get("seo_plugin") or "none"),
            version=1,
            structure_hash=str(captured["structure_hash"]),
            content_schema=schema.model_dump(mode="python"),
            state=state,
            is_default_for_page_type=False,
        )
        session.add(blueprint)
        session.commit()
    except Exception:
        session.rollback()
        if cleanup_snapshot_id is not None:
            _delete_remote_snapshot(bridge, cleanup_snapshot_id)
        raise
    session.refresh(blueprint)
    return _payload(blueprint)


def _recover_snapshot_migration_cleanup(
    session: Session,
    bridge: WordPressClient,
    legacy_id: str,
    job: Job,
    *,
    commit: bool = True,
) -> SnapshotMigrationResult | None:
    cleanup_snapshot_id = job.checkpoint.get("cleanup_snapshot_id")
    if cleanup_snapshot_id is None:
        return None
    try:
        _delete_remote_snapshot(bridge, int(cleanup_snapshot_id))
    except requests.RequestException as cleanup_error:
        transition_snapshot_migration(
            job,
            "failed",
            action="cleanup",
            cleanup_snapshot_id=int(cleanup_snapshot_id),
            error_message=str(cleanup_error)[:1000],
        )
        if commit:
            session.commit()
        return SnapshotMigrationResult(
            blueprint_id=legacy_id,
            state="failed",
            action="cleanup",
        )
    checkpoint = dict(job.checkpoint)
    checkpoint.pop("cleanup_snapshot_id", None)
    job.checkpoint = checkpoint
    legacy = session.get(PageBlueprint, legacy_id)
    if legacy is not None:
        prepare_snapshot_migration(session, legacy)
    if commit:
        session.commit()
    return None


@router.post("/page-blueprints/migrate")
def migrate_blueprints(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
    blueprint_id: str | None = None,
) -> dict:
    _manager_project(session, user, project_id)
    bridge = _bridge(session, project_id)
    successor_ids = select(PageBlueprint.supersedes_id).where(
        PageBlueprint.project_id == project_id,
        PageBlueprint.supersedes_id.is_not(None),
    )
    legacy_query = select(PageBlueprint.id).where(
        PageBlueprint.project_id == project_id,
        PageBlueprint.wordpress_snapshot_id.is_(None),
        PageBlueprint.id.not_in(successor_ids),
    )
    if blueprint_id is not None:
        legacy_query = legacy_query.where(PageBlueprint.id == blueprint_id)
    legacy_ids = session.scalars(
        legacy_query.order_by(PageBlueprint.created_at, PageBlueprint.id)
    ).all()
    if blueprint_id is not None and not legacy_ids:
        raise HTTPException(
            status_code=404,
            detail="Legacy template is not available for migration",
        )
    for legacy_id in legacy_ids:
        legacy = session.get(PageBlueprint, legacy_id)
        if legacy is not None:
            prepare_snapshot_migration(session, legacy)
    session.commit()

    results: list[SnapshotMigrationResult] = []
    for legacy_id in legacy_ids:
        trusted_snapshot_id: int | None = None
        migration_committed = False
        job = session.get(Job, snapshot_migration_job_id(legacy_id))
        if job is None:
            raise RuntimeError("Snapshot migration state is unavailable")
        cleanup_result = _recover_snapshot_migration_cleanup(
            session,
            bridge,
            legacy_id,
            job,
        )
        if cleanup_result is not None:
            results.append(cleanup_result)
            continue
        try:
            job = session.get(Job, snapshot_migration_job_id(legacy_id))
            if job is None:
                raise RuntimeError("Snapshot migration state is unavailable")
            transition_snapshot_migration(job, "migrating")
            session.commit()
            with session.begin():
                legacy = lock_legacy_blueprint(
                    session,
                    project_id,
                    legacy_id,
                )
                if legacy is None:
                    raise RuntimeError("Legacy blueprint is unavailable")
                job = session.scalar(
                    select(Job)
                    .where(Job.id == snapshot_migration_job_id(legacy_id))
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if job is None:
                    raise RuntimeError("Snapshot migration state is unavailable")
                cleanup_result = _recover_snapshot_migration_cleanup(
                    session,
                    bridge,
                    legacy_id,
                    job,
                    commit=False,
                )
                existing_successor = (
                    lock_blueprint_successor(session, project_id, legacy_id)
                    if cleanup_result is None
                    else None
                )
                if cleanup_result is not None:
                    result_state = cleanup_result.state
                    result_action = cleanup_result.action
                elif existing_successor is not None:
                    result_state = "migrated"
                    result_action = "none"
                    transition_snapshot_migration(
                        job,
                        result_state,
                        successor_id=existing_successor.id,
                    )
                else:
                    proposals = lock_current_blueprint_proposals(session, legacy)
                    mutating = [
                        proposal
                        for proposal in proposals
                        if proposal.state in MUTATING_PROPOSAL_STATES
                    ]
                    if mutating:
                        result_state = "pending"
                        result_action = "wait"
                        transition_snapshot_migration(
                            job,
                            "pending",
                            action="wait",
                            blocked_proposal_ids=sorted(
                                proposal.id for proposal in mutating
                            ),
                        )
                    else:
                        source = session.get(
                            WordPressPage,
                            legacy.source_wordpress_page_id,
                        )
                        if source is None:
                            raise ValueError("Reference page not found")
                        next_version = legacy.version + 1
                        captured = _capture_snapshot(
                            bridge,
                            {
                                "source_page_id": source.wordpress_object_id,
                                "name": legacy.name,
                                "page_type": legacy.page_type,
                                "version": next_version,
                            },
                        )
                        snapshot_id = _new_capture_snapshot_id(
                            session,
                            project_id,
                            captured,
                        )
                        trusted_snapshot_id = snapshot_id
                        schema, state = _validated_capture(
                            captured,
                            wordpress_snapshot_id=snapshot_id,
                            source_page_id=source.wordpress_object_id,
                            page_type=legacy.page_type,
                            version=next_version,
                            expected_builder=legacy.builder,
                        )
                        successor = create_blueprint_version(
                            session,
                            legacy,
                            wordpress_blueprint_id=snapshot_id,
                            wordpress_snapshot_id=snapshot_id,
                            snapshot_version=next_version,
                            schema_version="snapshot-text-v1",
                            adapter_version=_adapter_version(captured),
                            capture_state=state,
                            migration_state="native",
                            verified_at=datetime.now(UTC),
                            structure_hash=str(captured["structure_hash"]),
                            content_schema=schema.model_dump(mode="python"),
                            state=state,
                            seo_plugin=str(captured["seo_plugin"]),
                            commit=False,
                        )
                        incompatible = migrate_unapproved_proposals(
                            session,
                            legacy,
                            successor,
                            proposals,
                        )
                        if legacy.is_default_for_page_type:
                            set_default_blueprint(
                                session,
                                successor,
                                commit=False,
                            )
                        result_state = (
                            "incompatible" if incompatible else "migrated"
                        )
                        result_action = (
                            "new_proposal" if incompatible else "none"
                        )
                        transition_snapshot_migration(
                            job,
                            result_state,
                            action=result_action,
                            successor_id=successor.id,
                        )
            migration_committed = True
            results.append(
                SnapshotMigrationResult(
                    blueprint_id=legacy_id,
                    state=result_state,
                    action=result_action,
                )
            )
        except Exception as migration_error:
            session.rollback()
            failure_action = "recapture"
            if trusted_snapshot_id is not None and not migration_committed:
                with session.begin():
                    job = session.get(Job, snapshot_migration_job_id(legacy_id))
                    if job is None:
                        legacy = session.get(PageBlueprint, legacy_id)
                        if legacy is None:
                            continue
                        job = prepare_snapshot_migration(session, legacy)
                        transition_snapshot_migration(job, "migrating")
                    transition_snapshot_migration(
                        job,
                        "failed",
                        action="cleanup",
                        cleanup_snapshot_id=trusted_snapshot_id,
                        error_message=str(migration_error)[:1000],
                    )
                try:
                    _delete_remote_snapshot(bridge, trusted_snapshot_id)
                except requests.RequestException as cleanup_error:
                    failure_action = "cleanup"
                    with session.begin():
                        job = session.get(
                            Job,
                            snapshot_migration_job_id(legacy_id),
                        )
                        if job is None:
                            raise RuntimeError(
                                "Snapshot migration state is unavailable"
                            ) from cleanup_error
                        transition_snapshot_migration(
                            job,
                            "failed",
                            action="cleanup",
                            cleanup_snapshot_id=trusted_snapshot_id,
                            error_message=str(cleanup_error)[:1000],
                        )
                else:
                    with session.begin():
                        job = session.get(
                            Job,
                            snapshot_migration_job_id(legacy_id),
                        )
                        if job is None:
                            raise RuntimeError(
                                "Snapshot migration state is unavailable"
                            )
                        transition_snapshot_migration(
                            job,
                            "failed",
                            action="recapture",
                            clear_cleanup=True,
                            error_message=str(migration_error)[:1000],
                        )
            else:
                with session.begin():
                    job = session.get(Job, snapshot_migration_job_id(legacy_id))
                    if job is None:
                        legacy = session.get(PageBlueprint, legacy_id)
                        if legacy is None:
                            continue
                        job = prepare_snapshot_migration(session, legacy)
                        transition_snapshot_migration(job, "migrating")
                    transition_snapshot_migration(
                        job,
                        "failed",
                        action="recapture",
                        error_message=str(migration_error)[:1000],
                    )
            results.append(
                SnapshotMigrationResult(
                    blueprint_id=legacy_id,
                    state="failed",
                    action=failure_action,
                )
            )

    return {"items": [_migration_payload(result) for result in results]}


@router.get("/page-blueprints/{blueprint_id}")
def get_blueprint_route(
    project_id: str,
    blueprint_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    return _payload(_blueprint_or_404(session, project_id, blueprint_id))


@router.put("/page-blueprints/{blueprint_id}")
def update_blueprint(
    project_id: str,
    blueprint_id: str,
    payload: BlueprintUpdate,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    blueprint = _blueprint_or_404(session, project_id, blueprint_id)
    if payload.name is not None:
        blueprint.name = payload.name
    if payload.page_type is not None:
        if (
            blueprint.is_default_for_page_type
            and payload.page_type != blueprint.page_type
        ):
            raise HTTPException(
                status_code=409,
                detail="Change the default before changing page type",
            )
        if payload.page_type != blueprint.page_type:
            blueprint.state = "stale"
        blueprint.page_type = payload.page_type
    if payload.semantic_roles is not None:
        if blueprint.schema_version == "snapshot-text-v1":
            schema = SnapshotTextSchema.model_validate(blueprint.content_schema)
        else:
            schema = BlueprintSchema.model_validate(blueprint.content_schema)
        blocks = {block.id: block for block in schema.blocks}
        unknown = set(payload.semantic_roles) - set(blocks)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown blueprint block IDs: {', '.join(sorted(unknown))}",
            )
        for block_id, role in payload.semantic_roles.items():
            blocks[block_id].semantic_role = role
        blueprint.content_schema = schema.model_dump(mode="python")
    session.commit()
    session.refresh(blueprint)
    return _payload(blueprint)


@router.post("/page-blueprints/{blueprint_id}/validate")
def validate_blueprint(
    project_id: str,
    blueprint_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    blueprint = _blueprint_or_404(session, project_id, blueprint_id)
    if blueprint.wordpress_snapshot_id is not None:
        return _verify_native_snapshot(
            session,
            _bridge(session, project_id),
            blueprint,
        )
    inspected = _bridge(session, project_id).blueprint(blueprint.wordpress_blueprint_id)
    if str(inspected.get("status")) != "ready":
        blueprint.state = "invalid"
        blueprint.is_default_for_page_type = False
        session.commit()
        raise HTTPException(status_code=409, detail="WordPress blueprint is not ready")
    try:
        schema = BlueprintSchema.model_validate(inspected.get("content_schema"))
    except ValidationError as error:
        blueprint.state = "invalid"
        blueprint.is_default_for_page_type = False
        session.commit()
        raise HTTPException(
            status_code=409, detail="Blueprint schema is invalid"
        ) from error
    source = session.get(WordPressPage, blueprint.source_wordpress_page_id)
    expected_identity = {
        "wordpress_blueprint_id": blueprint.wordpress_blueprint_id,
        "source_page_id": source.wordpress_object_id if source is not None else None,
        "builder": blueprint.builder,
        "seo_plugin": blueprint.seo_plugin,
        "page_type": blueprint.page_type,
        "version": blueprint.version,
    }
    stored_schema = BlueprintSchema.model_validate(blueprint.content_schema)
    schema_matches = (
        _schema_with_stored_roles(schema, stored_schema) == blueprint.content_schema
    )
    if (
        any(inspected.get(key) != value for key, value in expected_identity.items())
        or str(inspected.get("structure_hash")) != blueprint.structure_hash
        or not schema_matches
    ):
        blueprint.state = "stale"
        blueprint.is_default_for_page_type = False
        session.commit()
        raise HTTPException(status_code=409, detail="Blueprint structure has changed")
    blueprint.state = "ready"
    session.commit()
    session.refresh(blueprint)
    return _payload(blueprint)


@router.post("/page-blueprints/{blueprint_id}/verify")
def verify_blueprint(
    project_id: str,
    blueprint_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    blueprint = _blueprint_or_404(session, project_id, blueprint_id)
    if blueprint.wordpress_snapshot_id is None:
        raise HTTPException(
            status_code=409,
            detail="Legacy blueprint requires snapshot migration",
        )
    return _verify_native_snapshot(
        session,
        _bridge(session, project_id),
        blueprint,
    )


@router.post("/page-blueprints/{blueprint_id}/set-default")
def default_blueprint(
    project_id: str,
    blueprint_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    blueprint = _blueprint_or_404(
        session,
        project_id,
        blueprint_id,
        for_update=True,
    )
    try:
        set_default_blueprint(session, blueprint)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    session.refresh(blueprint)
    return _payload(blueprint)


@router.post(
    "/page-blueprints/{blueprint_id}/new-version",
    status_code=status.HTTP_201_CREATED,
)
def version_blueprint(
    project_id: str,
    blueprint_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _manager_project(session, user, project_id)
    original = _blueprint_or_404(
        session,
        project_id,
        blueprint_id,
        for_update=True,
    )
    source = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == original.source_wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Reference page not found")
    bridge = _bridge(session, project_id)
    next_version = original.version + 1
    captured = _capture_snapshot(
        bridge,
        {
            "source_page_id": source.wordpress_object_id,
            "name": original.name,
            "page_type": original.page_type,
            "version": next_version,
        }
    )
    cleanup_snapshot_id: int | None = None
    try:
        snapshot_id = _new_capture_snapshot_id(session, project_id, captured)
        cleanup_snapshot_id = snapshot_id
        schema, state = _validated_capture(
            captured,
            wordpress_snapshot_id=snapshot_id,
            source_page_id=source.wordpress_object_id,
            page_type=original.page_type,
            version=next_version,
            expected_builder=original.builder,
        )
        replacement = create_blueprint_version(
            session,
            original,
            wordpress_blueprint_id=snapshot_id,
            wordpress_snapshot_id=snapshot_id,
            snapshot_version=next_version,
            schema_version="snapshot-text-v1",
            adapter_version=_adapter_version(captured),
            capture_state=state,
            migration_state="native",
            verified_at=datetime.now(UTC),
            structure_hash=str(captured["structure_hash"]),
            content_schema=schema.model_dump(mode="python"),
            state=state,
            seo_plugin=str(captured["seo_plugin"]),
            commit=False,
        )
        if original.is_default_for_page_type:
            set_default_blueprint(session, replacement, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        if cleanup_snapshot_id is not None:
            _delete_remote_snapshot(bridge, cleanup_snapshot_id)
        raise
    session.refresh(replacement)
    return _payload(replacement)


@router.delete(
    "/page-blueprints/{blueprint_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_blueprint_route(
    project_id: str,
    blueprint_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> Response:
    _manager_project(session, user, project_id)
    blueprint = _blueprint_or_404(
        session,
        project_id,
        blueprint_id,
        for_update=True,
    )
    proposal = session.scalar(
        select(PagePackageProposal.id).where(
            PagePackageProposal.project_id == project_id,
            PagePackageProposal.blueprint_id == blueprint.id,
        )
    )
    successor = session.scalar(
        select(PageBlueprint.id).where(PageBlueprint.supersedes_id == blueprint.id)
    )
    if proposal is not None or successor is not None:
        raise HTTPException(status_code=409, detail="Blueprint is still referenced")
    blueprint.state = "invalid"
    blueprint.is_default_for_page_type = False
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    _delete_remote_snapshot(
        _bridge(session, project_id),
        blueprint.wordpress_snapshot_id or blueprint.wordpress_blueprint_id,
    )
    session.delete(blueprint)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
