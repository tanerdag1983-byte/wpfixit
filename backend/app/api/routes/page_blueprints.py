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
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.schemas import BlueprintSchema
from app.domains.page_blueprints.service import (
    create_blueprint_version,
    set_default_blueprint,
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
    source_page_id: int,
    page_type: str,
    version: int,
    expected_builder: str | None = None,
) -> tuple[BlueprintSchema, str]:
    try:
        schema = BlueprintSchema.model_validate(data.get("content_schema"))
    except ValidationError as error:
        raise HTTPException(
            status_code=502, detail="WordPress returned an invalid blueprint schema"
        ) from error
    state = str(data.get("status", ""))
    if state != "ready":
        raise HTTPException(
            status_code=409, detail="Captured WordPress blueprint is not ready"
        )
    expected = {
        "source_page_id": source_page_id,
        "page_type": page_type,
        "version": version,
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
    if not str(data.get("structure_hash") or ""):
        raise HTTPException(
            status_code=502, detail="WordPress returned an empty blueprint hash"
        )
    return schema, state


def _schema_with_stored_roles(
    inspected: BlueprintSchema, stored: BlueprintSchema
) -> dict:
    stored_roles = {block.id: block.semantic_role for block in stored.blocks}
    if {block.id for block in inspected.blocks} != set(stored_roles):
        return inspected.model_dump(mode="python")
    for block in inspected.blocks:
        block.semantic_role = stored_roles[block.id]
    return inspected.model_dump(mode="python")


def _delete_remote_blueprint(bridge: WordPressClient, wordpress_id: int) -> None:
    try:
        bridge.delete_blueprint(wordpress_id)
    except requests.HTTPError as error:
        if error.response is None or error.response.status_code != 404:
            raise


def _new_capture_wordpress_id(
    session: Session,
    project_id: str,
    captured: dict,
) -> int:
    wordpress_id = captured.get("wordpress_blueprint_id")
    if (
        captured.get("created") is not True
        or isinstance(wordpress_id, bool)
        or not isinstance(wordpress_id, int)
        or wordpress_id < 1
    ):
        raise HTTPException(
            status_code=502,
            detail="WordPress returned an untrusted blueprint identity",
        )
    existing = session.scalar(
        select(PageBlueprint.id).where(
            PageBlueprint.project_id == project_id,
            PageBlueprint.wordpress_blueprint_id == wordpress_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="WordPress blueprint identity is already registered",
        )
    return wordpress_id


def _payload(blueprint: PageBlueprint) -> dict:
    return {
        "id": blueprint.id,
        "project_id": blueprint.project_id,
        "name": blueprint.name,
        "page_type": blueprint.page_type,
        "source_wordpress_page_id": blueprint.source_wordpress_page_id,
        "wordpress_blueprint_id": blueprint.wordpress_blueprint_id,
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
    return {"items": [_payload(item) for item in items]}


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
    captured = bridge.capture_blueprint(
        {
            "source_page_id": source.wordpress_object_id,
            "name": payload.name,
            "page_type": payload.page_type,
            "version": 1,
        }
    )
    cleanup_wordpress_id: int | None = None
    try:
        wordpress_id = _new_capture_wordpress_id(session, project_id, captured)
        cleanup_wordpress_id = wordpress_id
        schema, state = _validated_capture(
            captured,
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
            wordpress_blueprint_id=wordpress_id,
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
        session.refresh(blueprint)
    except Exception:
        session.rollback()
        if cleanup_wordpress_id is not None:
            _delete_remote_blueprint(bridge, cleanup_wordpress_id)
        raise
    return _payload(blueprint)


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
    original = _blueprint_or_404(session, project_id, blueprint_id)
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
    captured = bridge.capture_blueprint(
        {
            "source_page_id": source.wordpress_object_id,
            "name": original.name,
            "page_type": original.page_type,
            "version": next_version,
        }
    )
    cleanup_wordpress_id: int | None = None
    try:
        wordpress_id = _new_capture_wordpress_id(session, project_id, captured)
        cleanup_wordpress_id = wordpress_id
        schema, state = _validated_capture(
            captured,
            source_page_id=source.wordpress_object_id,
            page_type=original.page_type,
            version=next_version,
            expected_builder=original.builder,
        )
        replacement = create_blueprint_version(
            session,
            original,
            wordpress_blueprint_id=wordpress_id,
            structure_hash=str(captured["structure_hash"]),
            content_schema=schema.model_dump(mode="python"),
            state=state,
            commit=False,
        )
        if original.is_default_for_page_type:
            set_default_blueprint(session, replacement, commit=False)
        session.commit()
        session.refresh(replacement)
    except Exception:
        session.rollback()
        if cleanup_wordpress_id is not None:
            _delete_remote_blueprint(bridge, cleanup_wordpress_id)
        raise
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
    _delete_remote_blueprint(
        _bridge(session, project_id), blueprint.wordpress_blueprint_id
    )
    session.delete(blueprint)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
