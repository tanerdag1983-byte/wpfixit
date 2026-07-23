from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domains.jobs.models import Job
from app.domains.page_blueprints.lifecycle import (
    BLUEPRINT_LIFECYCLE_STATES,
    BlueprintLifecycleState,
)
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.schemas import BlueprintSchema, SnapshotTextSchema

_ALLOWED_BLUEPRINT_STATES = set(BLUEPRINT_LIFECYCLE_STATES)
SNAPSHOT_MIGRATION_JOB_TYPE = "page_blueprint_snapshot_migration"


@dataclass(frozen=True)
class LegacyBlueprintCandidate:
    project_id: str
    source_wordpress_page_id: str
    builder: str
    seo_plugin: str
    state: BlueprintLifecycleState = "capture_required"


@dataclass(frozen=True)
class SnapshotMigrationResult:
    blueprint_id: str
    state: Literal["migrated", "incompatible", "failed"]
    action: Literal["none", "new_proposal", "recapture"]


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
    if content_schema.get("schema_version") == "snapshot-text-v1":
        schema = SnapshotTextSchema.model_validate(content_schema)
        schema.fields_by_id()
        return schema.model_dump(mode="python")
    return BlueprintSchema.model_validate(content_schema).model_dump(mode="python")


def snapshot_schema_from_capture(captured: dict) -> SnapshotTextSchema:
    schema = SnapshotTextSchema.model_validate(captured["content_schema"])
    schema.fields_by_id()
    return schema


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
    wordpress_snapshot_id: int | None = None,
    snapshot_version: int | None = None,
    schema_version: str | None = None,
    adapter_version: str | None = None,
    capture_state: str | None = None,
    migration_state: str | None = None,
    verified_at: datetime | None = None,
    seo_plugin: str | None = None,
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
        wordpress_snapshot_id=wordpress_snapshot_id,
        snapshot_version=snapshot_version,
        schema_version=schema_version,
        adapter_version=adapter_version,
        capture_state=capture_state,
        migration_state=migration_state,
        verified_at=verified_at,
        builder=original.builder,
        seo_plugin=seo_plugin or original.seo_plugin,
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


def snapshot_block_fields_are_compatible(
    legacy_schema: dict,
    snapshot_schema: dict,
) -> bool:
    legacy = BlueprintSchema.model_validate(legacy_schema)
    snapshot = SnapshotTextSchema.model_validate(snapshot_schema)
    legacy_fields = {
        field.id: field.value_type for block in legacy.blocks for field in block.fields
    }
    snapshot_fields = {
        field.id: field.value_type
        for block in snapshot.blocks
        for field in block.fields
    }
    return legacy_fields == snapshot_fields


