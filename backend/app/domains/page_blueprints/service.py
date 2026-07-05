from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.domains.page_blueprints.lifecycle import (
    BLUEPRINT_LIFECYCLE_STATES,
    BlueprintLifecycleState,
)
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.schemas import BlueprintSchema

_ALLOWED_BLUEPRINT_STATES = set(BLUEPRINT_LIFECYCLE_STATES)


@dataclass(frozen=True)
class LegacyBlueprintCandidate:
    project_id: str
    source_wordpress_page_id: str
    builder: str
    seo_plugin: str
    state: BlueprintLifecycleState = "capture_required"


def legacy_blueprint_candidates(
    session: Session,
    project_id: str,
) -> list[LegacyBlueprintCandidate]:
    from app.domains.page_packages.models import ProjectPagePackageSettings

    settings = session.get(ProjectPagePackageSettings, project_id)
    if (
        settings is None
        or settings.validation_state != "valid"
        or not settings.template_wordpress_page_id
    ):
        return []
    managed_source_exists = session.query(PageBlueprint.id).filter(
        PageBlueprint.project_id == project_id,
        PageBlueprint.source_wordpress_page_id
        == settings.template_wordpress_page_id,
    ).first()
    if managed_source_exists is not None:
        return []
    return [
        LegacyBlueprintCandidate(
            project_id=project_id,
            source_wordpress_page_id=settings.template_wordpress_page_id,
            builder=settings.builder,
            seo_plugin=settings.seo_plugin,
        )
    ]


def _validated_schema(content_schema: dict) -> dict:
    return BlueprintSchema.model_validate(content_schema).model_dump(mode="python")


def _validated_state(state: str) -> str:
    if state not in _ALLOWED_BLUEPRINT_STATES:
        allowed_states = ", ".join(sorted(_ALLOWED_BLUEPRINT_STATES))
        raise ValueError(f"state must be one of: {allowed_states}")
    return state


def set_default_blueprint(
    session: Session,
    blueprint: PageBlueprint,
    *,
    commit: bool = True,
) -> None:
    if blueprint.state != "ready":
        raise ValueError("Only ready blueprints can be set as the default")

    session.execute(
        update(PageBlueprint)
        .where(
            PageBlueprint.project_id == blueprint.project_id,
            PageBlueprint.page_type == blueprint.page_type,
            PageBlueprint.id != blueprint.id,
        )
        .values(is_default_for_page_type=False)
    )
    blueprint.is_default_for_page_type = True
    if commit:
        session.commit()
    else:
        session.flush()


def create_blueprint_version(
    session: Session,
    original: PageBlueprint,
    *,
    wordpress_blueprint_id: int,
    structure_hash: str,
    content_schema: dict,
    state: BlueprintLifecycleState,
    commit: bool = True,
) -> PageBlueprint:
    validated_schema = _validated_schema(content_schema)
    validated_state = _validated_state(state)
    next_version = original.version + 1
    replacement = PageBlueprint(
        id=str(uuid5(NAMESPACE_URL, f"page-blueprint:{original.id}:{next_version}")),
        project_id=original.project_id,
        name=original.name,
        page_type=original.page_type,
        source_wordpress_page_id=original.source_wordpress_page_id,
        wordpress_blueprint_id=wordpress_blueprint_id,
        builder=original.builder,
        seo_plugin=original.seo_plugin,
        version=next_version,
        structure_hash=structure_hash,
        content_schema=validated_schema,
        state=validated_state,
        is_default_for_page_type=False,
        supersedes_id=original.id,
    )
    session.add(replacement)
    if commit:
        session.commit()
        session.refresh(replacement)
    else:
        session.flush()

    return replacement
