from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.schemas import BlueprintSchema


def _validated_schema(content_schema: dict) -> dict:
    return BlueprintSchema.model_validate(content_schema).model_dump(mode="python")


def set_default_blueprint(session: Session, blueprint: PageBlueprint) -> None:
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
    session.commit()


def create_blueprint_version(
    session: Session,
    original: PageBlueprint,
    *,
    wordpress_blueprint_id: int,
    structure_hash: str,
    content_schema: dict,
) -> PageBlueprint:
    validated_schema = _validated_schema(content_schema)
    next_version = session.scalar(
        select(func.max(PageBlueprint.version)).where(
            PageBlueprint.project_id == original.project_id,
            PageBlueprint.page_type == original.page_type,
        )
    )
    replacement = PageBlueprint(
        id=f"{original.id}-v{(next_version or original.version) + 1}",
        project_id=original.project_id,
        name=original.name,
        page_type=original.page_type,
        source_wordpress_page_id=original.source_wordpress_page_id,
        wordpress_blueprint_id=wordpress_blueprint_id,
        builder=original.builder,
        seo_plugin=original.seo_plugin,
        version=(next_version or original.version) + 1,
        structure_hash=structure_hash,
        content_schema=validated_schema,
        state=original.state,
        is_default_for_page_type=False,
        supersedes_id=original.id,
    )
    session.add(replacement)
    session.commit()
    session.refresh(replacement)

    if original.is_default_for_page_type:
        set_default_blueprint(session, replacement)
        session.refresh(replacement)

    return replacement