def migrate_unapproved_proposals(
    session: Session,
    legacy: PageBlueprint,
    successor: PageBlueprint,
) -> bool:
    from app.domains.page_packages.models import PagePackageProposal

    proposals = session.scalars(
        select(PagePackageProposal).where(
            PagePackageProposal.project_id == legacy.project_id,
            PagePackageProposal.blueprint_id == legacy.id,
            PagePackageProposal.is_current.is_(True),
        )
    ).all()
    compatible = snapshot_block_fields_are_compatible(
        legacy.content_schema,
        successor.content_schema,
    )
    incompatible = False

    for proposal in proposals:
        if (
            proposal.state in {"approved", "draft_in_progress", "draft_created"}
            or proposal.approved_by is not None
            or proposal.approved_at is not None
        ):
            continue
        if not compatible:
            proposal.state = "failed"
            job = session.get(Job, proposal.job_id)
            if job is not None:
                job.error_code = "snapshot_migration_requires_generation"
            incompatible = True
            continue

        next_id = str(uuid4())
        job = Job(
            id=str(uuid4()),
            project_id=proposal.project_id,
            job_type="page_package_snapshot_migration",
            state="completed",
            progress=100,
            checkpoint={
                "legacy_proposal_version_id": proposal.id,
                "snapshot_blueprint_id": successor.id,
            },
        )
        next_version = PagePackageProposal(
            id=next_id,
            project_id=proposal.project_id,
            opportunity_id=proposal.opportunity_id,
            job_id=job.id,
            state="proposed",
            proposal_group_id=proposal.proposal_group_id,
            version_number=proposal.version_number + 1,
            parent_version_id=proposal.id,
            current_version_id=next_id,
            is_current=True,
            generation_mode=proposal.generation_mode,
            target_block_id=proposal.target_block_id,
            user_instruction=proposal.user_instruction,
            blueprint_id=successor.id,
            blueprint_version=successor.version,
            blueprint_structure_hash=successor.structure_hash,
            package=proposal.package,
            rendered_html=proposal.rendered_html,
            config_snapshot={
                **proposal.config_snapshot,
                "blueprint_id": successor.id,
                "page_type": successor.page_type,
                "version": successor.version,
                "structure_hash": successor.structure_hash,
                "builder": successor.builder,
                "seo_plugin": successor.seo_plugin,
                "content_schema": successor.content_schema,
                "wordpress_snapshot_id": successor.wordpress_snapshot_id,
                "snapshot_version": successor.snapshot_version,
                "schema_version": successor.schema_version,
                "adapter_version": successor.adapter_version,
                "capture_state": successor.capture_state,
                "migration_state": successor.migration_state,
            },
            provider=proposal.provider,
            model=proposal.model,
            prompt_version=proposal.prompt_version,
            input_tokens=proposal.input_tokens,
            output_tokens=proposal.output_tokens,
            proposed_by=proposal.proposed_by,
        )
        proposal.is_current = False
        proposal.current_version_id = next_id
        session.query(PagePackageProposal).filter(
            PagePackageProposal.proposal_group_id == proposal.proposal_group_id
        ).update(
            {PagePackageProposal.current_version_id: next_id},
            synchronize_session="fetch",
        )
        session.add_all([job, next_version])

    session.flush()
    return incompatible


def snapshot_migration_job_id(blueprint_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"snapshot-migration:{blueprint_id}"))


def prepare_snapshot_migration(
    session: Session,
    blueprint: PageBlueprint,
) -> Job:
    job = session.get(Job, snapshot_migration_job_id(blueprint.id))
    if job is None:
        job = Job(
            id=snapshot_migration_job_id(blueprint.id),
            project_id=blueprint.project_id,
            job_type=SNAPSHOT_MIGRATION_JOB_TYPE,
            state="pending",
            progress=0,
            checkpoint={
                "blueprint_id": blueprint.id,
                "transitions": ["pending"],
            },
        )
        session.add(job)
    else:
        checkpoint = dict(job.checkpoint)
        transitions = list(checkpoint.get("transitions", []))
        transitions.append("pending")
        job.state = "pending"
        job.progress = 0
        job.error_code = None
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        job.checkpoint = {**checkpoint, "transitions": transitions}
    session.flush()
    return job


def transition_snapshot_migration(
    job: Job,
    state: Literal["pending", "migrating", "migrated", "incompatible", "failed"],
    *,
    action: Literal["none", "new_proposal", "recapture"] = "none",
    successor_id: str | None = None,
) -> None:
    checkpoint = dict(job.checkpoint)
    transitions = list(checkpoint.get("transitions", []))
    if not transitions or transitions[-1] != state:
        transitions.append(state)
    checkpoint["transitions"] = transitions
    checkpoint["action"] = action
    if successor_id is not None:
        checkpoint["successor_blueprint_id"] = successor_id
    job.state = state
    job.checkpoint = checkpoint
    if state == "migrating":
        job.progress = 25
        job.started_at = datetime.now(UTC)
    elif state in {"migrated", "incompatible", "failed"}:
        job.progress = 100
        job.completed_at = datetime.now(UTC)
    if state == "failed":
        job.error_code = "snapshot_migration_recapture_required"
