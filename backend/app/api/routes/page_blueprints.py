from typing import Annotated, Literal
from uuid import uuid4

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


class BlueprintCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    page_type: str = Field(min_length=1, max_length=32)
    source_wordpress_page_id: str = Field(min_length=1, max_length=64)


class BlueprintUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    page_type: str | None = Field(default=None, min_length=1, max_length=32)
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
    session: Session, project_id: str, blueprint_id: str
) -> PageBlueprint:
    blueprint = session.scalar(
        select(PageBlueprint).where(
            PageBlueprint.id == blueprint_id,
            PageBlueprint.project_id == project_id,
        )
    )
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


def _validated_capture(data: dict) -> tuple[BlueprintSchema, str]:
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
    return schema, state


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
    _project_or_404(session, user, project_id)
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
    captured = bridge.capture_blueprint({"source_page_id": source.wordpress_object_id})
    try:
        schema, state = _validated_capture(captured)
        blueprint = PageBlueprint(
            id=str(uuid4()),
            project_id=project_id,
            name=payload.name,
            page_type=payload.page_type,
            source_wordpress_page_id=source.id,
            wordpress_blueprint_id=int(captured["wordpress_blueprint_id"]),
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
        wordpress_id = captured.get("wordpress_blueprint_id")
        if wordpress_id is not None:
            bridge.delete_blueprint(int(wordpress_id))
        raise
    return _payload(blueprint)


@router.get("/page-blueprints/{blueprint_id}")
def get_blueprint_route(
    project_id: str,
    blueprint_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _project_or_404(session, user, project_id)
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
    try:
        schema = BlueprintSchema.model_validate(inspected.get("content_schema"))
    except ValidationError as error:
        blueprint.state = "invalid"
        blueprint.is_default_for_page_type = False
        session.commit()
        raise HTTPException(
            status_code=409, detail="Blueprint schema is invalid"
        ) from error
    if (
        str(inspected.get("structure_hash")) != blueprint.structure_hash
        or schema.model_dump(mode="python") != blueprint.content_schema
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
    blueprint = _blueprint_or_404(session, project_id, blueprint_id)
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
    captured = bridge.capture_blueprint({"source_page_id": source.wordpress_object_id})
    try:
        schema, state = _validated_capture(captured)
        replacement = create_blueprint_version(
            session,
            original,
            wordpress_blueprint_id=int(captured["wordpress_blueprint_id"]),
            structure_hash=str(captured["structure_hash"]),
            content_schema=schema.model_dump(mode="python"),
            state=state,
        )
        if original.is_default_for_page_type:
            set_default_blueprint(session, replacement)
            session.refresh(replacement)
    except Exception:
        session.rollback()
        wordpress_id = captured.get("wordpress_blueprint_id")
        if wordpress_id is not None:
            bridge.delete_blueprint(int(wordpress_id))
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
    blueprint = _blueprint_or_404(session, project_id, blueprint_id)
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
    _bridge(session, project_id).delete_blueprint(blueprint.wordpress_blueprint_id)
    session.delete(blueprint)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
