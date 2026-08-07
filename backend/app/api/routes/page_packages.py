import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote_plus
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.core.database import background_engine, get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_packages.generation import (
    PolicyPagePackageGenerator,
    build_context,
    normalize_snapshot_text_package,
    prompt_version,
    regeneration_candidate_payload,
    validate_blueprint_replacements,
)
from app.domains.page_packages.models import (
    PagePackageHandoff,
    PagePackageProposal,
    PagePackageRegenerationCandidate,
    PageProposalStage,
    ProjectPagePackageSettings,
)
from app.domains.page_packages.schemas import (
    GeneratedBlueprintPackage,
    GeneratedSnapshotTextPackage,
    InternalLink,
    PagePackageContext,
    PagePackageGenerationResult,
    PagePackageProposalWrite,
    PagePackageSettingsWrite,
    PageProposalHandoffCompleteRequest,
    PageProposalHandoffRedeemRequest,
    PageProposalRegenerationRequest,
    PageProposalRequest,
)
from app.domains.page_packages.service import (
    accept_regeneration_candidate_with_revocations,
    complete_page_package_handoff,
    create_regeneration_candidate,
    discard_regeneration_candidate,
    existing_page_snapshot_blueprint,
    issue_page_package_handoff,
    lock_active_default_blueprint,
    redeem_page_package_handoff,
    revoke_page_package_handoff,
)
from app.domains.page_packages.stages import (
    attention_stage,
    begin_stage,
    complete_stage,
    fail_stage,
    initialize_proposal_stages,
    locked_stage,
    ordered_proposal_stages,
    reclaim_stale_running_stage,
    retry_stage,
)
from app.domains.projects.models import Project
from app.domains.projects.service import get_membership, get_project
from app.domains.recommendations.models import (
    AiConnection,
    CompanyProfile,
    ProjectAiPolicy,
)
from app.domains.recommendations.openai_compatible_provider import (
    normalize_blueprint_package,
)
from app.domains.recommendations.provider_factory import build_generator
from app.domains.subscriptions.models import UsageEvent
from app.domains.wordpress.client import WordPressClient
from app.domains.wordpress.draft_jobs import cancel_ineligible_draft_jobs
from app.domains.wordpress.models import (
    PageObservedVersion,
    PageScoreSnapshot,
    WordPressConnection,
    WordPressDraftJob,
    WordPressPage,
    WordPressSnapshotCaptureJob,
)
from app.domains.wordpress.snapshot_jobs import (
    SnapshotJobError,
    create_or_get_snapshot_job,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["page-packages"])
SessionDependency = Annotated[Session, Depends(get_session)]
UserDependency = Annotated[CurrentUser, Depends(get_current_user)]
REQUIRED_SLOTS = {
    "hero_title",
    "introduction",
    "main_content",
    "faq",
}
OPTIONAL_SLOTS = {
    "cta_title",
    "cta_text",
}
MAPPABLE_SLOTS = REQUIRED_SLOTS | OPTIONAL_SLOTS


@router.get("/page-package-settings")
def get_page_package_settings(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _project_or_404(session, user, project_id)
    settings = session.get(ProjectPagePackageSettings, project_id)
    if settings is None:
        return {"configured": False, "validation_state": "unconfigured"}
    return _settings_payload(settings)


@router.get("/page-package-settings/options")
def get_page_package_options(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _project_or_404(session, user, project_id)
    try:
        detected = _page_package_client(session, project_id).builders()
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="WordPress builders could not be detected",
        ) from error
    return {
        "builders": list(detected.get("builders") or []),
        "seo_plugin": detected.get("seo_plugin"),
    }


@router.put("/page-package-settings")
def put_page_package_settings(
    project_id: str,
    payload: PagePackageSettingsWrite,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    template = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == payload.template_wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Template page not found")
    settings = session.get(ProjectPagePackageSettings, project_id)
    if settings is None:
        settings = ProjectPagePackageSettings(project_id=project_id)
        session.add(settings)
    settings.builder = payload.builder
    settings.template_wordpress_page_id = template.id
    settings.seo_plugin = payload.seo_plugin
    settings.slot_mapping = payload.slot_mapping
    settings.template_content_hash = None
    settings.validation_state = "unvalidated"
    settings.validated_at = None
    session.commit()
    return _settings_payload(settings)


@router.post("/page-package-settings/inspect-template")
def inspect_page_package_template(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    settings, template = _configured_settings(session, project_id)
    try:
        return _page_package_client(session, project_id).template_slots(
            template.wordpress_object_id,
            settings.builder,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="WordPress template could not be inspected",
        ) from error


@router.post("/page-package-settings/validate")
def validate_page_package_settings(
    project_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    settings, template = _configured_settings(session, project_id)
    try:
        inspection = _page_package_client(session, project_id).template_slots(
            template.wordpress_object_id,
            settings.builder,
        )
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="WordPress template could not be inspected",
        ) from error
    available_paths = {
        str(slot.get("path"))
        for slot in inspection.get("slots", [])
        if isinstance(slot, dict) and slot.get("path")
    }
    mapped_required = {
        slot for slot in REQUIRED_SLOTS if settings.slot_mapping.get(slot)
    }
    mapped_slots = {slot for slot in MAPPABLE_SLOTS if settings.slot_mapping.get(slot)}
    mapped_path_values = [settings.slot_mapping[slot] for slot in mapped_slots]
    mapped_paths = set(mapped_path_values)
    duplicate_paths = {
        path for path in mapped_paths if mapped_path_values.count(path) > 1
    }
    duplicate_paths_are_safe = not duplicate_paths or (
        settings.builder == "acf"
        and all(path.startswith("acf-block:") for path in duplicate_paths)
    )
    valid = (
        inspection.get("builder") == settings.builder
        and inspection.get("seo_plugin") == settings.seo_plugin
        and mapped_required == REQUIRED_SLOTS
        and duplicate_paths_are_safe
        and mapped_paths.issubset(available_paths)
        and bool(inspection.get("template_hash"))
    )
    if not valid:
        settings.validation_state = "invalid"
        settings.template_content_hash = None
        settings.validated_at = None
        session.commit()
        raise HTTPException(
            status_code=409,
            detail="Builder, SEO plugin, or mapped slots do not match the template",
        )
    settings.validation_state = "valid"
    settings.template_content_hash = str(inspection["template_hash"])
    settings.validated_at = datetime.now(UTC)
    session.commit()
    return _settings_payload(settings)


@router.post(
    "/keyword-opportunities/{opportunity_id}/page-proposal",
    status_code=202,
)
def create_page_package_proposal(
    project_id: str,
    opportunity_id: str,
    payload: PageProposalRequest,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    opportunity = session.scalar(
        select(KeywordOpportunity).where(
            KeywordOpportunity.id == opportunity_id,
            KeywordOpportunity.project_id == project_id,
        ).with_for_update()
    )
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Keyword opportunity not found")
    if opportunity.target_classification == "review":
        raise HTTPException(
            status_code=409,
            detail="Assign a target page before creating a page proposal",
        )
    source_page = None
    snapshot_job = None
    if opportunity.target_classification == "existing_page":
        source_page = _existing_page_target(session, project_id, opportunity)
        snapshot_job = _completed_existing_page_snapshot(session, source_page)
        if snapshot_job is None:
            try:
                snapshot_job = create_or_get_snapshot_job(session, source_page)
            except SnapshotJobError as error:
                if error.persist_changes:
                    session.commit()
                raise HTTPException(status_code=409, detail=str(error)) from error
            session.commit()
            return {
                "stage": "waiting_for_wordpress_snapshot",
                "snapshot_job_id": snapshot_job.id,
                "source_wordpress_page_id": source_page.id,
            }
        try:
            blueprint = existing_page_snapshot_blueprint(
                session,
                source_page,
                snapshot_job,
                payload.page_type,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    elif opportunity.target_classification == "new_page":
        blueprint, selection_changed = lock_active_default_blueprint(
            session,
            project_id,
            payload.page_type,
        )
        if blueprint is None:
            if selection_changed:
                raise HTTPException(
                    status_code=409,
                    detail="Default blueprint changed; retry proposal creation",
                )
            raise HTTPException(
                status_code=422,
                detail="Set a ready default blueprint for this page type",
            )
    else:
        raise HTTPException(
            status_code=409,
            detail="Opportunity target classification is not supported",
        )
    existing_query = select(PagePackageProposal).where(
        PagePackageProposal.project_id == project_id,
        PagePackageProposal.opportunity_id == opportunity_id,
        PagePackageProposal.blueprint_id == blueprint.id,
        PagePackageProposal.source_wordpress_page_id
        == (source_page.id if source_page is not None else None),
        PagePackageProposal.is_current.is_(True),
    )
    if source_page is None:
        existing_query = existing_query.where(
            PagePackageProposal.state.in_(
                ["generating", "needs_attention", "proposed"]
            )
        )
    existing = session.scalar(
        existing_query.order_by(PagePackageProposal.created_at.desc())
    )
    if existing is not None:
        return _proposal_payload(session, existing)

    context = (
        _existing_page_generation_context(
            session,
            project,
            opportunity,
            source_page,
            snapshot_job,
            blueprint,
        )
        if source_page is not None and snapshot_job is not None
        else _generation_context(session, project, opportunity, blueprint)
    )
    policy = session.get(ProjectAiPolicy, project.id)
    if policy is None:
        raise HTTPException(
            status_code=422, detail="Project AI model is not configured"
        )
    job = Job(
        id=str(uuid4()),
        project_id=project_id,
        job_type="page_package_generation",
        state="queued",
        progress=0,
        checkpoint={"opportunity_id": opportunity_id},
    )
    config_snapshot = {
        "blueprint_id": blueprint.id,
        "page_type": blueprint.page_type,
        "version": blueprint.version,
        "structure_hash": blueprint.structure_hash,
        "builder": blueprint.builder,
        "seo_plugin": blueprint.seo_plugin,
        "content_schema": blueprint.content_schema,
    }
    if _is_snapshot_schema(blueprint.content_schema):
        config_snapshot.update(
            {
                "wordpress_snapshot_id": blueprint.wordpress_snapshot_id,
                "snapshot_version": blueprint.snapshot_version,
                "schema_version": blueprint.schema_version,
                "adapter_version": blueprint.adapter_version,
            }
        )
    if source_page is not None and snapshot_job is not None:
        snapshot_result = snapshot_job.snapshot_result
        assert isinstance(snapshot_result, dict)
        config_snapshot.update(
            {
                "snapshot_job_id": snapshot_job.id,
                "source_wordpress_page_id": source_page.id,
                "source_wordpress_object_id": source_page.wordpress_object_id,
                "source_url": snapshot_result["source_url"],
                "source_content_hash": snapshot_result["source_content_hash"],
                "generation_context": context.model_dump(mode="json"),
            }
        )
    proposal = PagePackageProposal(
        id=str(uuid4()),
        project_id=project_id,
        opportunity_id=opportunity_id,
        job_id=job.id,
        state="generating",
        proposal_group_id="",
        current_version_id="",
        package={},
        rendered_html="",
        config_snapshot=config_snapshot,
        source_wordpress_page_id=source_page.id if source_page is not None else None,
        blueprint_id=blueprint.id,
        blueprint_version=blueprint.version,
        blueprint_structure_hash=blueprint.structure_hash,
        model=policy.primary_model,
        prompt_version=prompt_version(context, policy.primary_model),
        proposed_by=user.id,
    )
    proposal.proposal_group_id = proposal.id
    proposal.current_version_id = proposal.id
    session.add_all([job, proposal])
    if _is_snapshot_schema(blueprint.content_schema):
        initialize_proposal_stages(session, proposal.id)
    session.commit()
    background_tasks.add_task(
        _run_page_package_generation,
        background_engine(session),
        proposal.id,
    )
    return _proposal_payload(session, proposal)


def _existing_page_target(
    session: Session,
    project_id: str,
    opportunity: KeywordOpportunity,
) -> WordPressPage:
    if not opportunity.target_url:
        raise HTTPException(
            status_code=409,
            detail="Assign a synchronized target page before creating a proposal",
        )
    pages = session.scalars(
        select(WordPressPage).where(
            WordPressPage.project_id == project_id,
            WordPressPage.post_type == "page",
            WordPressPage.url == opportunity.target_url,
        ).with_for_update()
    ).all()
    if len(pages) != 1:
        raise HTTPException(
            status_code=409,
            detail="Opportunity target must match one synchronized WordPress page",
        )
    return pages[0]


def _completed_existing_page_snapshot(
    session: Session,
    page: WordPressPage,
) -> WordPressSnapshotCaptureJob | None:
    jobs = session.scalars(
        select(WordPressSnapshotCaptureJob)
        .where(
            WordPressSnapshotCaptureJob.project_id == page.project_id,
            WordPressSnapshotCaptureJob.wordpress_page_id == page.id,
            WordPressSnapshotCaptureJob.state == "completed",
        )
        .order_by(
            WordPressSnapshotCaptureJob.completed_at.desc(),
            WordPressSnapshotCaptureJob.id.desc(),
        )
    ).all()
    for job in jobs:
        result = job.snapshot_result
        if (
            isinstance(result, dict)
            and result.get("source_post_id") == page.wordpress_object_id
            and result.get("source_url") == page.url
            and result.get("source_content_hash") == page.content_hash
        ):
            return job
    return None


def _existing_page_generation_context(
    session: Session,
    project: Project,
    opportunity: KeywordOpportunity,
    page: WordPressPage,
    snapshot_job: WordPressSnapshotCaptureJob,
    blueprint: PageBlueprint,
) -> PagePackageContext:
    result = snapshot_job.snapshot_result
    if not isinstance(result, dict):
        raise ValueError("completed snapshot result is unavailable")
    version = session.scalar(
        select(PageObservedVersion)
        .where(
            PageObservedVersion.wordpress_page_id == page.id,
            PageObservedVersion.content_hash == result["source_content_hash"],
        )
        .order_by(PageObservedVersion.observed_at.desc())
    )
    score = (
        session.scalar(
            select(PageScoreSnapshot).where(
                PageScoreSnapshot.page_version_id == version.id
            )
        )
        if version is not None
        else None
    )
    improvement_context = {
        "target_url": result["source_url"],
        "prior_score": score.overall_score if score is not None else None,
        "target_match_score": opportunity.target_score,
        "improvement_evidence": {
            "keyword_match": opportunity.target_evidence,
            "recommended_action": opportunity.recommended_action,
            "score_factors": score.factors if score is not None else [],
        },
    }
    base = _generation_context(session, project, opportunity, blueprint)
    company_context = (
        "Existing page improvement context:\n"
        + json.dumps(improvement_context, ensure_ascii=False, sort_keys=True)
        + "\n"
        + base.company_context
    )[:10_000]
    return base.model_copy(update={"company_context": company_context})


def _run_page_package_generation(bind, proposal_id: str) -> None:
    with Session(bind) as session:
        proposal = session.get(PagePackageProposal, proposal_id)
        if proposal is None or proposal.state != "generating":
            return
        job = session.get(Job, proposal.job_id)
        opportunity = session.get(KeywordOpportunity, proposal.opportunity_id)
        project = session.get(Project, proposal.project_id)
        blueprint = session.scalar(
            select(PageBlueprint).where(
                PageBlueprint.project_id == proposal.project_id,
                PageBlueprint.id == proposal.blueprint_id,
                PageBlueprint.version == proposal.blueprint_version,
                PageBlueprint.structure_hash == proposal.blueprint_structure_hash,
                PageBlueprint.state == "ready",
            )
        )
        if job is None or opportunity is None or project is None:
            return
        if _is_snapshot_schema(proposal.config_snapshot.get("content_schema")):
            _run_snapshot_page_package_generation(
                session,
                proposal,
                job,
                opportunity,
                project,
                blueprint,
            )
            return
        if blueprint is None:
            proposal.state = "failed"
            job.state = "failed"
            job.error_code = "BlueprintUnavailable"
            job.error_message = "Blueprint changed before generation started"
            job.completed_at = datetime.now(UTC)
            session.commit()
            return
        if blueprint.content_schema != proposal.config_snapshot.get("content_schema"):
            proposal.state = "failed"
            job.state = "failed"
            job.error_code = "BlueprintSchemaChanged"
            job.error_message = "Blueprint schema changed before generation started"
            job.completed_at = datetime.now(UTC)
            session.commit()
            return
        job.state = "running"
        job.progress = 5
        job.started_at = datetime.now(UTC)
        session.commit()
        try:
            generator = _page_package_generator(session, project)
            context = _proposal_generation_context(
                session,
                proposal,
                project,
                opportunity,
                blueprint,
            )
            generated = PagePackageGenerationResult.model_validate(
                generator.generate_page_package(context)
            )
            raw_package = (
                generated.package.model_dump(mode="json")
                if hasattr(generated.package, "model_dump")
                else generated.package
            )
            package = normalize_blueprint_package(raw_package, context)
            package = validate_blueprint_replacements(package, context)
            allowed_links = {link.url for link in context.internal_link_candidates}
            if any(link.url not in allowed_links for link in package.internal_links):
                raise ValueError("AI returned an unknown internal link")
            proposal.package = package.model_dump()
            proposal.rendered_html = ""
            proposal.provider = generated.provider or proposal.provider
            proposal.model = generated.model or proposal.model
            proposal.input_tokens = generated.input_tokens
            proposal.output_tokens = generated.output_tokens
            proposal.state = "proposed"
            job.state = "completed"
            job.progress = 100
            job.checkpoint = {**job.checkpoint, "proposal_id": proposal.id}
            job.completed_at = datetime.now(UTC)
            token_count = generated.input_tokens + generated.output_tokens
            if token_count:
                session.add(
                    UsageEvent(
                        id=str(uuid4()),
                        organization_id=project.organization_id,
                        project_id=project.id,
                        event_type="ai_tokens",
                        quantity=token_count,
                    )
                )
            session.commit()
        except Exception as error:
            proposal.state = "failed"
            job.state = "failed"
            job.error_code = error.__class__.__name__
            job.error_message = str(error)[:2_000]
            job.completed_at = datetime.now(UTC)
            session.commit()


def _run_snapshot_page_package_generation(
    session: Session,
    proposal: PagePackageProposal,
    job: Job,
    opportunity: KeywordOpportunity,
    project: Project,
    blueprint: PageBlueprint | None,
) -> None:
    active_stage_name = "template"
    active_attempt_token: str | None = None
    try:
        template = locked_stage(session, proposal.id, "template")
        if template.state == "pending":
            template = begin_stage(session, proposal.id, "template")
            active_attempt_token = template.attempt_token
            job.state = "running"
            job.progress = 5
            job.started_at = job.started_at or datetime.now(UTC)
            session.commit()
            if blueprint is None:
                raise ValueError("Snapshot changed before generation started")
            _require_stored_snapshot_identity(proposal, blueprint)
            complete_stage(
                session,
                proposal.id,
                "template",
                result=_snapshot_identity(blueprint),
                attempt_token=active_attempt_token,
            )
            job.progress = 20
            session.commit()
        elif template.state == "running":
            try:
                template = reclaim_stale_running_stage(
                    session, proposal.id, "template"
                )
            except ValueError as error:
                if str(error) == "stage_in_progress":
                    return
                raise
            active_attempt_token = template.attempt_token
            job.state = "running"
            job.progress = 5
            job.started_at = job.started_at or datetime.now(UTC)
            session.commit()
            if blueprint is None:
                raise ValueError("Snapshot changed before generation started")
            _require_stored_snapshot_identity(proposal, blueprint)
            complete_stage(
                session,
                proposal.id,
                "template",
                result=_snapshot_identity(blueprint),
                attempt_token=active_attempt_token,
            )
            job.progress = 20
            session.commit()
        elif template.state != "ready":
            return

        text = locked_stage(session, proposal.id, "text")
        generated_text = text.result
        if text.state == "pending":
            active_stage_name = "text"
            text = begin_stage(session, proposal.id, "text")
            active_attempt_token = text.attempt_token
            job.state = "running"
            job.progress = 30
            job.started_at = job.started_at or datetime.now(UTC)
            session.commit()
            if blueprint is None:
                raise ValueError("Snapshot changed before text generation")
            context = _proposal_generation_context(
                session,
                proposal,
                project,
                opportunity,
                blueprint,
            )
            generated = PagePackageGenerationResult.model_validate(
                _page_package_generator(session, project).generate_page_package(context)
            )
            generated_text = (
                generated.package.model_dump(mode="json")
                if hasattr(generated.package, "model_dump")
                else generated.package
            )
            complete_stage(
                session,
                proposal.id,
                "text",
                result=generated_text,
                attempt_token=active_attempt_token,
            )
            proposal.provider = generated.provider or proposal.provider
            proposal.model = generated.model or proposal.model
            proposal.input_tokens = generated.input_tokens
            proposal.output_tokens = generated.output_tokens
            job.progress = 70
            token_count = generated.input_tokens + generated.output_tokens
            if token_count:
                session.add(
                    UsageEvent(
                        id=str(uuid4()),
                        organization_id=project.organization_id,
                        project_id=project.id,
                        event_type="ai_tokens",
                        quantity=token_count,
                    )
                )
            session.commit()
        elif text.state == "running":
            active_stage_name = "text"
            try:
                text = reclaim_stale_running_stage(session, proposal.id, "text")
            except ValueError as error:
                if str(error) == "stage_in_progress":
                    return
                raise
            active_attempt_token = text.attempt_token
            job.state = "running"
            job.progress = 30
            job.started_at = job.started_at or datetime.now(UTC)
            session.commit()
            if blueprint is None:
                raise ValueError("Snapshot changed before text generation")
            context = _proposal_generation_context(
                session,
                proposal,
                project,
                opportunity,
                blueprint,
            )
            generated = PagePackageGenerationResult.model_validate(
                _page_package_generator(session, project).generate_page_package(context)
            )
            generated_text = (
                generated.package.model_dump(mode="json")
                if hasattr(generated.package, "model_dump")
                else generated.package
            )
            complete_stage(
                session,
                proposal.id,
                "text",
                result=generated_text,
                attempt_token=active_attempt_token,
            )
            proposal.provider = generated.provider or proposal.provider
            proposal.model = generated.model or proposal.model
            proposal.input_tokens = generated.input_tokens
            proposal.output_tokens = generated.output_tokens
            job.progress = 70
            token_count = generated.input_tokens + generated.output_tokens
            if token_count:
                session.add(
                    UsageEvent(
                        id=str(uuid4()),
                        organization_id=project.organization_id,
                        project_id=project.id,
                        event_type="ai_tokens",
                        quantity=token_count,
                    )
                )
            session.commit()
        elif text.state != "ready":
            return

        validation = locked_stage(session, proposal.id, "validation")
        if validation.state == "pending":
            active_stage_name = "validation"
            validation = begin_stage(session, proposal.id, "validation")
            active_attempt_token = validation.attempt_token
            job.progress = 80
            session.commit()
            if blueprint is None:
                raise ValueError("Snapshot changed before validation")
            context = _proposal_generation_context(
                session,
                proposal,
                project,
                opportunity,
                blueprint,
            )
            _apply_snapshot_validation(
                session,
                proposal,
                job,
                context,
                generated_text,
                active_attempt_token,
            )
            session.commit()
        elif validation.state == "running":
            active_stage_name = "validation"
            try:
                validation = reclaim_stale_running_stage(
                    session, proposal.id, "validation"
                )
            except ValueError as error:
                if str(error) == "stage_in_progress":
                    return
                raise
            active_attempt_token = validation.attempt_token
            job.state = "running"
            job.progress = 80
            session.commit()
            if blueprint is None:
                raise ValueError("Snapshot changed before validation")
            context = _proposal_generation_context(
                session,
                proposal,
                project,
                opportunity,
                blueprint,
            )
            _apply_snapshot_validation(
                session,
                proposal,
                job,
                context,
                generated_text,
                active_attempt_token,
            )
            session.commit()
    except Exception as error:
        _fail_snapshot_generation(
            session,
            proposal,
            job,
            active_stage_name,
            error,
            active_attempt_token,
        )


def _apply_snapshot_validation(
    session: Session,
    proposal: PagePackageProposal,
    job: Job,
    context: PagePackageContext,
    generated_text: dict,
    attempt_token: str,
) -> None:
    validation = normalize_snapshot_text_package(generated_text, context)
    field_errors = dict(validation.field_errors)
    for field_id in validation.missing_required_field_ids:
        field_errors.setdefault(field_id, "required")
    result = {
        **_snapshot_validation_result(validation.replacements, context),
        "field_errors": validation.field_errors,
        "blocking_field_ids": validation.blocking_field_ids,
        "ignored_field_ids": validation.ignored_field_ids,
        "missing_required_field_ids": validation.missing_required_field_ids,
    }
    if validation.ready and not validation.field_errors:
        complete_stage(
            session,
            proposal.id,
            "validation",
            result=result,
            attempt_token=attempt_token,
        )
        proposal_state = "proposed"
    else:
        attention_stage(
            session,
            proposal.id,
            "validation",
            result=result,
            errors=dict(sorted(field_errors.items())),
            attempt_token=attempt_token,
        )
        proposal_state = "needs_attention"
    proposal.package = {"text_replacements": validation.replacements}
    proposal.rendered_html = ""
    proposal.state = proposal_state
    job.state = "completed"
    job.progress = 100
    job.error_code = None
    job.error_message = None
    job.checkpoint = {**job.checkpoint, "proposal_id": proposal.id}
    job.completed_at = datetime.now(UTC)


def _snapshot_validation_result(
    replacements: dict[str, str],
    context: PagePackageContext,
) -> dict:
    return {
        "text_replacements": replacements,
        "approved_urls": sorted(
            {
                link.url
                for link in getattr(context, "internal_link_candidates", [])
            }
            | set(getattr(context, "approved_cta_urls", []))
        ),
    }


def _fail_snapshot_generation(
    session: Session,
    proposal: PagePackageProposal,
    job: Job,
    stage_name: str,
    error: Exception,
    attempt_token: str | None,
) -> None:
    message = str(error)[:2_000]
    try:
        stage = locked_stage(session, proposal.id, stage_name)
        if attempt_token is not None and stage.attempt_token != attempt_token:
            session.rollback()
            return
        if stage.state == "running" and attempt_token is not None:
            fail_stage(
                session,
                proposal.id,
                stage_name,
                errors={"message": message},
                attempt_token=attempt_token,
            )
    except ValueError as stage_error:
        if str(stage_error) == "stale_stage_attempt":
            session.rollback()
            return
        pass
    proposal.state = "failed"
    job.state = "failed"
    job.error_code = error.__class__.__name__
    job.error_message = message
    job.completed_at = datetime.now(UTC)
    session.commit()


@router.get("/page-proposals/{proposal_id}")
def get_page_package_proposal(
    project_id: str,
    proposal_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    _project_or_404(session, user, project_id)
    return _proposal_payload(
        session, _proposal_or_404(session, project_id, proposal_id)
    )


@router.post(
    "/page-proposals/{proposal_id}/stages/{stage_name}/retry",
    status_code=202,
)
def retry_page_proposal_stage(
    project_id: str,
    proposal_id: str,
    stage_name: str,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    proposal = _proposal_or_404(session, project_id, proposal_id, lock=True)
    if not _is_snapshot_schema(proposal.config_snapshot.get("content_schema")):
        raise HTTPException(
            status_code=409,
            detail="Legacy proposal stages cannot be retried",
        )
    if stage_name == "text":
        try:
            next_version = _create_snapshot_text_retry_version(
                session,
                proposal,
                user.id,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        background_tasks.add_task(
            _run_page_package_generation,
            background_engine(session),
            next_version.id,
        )
        return _proposal_payload(session, next_version)
    if stage_name != "validation":
        raise HTTPException(status_code=404, detail="Proposal stage not found")
    if not proposal.is_current:
        raise HTTPException(
            status_code=409,
            detail="Only the current proposal version can be retried",
        )
    blueprint = _proposal_blueprint_or_409(session, proposal)
    opportunity = session.get(KeywordOpportunity, proposal.opportunity_id)
    job = session.get(Job, proposal.job_id)
    if opportunity is None or job is None:
        raise HTTPException(status_code=409, detail="Proposal context is unavailable")
    text = locked_stage(session, proposal.id, "text")
    if text.state != "ready":
        raise HTTPException(
            status_code=409,
            detail="Proposal text is not ready for validation",
        )
    try:
        validation = retry_stage(session, proposal.id, "validation")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    proposal.state = "generating"
    job.state = "running"
    job.progress = 80
    job.completed_at = None
    session.commit()
    try:
        context = _proposal_generation_context(
            session,
            proposal,
            project,
            opportunity,
            blueprint,
        )
        stored_replacements = proposal.package.get("text_replacements", {})
        if not isinstance(stored_replacements, dict):
            raise ValueError("Stored snapshot package is invalid")
        _apply_snapshot_validation(
            session,
            proposal,
            job,
            context,
            {
                "text_replacements": {
                    field_id: {"value": value}
                    for field_id, value in stored_replacements.items()
                }
            },
            validation.attempt_token,
        )
        session.commit()
    except Exception as error:
        _fail_snapshot_generation(
            session,
            proposal,
            job,
            "validation",
            error,
            validation.attempt_token,
        )
    return _proposal_payload(session, proposal)


@router.put("/page-proposals/{proposal_id}")
def update_page_package_proposal(
    project_id: str,
    proposal_id: str,
    payload: PagePackageProposalWrite,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    proposal = _proposal_or_404(session, project_id, proposal_id, lock=True)
    blueprint = _proposal_blueprint_or_409(session, proposal)
    project = session.get(Project, proposal.project_id)
    opportunity = session.get(KeywordOpportunity, proposal.opportunity_id)
    if project is None or opportunity is None:
        raise HTTPException(status_code=409, detail="Proposal context is unavailable")

    if _is_snapshot_schema(proposal.config_snapshot.get("content_schema")):
        if not proposal.is_current:
            raise HTTPException(
                status_code=409,
                detail="Only the current snapshot proposal version can be edited",
            )
        if proposal.state not in {"needs_attention", "proposed"}:
            raise HTTPException(
                status_code=409,
                detail="Only proposed snapshot proposals can be edited",
            )
        if not isinstance(payload.package, GeneratedSnapshotTextPackage):
            raise HTTPException(
                status_code=422,
                detail="Snapshot proposals require field-ID text replacements",
            )
        text = locked_stage(session, proposal.id, "text")
        if text.state != "ready":
            raise HTTPException(
                status_code=409,
                detail="Proposal text is not ready for validation",
            )
        if proposal.state == "needs_attention":
            try:
                validation = retry_stage(session, proposal.id, "validation")
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
        else:
            validation = locked_stage(session, proposal.id, "validation")
            if validation.state != "ready":
                raise HTTPException(
                    status_code=409,
                    detail="Proposal validation is not ready for editing",
                )
            validation.state = "running"
            validation.retry_count += 1
            validation.started_at = datetime.now(UTC)
            validation.last_retried_at = validation.started_at
            validation.completed_at = None
            validation.result = {}
            validation.errors = {}
            validation.attempt_token = str(uuid4())
        job = session.get(Job, proposal.job_id)
        if job is None:
            raise HTTPException(status_code=409, detail="Proposal job is unavailable")
        proposal.state = "generating"
        job.state = "running"
        job.progress = 80
        job.completed_at = None
        _apply_snapshot_validation(
            session,
            proposal,
            job,
            _proposal_generation_context(
                session,
                proposal,
                project,
                opportunity,
                blueprint,
            ),
            payload.package.model_dump(mode="json"),
            validation.attempt_token,
        )
        session.commit()
        return _proposal_payload(session, proposal)

    if proposal.state != "proposed":
        raise HTTPException(status_code=409, detail="Only proposed pages can be edited")
    if not isinstance(payload.package, GeneratedBlueprintPackage):
        raise HTTPException(
            status_code=422,
            detail="Legacy proposals require a blueprint package",
        )
    package = GeneratedBlueprintPackage.model_validate(payload.package)
    validate_blueprint_replacements(
        package,
        _proposal_generation_context(
            session,
            proposal,
            project,
            opportunity,
            blueprint,
        ),
    )
    proposal.package = package.model_dump()
    proposal.rendered_html = ""
    session.commit()
    return _proposal_payload(session, proposal)


@router.post("/page-proposals/{proposal_id}/approve")
def approve_page_package_proposal(
    project_id: str,
    proposal_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    proposal = _proposal_or_404(session, project_id, proposal_id, lock=True)
    if (
        _is_snapshot_schema(proposal.config_snapshot.get("content_schema"))
        and not proposal.is_current
    ):
        raise HTTPException(
            status_code=409,
            detail="Only the current snapshot proposal version can be approved",
        )
    snapshot_schema = _is_snapshot_schema(
        proposal.config_snapshot.get("content_schema")
    )
    if proposal.state != "proposed" and not (
        snapshot_schema and proposal.state == "needs_attention"
    ):
        raise HTTPException(
            status_code=409, detail="Only proposed pages can be approved"
        )
    blueprint = _proposal_blueprint_or_409(session, proposal)
    project_context = session.get(Project, proposal.project_id)
    opportunity = session.get(KeywordOpportunity, proposal.opportunity_id)
    if project_context is None or opportunity is None:
        raise HTTPException(status_code=409, detail="Proposal context is unavailable")
    if proposal.source_wordpress_page_id is not None:
        source_page = session.get(WordPressPage, proposal.source_wordpress_page_id)
        if (
            source_page is None
            or opportunity.target_classification != "existing_page"
            or opportunity.target_url != source_page.url
        ):
            raise HTTPException(
                status_code=409,
                detail="Opportunity target changed; generate again",
            )
    if snapshot_schema:
        validation = session.scalar(
            select(PageProposalStage)
            .where(
                PageProposalStage.proposal_version_id == proposal.id,
                PageProposalStage.name == "validation",
            )
            .with_for_update()
        )
        if validation is None:
            job = session.get(Job, proposal.job_id)
            if job is None or job.job_type != "page_package_snapshot_migration":
                raise HTTPException(
                    status_code=409,
                    detail="Proposal validation stages are unavailable",
                )
            package = GeneratedBlueprintPackage.model_validate(proposal.package)
            context = _proposal_generation_context(
                session,
                proposal,
                project_context,
                opportunity,
                blueprint,
            )
            generated = {
                "text_replacements": {
                    **{
                        replacement.field_id: {"value": replacement.value}
                        for replacement in package.replacements
                    },
                    "document:title": {"value": package.title},
                    "document:slug": {"value": package.slug},
                    "seo:title": {"value": package.seo_title},
                    "seo:meta_description": {
                        "value": package.meta_description
                    },
                    "seo:focus_keyword": {"value": package.focus_keyword},
                }
            }
            migrated_validation = normalize_snapshot_text_package(
                generated,
                context,
            )
            if not migrated_validation.ready:
                raise HTTPException(
                    status_code=409,
                    detail="Migrated proposal requires regeneration",
                )
            validation = PageProposalStage(
                proposal_version_id=proposal.id,
                name="validation",
                state="ready",
                result={
                    **_snapshot_validation_result(
                        migrated_validation.replacements,
                        context,
                    ),
                    "field_errors": migrated_validation.field_errors,
                    "blocking_field_ids": migrated_validation.blocking_field_ids,
                    "ignored_field_ids": migrated_validation.ignored_field_ids,
                    "missing_required_field_ids": (
                        migrated_validation.missing_required_field_ids
                    ),
                },
                errors={},
                completed_at=datetime.now(UTC),
            )
            session.add(validation)
            proposal.package = {
                "text_replacements": migrated_validation.replacements
            }
        elif validation.state == "attention":
            if validation.result.get("blocking_field_ids") or validation.result.get(
                "missing_required_field_ids"
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Proposal validation requires field correction",
                )
        elif validation.state != "ready":
            raise HTTPException(
                status_code=409,
                detail="Proposal validation is not ready",
            )
    else:
        package = GeneratedBlueprintPackage.model_validate(proposal.package)
        validate_blueprint_replacements(
            package,
            _proposal_generation_context(
                session,
                proposal,
                project_context,
                opportunity,
                blueprint,
            ),
        )
    if proposal.source_wordpress_page_id is None:
        _require_current_wordpress_blueprint(session, project_id, blueprint)
    else:
        try:
            _require_stored_snapshot_identity(proposal, blueprint)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    proposal.state = "approved"
    proposal.approved_by = user.id
    proposal.approved_at = datetime.now(UTC)
    cancel_ineligible_draft_jobs(
        session,
        proposal.project_id,
        proposal.proposal_group_id,
        eligible_proposal_version_id=proposal.id,
    )
    session.commit()
    return _proposal_payload(session, proposal)


@router.post("/page-proposals/{proposal_id}/regenerate", status_code=202)
def regenerate_page_package_proposal(
    project_id: str,
    proposal_id: str,
    payload: PageProposalRegenerationRequest,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    proposal = _proposal_or_404(session, project_id, proposal_id, lock=True)
    if proposal.state != "approved" or not proposal.is_current:
        raise HTTPException(
            status_code=409,
            detail="Only the current approved proposal can be regenerated",
        )
    candidate = create_regeneration_candidate(
        session,
        proposal,
        mode=payload.mode,
        target_block_id=payload.target_block_id,
        instruction=payload.instruction,
        candidate_package=regeneration_candidate_payload(proposal.package, payload),
        candidate_rendered_html=proposal.rendered_html,
        provider=proposal.provider,
        model=proposal.model,
        prompt_version=proposal.prompt_version,
        status="generating",
    )
    background_tasks.add_task(
        _run_page_package_regeneration,
        background_engine(session),
        candidate.id,
    )
    return {
        "base_version": _proposal_payload(session, proposal),
        "candidate": _candidate_payload(candidate),
    }


def _run_page_package_regeneration(bind, candidate_id: str) -> None:
    with Session(bind) as session:
        candidate = session.get(PagePackageRegenerationCandidate, candidate_id)
        if candidate is None or candidate.status != "generating":
            return
        base = session.get(PagePackageProposal, candidate.base_version_id)
        if base is None:
            candidate.status = "failed"
            candidate.candidate_package = {
                "_generation_error": "Base proposal not found"
            }
            session.commit()
            return
        project = session.get(Project, base.project_id)
        opportunity = session.get(KeywordOpportunity, base.opportunity_id)
        blueprint = session.scalar(
            select(PageBlueprint).where(
                PageBlueprint.project_id == base.project_id,
                PageBlueprint.id == base.blueprint_id,
                PageBlueprint.version == base.blueprint_version,
                PageBlueprint.structure_hash == base.blueprint_structure_hash,
                PageBlueprint.state == "ready",
            )
        )
        if project is None or opportunity is None or blueprint is None:
            candidate.status = "failed"
            candidate.candidate_package = {
                "_generation_error": "Blueprint context is unavailable"
            }
            session.commit()
            return
        try:
            context = _proposal_generation_context(
                session,
                base,
                project,
                opportunity,
                blueprint,
            )
            guidance = "Regeneratie-instructie: " + (
                candidate.instruction or "Maak een verbeterde versie."
            )
            if candidate.target_block_id:
                guidance += f" Pas primair blok {candidate.target_block_id} aan."
            context = context.model_copy(
                update={"company_context": context.company_context + "\n" + guidance}
            )
            generated = PagePackageGenerationResult.model_validate(
                _page_package_generator(session, project).generate_page_package(context)
            )
            raw_package = (
                generated.package.model_dump(mode="json")
                if hasattr(generated.package, "model_dump")
                else generated.package
            )
            if _is_snapshot_schema(base.config_snapshot.get("content_schema")):
                validation = normalize_snapshot_text_package(raw_package, context)
                if not validation.ready:
                    raise ValueError("Snapshot candidate requires correction")
                base_replacements = base.package.get("text_replacements", {})
                if not isinstance(base_replacements, dict):
                    raise ValueError("Base snapshot package is invalid")
                replacements = {
                    **base_replacements,
                    **validation.replacements,
                }
                candidate.candidate_package = {
                    "text_replacements": replacements,
                    "approved_urls": _snapshot_validation_result(
                        replacements,
                        context,
                    )["approved_urls"],
                }
            else:
                package = normalize_blueprint_package(raw_package, context)
                package = validate_blueprint_replacements(package, context)
                candidate.candidate_package = package.model_dump()
            candidate.candidate_rendered_html = ""
            candidate.provider = generated.provider or candidate.provider
            candidate.model = generated.model or candidate.model
            candidate.prompt_version = prompt_version(context, candidate.model or "")
            candidate.input_tokens = generated.input_tokens
            candidate.output_tokens = generated.output_tokens
            candidate.status = "ready"
        except Exception as error:
            candidate.status = "failed"
            candidate.candidate_package = {"_generation_error": str(error)[:2_000]}
        session.commit()


@router.post("/page-proposals/candidates/{candidate_id}/accept")
def accept_page_package_regeneration_candidate(
    project_id: str,
    candidate_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    try:
        accepted = accept_regeneration_candidate_with_revocations(
            session,
            candidate_id,
            user.id,
            expected_project_id=project_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "current_version": _proposal_payload(session, accepted.proposal),
        "revoked_handoff_ids": accepted.revoked_handoff_ids,
    }


@router.post("/page-proposals/candidates/{candidate_id}/discard")
def discard_page_package_regeneration_candidate(
    project_id: str,
    candidate_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    try:
        candidate = discard_regeneration_candidate(
            session,
            candidate_id,
            expected_project_id=project_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"candidate": _candidate_payload(candidate)}


@router.post("/page-proposals/{proposal_id}/handoffs")
def issue_page_package_proposal_handoff(
    project_id: str,
    proposal_id: str,
    request: Request,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    proposal = _proposal_or_404(session, project_id, proposal_id, lock=True)
    try:
        issued = issue_page_package_handoff(session, proposal, user.id)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    connection = session.scalar(
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="WordPress connection not found")
    return {
        "handoff": _handoff_payload(issued.record),
        "code": issued.raw_code,
        "import_url": _build_handoff_import_url(
            connection.site_url,
            issued.raw_code,
            backend_base_url=_handoff_backend_base_url(
                request,
                project_id,
                proposal_id,
            ),
        ),
    }


@router.post("/page-proposals/handoffs/redeem")
async def redeem_page_package_proposal_handoff(
    project_id: str,
    payload: PageProposalHandoffRedeemRequest,
    request: Request,
    session: SessionDependency,
    x_wp_fixpilot_timestamp: str = Header(...),
    x_wp_fixpilot_nonce: str = Header(...),
    x_wp_fixpilot_signature: str = Header(...),
) -> dict:
    _verify_plugin_request(
        session,
        project_id,
        request.url.path,
        "POST",
        payload.model_dump(),
        x_wp_fixpilot_timestamp=x_wp_fixpilot_timestamp,
        x_wp_fixpilot_nonce=x_wp_fixpilot_nonce,
        x_wp_fixpilot_signature=x_wp_fixpilot_signature,
    )
    try:
        redeemed = redeem_page_package_handoff(
            session,
            payload.code,
            payload.site_url,
            payload.wordpress_user_id,
            expected_project_id=project_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "handoff": _handoff_payload(redeemed.handoff),
        "package": _import_package_payload(session, redeemed.proposal),
    }


@router.post("/page-proposals/handoffs/{handoff_id}/complete")
async def complete_page_package_proposal_handoff(
    project_id: str,
    handoff_id: str,
    payload: PageProposalHandoffCompleteRequest,
    request: Request,
    session: SessionDependency,
    x_wp_fixpilot_timestamp: str = Header(...),
    x_wp_fixpilot_nonce: str = Header(...),
    x_wp_fixpilot_signature: str = Header(...),
) -> dict:
    _verify_plugin_request(
        session,
        project_id,
        request.url.path,
        "POST",
        payload.model_dump(),
        x_wp_fixpilot_timestamp=x_wp_fixpilot_timestamp,
        x_wp_fixpilot_nonce=x_wp_fixpilot_nonce,
        x_wp_fixpilot_signature=x_wp_fixpilot_signature,
    )
    try:
        handoff = complete_page_package_handoff(
            session,
            handoff_id,
            wordpress_object_id=payload.wordpress_object_id,
            edit_url=payload.edit_url,
            expected_project_id=project_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    proposal = session.get(PagePackageProposal, handoff.proposal_version_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal version not found")
    return {
        "handoff": _handoff_payload(handoff),
        "proposal_version": _proposal_payload(session, proposal),
    }


@router.post("/page-proposals/handoffs/{handoff_id}/revoke")
def revoke_page_package_proposal_handoff(
    project_id: str,
    handoff_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    try:
        handoff = revoke_page_package_handoff(
            session,
            handoff_id,
            expected_project_id=project_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"handoff": _handoff_payload(handoff)}


@router.post("/page-proposals/{proposal_id}/create-draft")
def create_wordpress_draft(
    project_id: str,
    proposal_id: str,
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    project = _project_or_404(session, user, project_id)
    _require_manager(session, user, project.organization_id)
    proposal = _proposal_or_404(session, project_id, proposal_id, lock=True)
    if proposal.state == "draft_created" and proposal.wordpress_object_id:
        return _proposal_payload(session, proposal)
    if proposal.state != "approved" or not proposal.approved_by:
        raise HTTPException(
            status_code=409,
            detail="Approve the page proposal before creating a WordPress draft",
        )
    outbound_job = session.scalar(
        select(WordPressDraftJob).where(
            WordPressDraftJob.proposal_version_id == proposal.id,
            WordPressDraftJob.state.in_(("queued", "claimed", "completed")),
        )
    )
    if outbound_job is not None:
        if outbound_job.state == "completed" and outbound_job.wordpress_object_id:
            proposal.state = "draft_created"
            proposal.wordpress_object_id = outbound_job.wordpress_object_id
            proposal.wordpress_edit_url = outbound_job.wordpress_edit_url
            session.commit()
            return _proposal_payload(session, proposal)
        raise HTTPException(
            status_code=409, detail="Outbound WordPress delivery is already active"
        )
    if proposal.source_wordpress_page_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Existing-page drafts require the outbound draft-job path",
        )
    blueprint = _proposal_blueprint_or_409(session, proposal)
    _require_current_wordpress_blueprint(session, project_id, blueprint)
    opportunity = session.get(KeywordOpportunity, proposal.opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=409, detail="Proposal context is unavailable")
    package = GeneratedBlueprintPackage.model_validate(proposal.package)
    context = _proposal_generation_context(
        session,
        proposal,
        project,
        opportunity,
        blueprint,
    )
    validate_blueprint_replacements(package, context)
    replacements = {
        replacement.field_id: replacement.value for replacement in package.replacements
    }
    url_field_ids = {
        field["id"]
        for block in blueprint.content_schema.get("blocks", [])
        for field in block.get("fields", [])
        if field.get("value_type") == "url"
    }
    approved_urls = sorted(
        {link.url for link in package.internal_links}
        | {
            replacement.value
            for replacement in package.replacements
            if replacement.field_id in url_field_ids
        }
    )
    proposal.state = "draft_in_progress"
    session.flush()
    try:
        result = _page_package_client(session, project_id).create_blueprint_draft(
            blueprint.wordpress_blueprint_id,
            {
                "expected_version": proposal.blueprint_version,
                "expected_structure_hash": proposal.blueprint_structure_hash,
                "idempotency_key": proposal.id,
                "replacements": replacements,
                "approved_urls": approved_urls,
                "seo": {
                    "title": package.seo_title,
                    "description": package.meta_description,
                    "keyword": package.focus_keyword,
                },
            },
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="WordPress draft creation failed",
        ) from error
    if result.get("status") != "draft" or not result.get("wordpress_object_id"):
        raise HTTPException(status_code=502, detail="WordPress did not return a draft")
    proposal.state = "draft_created"
    proposal.wordpress_object_id = int(result["wordpress_object_id"])
    proposal.wordpress_edit_url = str(result.get("edit_url") or "") or None
    session.commit()
    return _proposal_payload(session, proposal)


def _proposal_blueprint_or_409(
    session: Session, proposal: PagePackageProposal
) -> PageBlueprint:
    blueprint = session.scalar(
        select(PageBlueprint).where(
            PageBlueprint.project_id == proposal.project_id,
            PageBlueprint.id == proposal.blueprint_id,
            PageBlueprint.version == proposal.blueprint_version,
            PageBlueprint.structure_hash == proposal.blueprint_structure_hash,
        )
    )
    if (
        blueprint is None
        or blueprint.state != "ready"
        or blueprint.content_schema != proposal.config_snapshot.get("content_schema")
    ):
        raise HTTPException(
            status_code=409,
            detail="Blueprint changed; generate a new proposal",
        )
    return blueprint


def _require_current_wordpress_blueprint(
    session: Session,
    project_id: str,
    blueprint: PageBlueprint,
) -> None:
    wordpress_id = (
        blueprint.wordpress_snapshot_id
        if blueprint.wordpress_snapshot_id is not None
        else blueprint.wordpress_blueprint_id
    )
    try:
        current = _page_package_client(session, project_id).blueprint(
            wordpress_id
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="WordPress blueprint validation failed",
        ) from error
    identity_changed = (
        current.get("status") != "ready"
        or current.get("version") != blueprint.version
        or current.get("structure_hash") != blueprint.structure_hash
    )
    if blueprint.wordpress_snapshot_id is not None:
        expected_snapshot_identity = {
            "wordpress_blueprint_id": blueprint.wordpress_snapshot_id,
            "wordpress_snapshot_id": blueprint.wordpress_snapshot_id,
            "post_type": "wpfixpilot_snapshot",
            "adapter_version": blueprint.adapter_version,
            "schema_version": blueprint.schema_version,
            "builder": blueprint.builder,
            "seo_plugin": blueprint.seo_plugin,
            "snapshot_version": blueprint.snapshot_version,
        }
        identity_changed = identity_changed or any(
            current.get(key) != value
            for key, value in expected_snapshot_identity.items()
        )
    if identity_changed:
        blueprint.state = "stale"
        blueprint.is_default_for_page_type = False
        session.commit()
        raise HTTPException(
            status_code=409,
            detail="Blueprint structure changed; generate a new proposal",
        )


def _is_snapshot_schema(value: object) -> bool:
    return isinstance(value, dict) and value.get("schema_version") == (
        "snapshot-text-v1"
    )


def _snapshot_identity(blueprint: PageBlueprint) -> dict:
    return {
        "wordpress_snapshot_id": blueprint.wordpress_snapshot_id,
        "snapshot_version": blueprint.snapshot_version,
        "schema_version": blueprint.schema_version,
        "structure_hash": blueprint.structure_hash,
    }


def _require_stored_snapshot_identity(
    proposal: PagePackageProposal,
    blueprint: PageBlueprint,
) -> None:
    expected = {
        "wordpress_snapshot_id": proposal.config_snapshot.get(
            "wordpress_snapshot_id"
        ),
        "snapshot_version": proposal.config_snapshot.get("snapshot_version"),
        "schema_version": proposal.config_snapshot.get("schema_version"),
        "structure_hash": proposal.config_snapshot.get("structure_hash"),
    }
    if (
        any(value is None for value in expected.values())
        or _snapshot_identity(blueprint) != expected
        or blueprint.content_schema != proposal.config_snapshot.get("content_schema")
    ):
        raise ValueError("Snapshot identity changed before generation started")


def _create_snapshot_text_retry_version(
    session: Session,
    proposal: PagePackageProposal,
    actor_id: str,
) -> PagePackageProposal:
    if not proposal.is_current or proposal.state not in {"needs_attention", "failed"}:
        raise ValueError(
            "Only the current attention or failed proposal can retry text"
        )
    template = locked_stage(session, proposal.id, "template")
    text = locked_stage(session, proposal.id, "text")
    validation = locked_stage(session, proposal.id, "validation")
    if template.state != "ready":
        raise ValueError("Proposal template is not ready")
    if text.state == "ready" and validation.state not in {"attention", "failed"}:
        raise ValueError("Proposal text is not retryable")
    if text.state not in {"ready", "attention", "failed"}:
        raise ValueError("Proposal text is not retryable")

    next_version_id = str(uuid4())
    job = Job(
        id=str(uuid4()),
        project_id=proposal.project_id,
        job_type="page_package_generation",
        state="queued",
        progress=0,
        checkpoint={
            "opportunity_id": proposal.opportunity_id,
            "retry_of_proposal_id": proposal.id,
        },
    )
    next_version = PagePackageProposal(
        id=next_version_id,
        project_id=proposal.project_id,
        opportunity_id=proposal.opportunity_id,
        job_id=job.id,
        state="generating",
        proposal_group_id=proposal.proposal_group_id,
        version_number=proposal.version_number + 1,
        parent_version_id=proposal.id,
        current_version_id=next_version_id,
        is_current=True,
        generation_mode="full",
        source_wordpress_page_id=proposal.source_wordpress_page_id,
        blueprint_id=proposal.blueprint_id,
        blueprint_version=proposal.blueprint_version,
        blueprint_structure_hash=proposal.blueprint_structure_hash,
        package={},
        rendered_html="",
        config_snapshot=proposal.config_snapshot,
        provider=proposal.provider,
        model=proposal.model,
        prompt_version=proposal.prompt_version,
        proposed_by=actor_id,
    )
    session.query(PagePackageProposal).filter(
        PagePackageProposal.proposal_group_id == proposal.proposal_group_id
    ).update(
        {
            PagePackageProposal.current_version_id: next_version_id,
            PagePackageProposal.is_current: False,
        },
        synchronize_session="fetch",
    )
    session.add_all([job, next_version])
    initialize_proposal_stages(session, next_version.id)
    session.flush()
    template_stage = begin_stage(session, next_version.id, "template")
    complete_stage(
        session,
        next_version.id,
        "template",
        result=dict(template.result),
        attempt_token=template_stage.attempt_token,
    )
    session.commit()
    session.refresh(next_version)
    return next_version


def _page_package_generator(session: Session, project):
    profile = session.get(CompanyProfile, project.id)
    company_context = _company_context(profile)
    policy = session.get(ProjectAiPolicy, project.id)
    if policy is None:
        raise HTTPException(
            status_code=422, detail="Project AI model is not configured"
        )
    primary = session.get(AiConnection, policy.primary_connection_id)
    if (
        primary is None
        or primary.organization_id != project.organization_id
        or not primary.enabled
    ):
        raise HTTPException(
            status_code=422, detail="Project AI connection is unavailable"
        )
    primary_generator = build_generator(primary, policy.primary_model, company_context)
    fallback_generator = None
    if policy.fallback_connection_id and policy.fallback_model:
        fallback = session.get(AiConnection, policy.fallback_connection_id)
        if (
            fallback is not None
            and fallback.organization_id == project.organization_id
            and fallback.enabled
        ):
            fallback_generator = build_generator(
                fallback, policy.fallback_model, company_context
            )
    return PolicyPagePackageGenerator(primary_generator, fallback_generator)


def _proposal_generation_context(
    session: Session,
    proposal: PagePackageProposal,
    project: Project,
    opportunity: KeywordOpportunity,
    blueprint: PageBlueprint,
) -> PagePackageContext:
    if getattr(proposal, "source_wordpress_page_id", None) is not None:
        return build_context(session, proposal)
    return _generation_context(session, project, opportunity, blueprint)


def _generation_context(
    session: Session,
    project,
    opportunity: KeywordOpportunity,
    blueprint: PageBlueprint,
) -> PagePackageContext:
    profile = session.get(CompanyProfile, project.id)
    pages = session.scalars(
        select(WordPressPage)
        .where(WordPressPage.project_id == project.id)
        .order_by(WordPressPage.title)
        .limit(500)
    ).all()
    links = [
        InternalLink(anchor=page.title or page.slug, url=page.url)
        for page in pages
        if page.title or page.slug
    ]
    if not links:
        links = [InternalLink(anchor=project.name, url=project.domain)]
    approved_cta_urls = [
        field["current_value"]
        for block in blueprint.content_schema.get("blocks", [])
        for field in block.get("fields", [])
        if field.get("value_type") == "url" and field.get("current_value")
    ]
    return PagePackageContext(
        keyword=opportunity.keyword,
        search_volume=opportunity.search_volume,
        intent=opportunity.intent,
        company_context=_company_context(profile),
        project_domain=project.domain,
        internal_link_candidates=links,
        template_slots={},
        approved_cta_urls=approved_cta_urls,
        blueprint_schema=blueprint.content_schema,
    )


def _company_context(profile: CompanyProfile | None) -> str:
    if profile is None:
        return ""
    return "\n".join(
        [
            f"Bedrijf: {profile.company_name}",
            f"Omschrijving: {profile.description}",
            f"Doelgroep: {profile.audience}",
            f"Diensten: {', '.join(profile.services)}",
            f"Tone of voice: {profile.tone_of_voice}",
            f"Projectprompt: {profile.custom_prompt}",
        ]
    )[:10_000]


def _proposal_or_404(
    session: Session,
    project_id: str,
    proposal_id: str,
    *,
    lock: bool = False,
) -> PagePackageProposal:
    statement = select(PagePackageProposal).where(
        PagePackageProposal.id == proposal_id,
        PagePackageProposal.project_id == project_id,
    )
    if lock:
        statement = statement.with_for_update()
    proposal = session.scalar(statement)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Page proposal not found")
    return proposal


def _proposal_payload(session: Session, proposal: PagePackageProposal) -> dict:
    job = session.get(Job, proposal.job_id)
    stages = ordered_proposal_stages(session, proposal.id)
    validation_stage = next(
        (stage for stage in stages if stage.name == "validation"),
        None,
    )
    field_errors: dict = {}
    if validation_stage is not None:
        if validation_stage.errors:
            field_errors = validation_stage.errors
        elif isinstance(validation_stage.result, dict):
            stored_errors = validation_stage.result.get("field_errors")
            if isinstance(stored_errors, dict):
                field_errors = stored_errors
    field_errors = _schema_field_errors(
        proposal.config_snapshot.get("content_schema"),
        field_errors,
    )
    active_candidate = session.scalar(
        select(PagePackageRegenerationCandidate)
        .where(
            PagePackageRegenerationCandidate.base_version_id == proposal.id,
            PagePackageRegenerationCandidate.status.in_(
                ("generating", "ready", "failed")
            ),
        )
        .order_by(PagePackageRegenerationCandidate.created_at.desc())
    )
    latest_handoff = session.scalar(
        select(PagePackageHandoff)
        .where(PagePackageHandoff.proposal_version_id == proposal.id)
        .order_by(PagePackageHandoff.created_at.desc())
    )
    outbound_draft_job = session.scalar(
        select(WordPressDraftJob).where(
            WordPressDraftJob.proposal_version_id == proposal.id
        )
    )
    blueprint = None
    if proposal.blueprint_id is not None:
        stored = session.get(PageBlueprint, proposal.blueprint_id)
        if stored is not None and str(stored.project_id) == str(proposal.project_id):
            blueprint = {
                "id": stored.id,
                "name": stored.name,
                "page_type": stored.page_type,
                "version": proposal.blueprint_version,
                "structure_hash": proposal.blueprint_structure_hash,
                "builder": stored.builder,
                "seo_plugin": stored.seo_plugin,
                "wordpress_blueprint_id": stored.wordpress_blueprint_id,
                "source_wordpress_page_id": stored.source_wordpress_page_id,
            }
    return {
        "id": proposal.id,
        "project_id": proposal.project_id,
        "opportunity_id": proposal.opportunity_id,
        "state": proposal.state,
        "proposal_group_id": proposal.proposal_group_id,
        "version_number": proposal.version_number,
        "parent_version_id": proposal.parent_version_id,
        "current_version_id": proposal.current_version_id,
        "is_current": proposal.is_current,
        "generation_mode": proposal.generation_mode,
        "target_block_id": proposal.target_block_id,
        "user_instruction": proposal.user_instruction,
        "source_wordpress_page_id": proposal.source_wordpress_page_id,
        "package": proposal.package,
        "rendered_html": proposal.rendered_html,
        "config_snapshot": proposal.config_snapshot,
        "blueprint": blueprint,
        "provider": proposal.provider,
        "model": proposal.model,
        "prompt_version": proposal.prompt_version,
        "input_tokens": proposal.input_tokens,
        "output_tokens": proposal.output_tokens,
        "stages": [_stage_payload(stage) for stage in stages],
        "field_errors": dict(sorted(field_errors.items())),
        "approved_by": proposal.approved_by,
        "approved_at": proposal.approved_at,
        "wordpress_object_id": proposal.wordpress_object_id,
        "wordpress_edit_url": proposal.wordpress_edit_url,
        "active_candidate": _candidate_payload(active_candidate)
        if active_candidate is not None
        else None,
        "latest_handoff": _handoff_payload(latest_handoff)
        if latest_handoff is not None
        else None,
        "draft_job": (
            {
                "id": outbound_draft_job.id,
                "state": outbound_draft_job.state,
                "error_code": outbound_draft_job.error_code,
                "error_message": outbound_draft_job.error_message,
                "wordpress_edit_url": outbound_draft_job.wordpress_edit_url,
                "attempt_count": outbound_draft_job.attempt_count,
            }
            if outbound_draft_job is not None
            else None
        ),
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
        "job": {
            "id": job.id,
            "state": job.state,
            "progress": job.progress,
            "error_message": job.error_message,
        }
        if job
        else None,
    }


def _stage_payload(stage: PageProposalStage) -> dict:
    return {
        "name": stage.name,
        "state": stage.state,
        "result": stage.result,
        "errors": stage.errors,
        "retry_count": stage.retry_count,
        "started_at": stage.started_at,
        "completed_at": stage.completed_at,
        "last_retried_at": stage.last_retried_at,
        "created_at": stage.created_at,
        "updated_at": stage.updated_at,
    }


def _schema_field_errors(content_schema: object, errors: object) -> dict[str, str]:
    if not isinstance(content_schema, dict) or not isinstance(errors, dict):
        return {}
    fields = list(content_schema.get("document_fields") or [])
    for block in content_schema.get("blocks") or []:
        if isinstance(block, dict):
            fields.extend(block.get("fields") or [])
    field_ids = {
        field.get("id")
        for field in fields
        if isinstance(field, dict) and isinstance(field.get("id"), str)
    }
    return {
        field_id: message
        for field_id, message in errors.items()
        if field_id in field_ids and isinstance(message, str)
    }


def _candidate_payload(candidate: PagePackageRegenerationCandidate) -> dict:
    return {
        "id": candidate.id,
        "proposal_group_id": candidate.proposal_group_id,
        "base_version_id": candidate.base_version_id,
        "generation_mode": candidate.generation_mode,
        "target_block_id": candidate.target_block_id,
        "instruction": candidate.instruction,
        "status": candidate.status,
        "provider": candidate.provider,
        "model": candidate.model,
        "prompt_version": candidate.prompt_version,
        "input_tokens": candidate.input_tokens,
        "output_tokens": candidate.output_tokens,
        "candidate_package": candidate.candidate_package,
        "candidate_rendered_html": candidate.candidate_rendered_html,
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def _handoff_payload(handoff: PagePackageHandoff) -> dict:
    return {
        "id": handoff.id,
        "project_id": handoff.project_id,
        "proposal_version_id": handoff.proposal_version_id,
        "wordpress_connection_id": handoff.wordpress_connection_id,
        "state": handoff.state,
        "expires_at": handoff.expires_at,
        "redeemed_at": handoff.redeemed_at,
        "completed_at": handoff.completed_at,
        "revoked_at": handoff.revoked_at,
        "wordpress_object_id": handoff.wordpress_object_id,
        "wordpress_edit_url": handoff.wordpress_edit_url,
        "created_at": handoff.created_at,
    }


def _import_package_payload(session: Session, proposal: PagePackageProposal) -> dict:
    package = proposal.package
    blueprint = None
    if proposal.blueprint_id is not None:
        blueprint = session.get(PageBlueprint, proposal.blueprint_id)
    project = session.get(Project, proposal.project_id)
    opportunity = session.get(KeywordOpportunity, proposal.opportunity_id)
    if (
        isinstance(package, dict)
        and blueprint is not None
        and project is not None
        and opportunity is not None
        and blueprint.content_schema is not None
    ):
        context = _proposal_generation_context(
            session,
            proposal,
            project,
            opportunity,
            blueprint,
        )
        try:
            package = normalize_blueprint_package(package, context).model_dump(
                mode="json"
            )
        except (TypeError, ValueError, ValidationError):
            package = proposal.package

    blueprint = None
    if proposal.blueprint_id is not None:
        stored = session.get(PageBlueprint, proposal.blueprint_id)
        if stored is not None and str(stored.project_id) == str(proposal.project_id):
            blueprint = {
                "id": stored.id,
                "name": stored.name,
                "page_type": stored.page_type,
                "version": proposal.blueprint_version,
                "structure_hash": proposal.blueprint_structure_hash,
                "builder": stored.builder,
                "seo_plugin": stored.seo_plugin,
                "wordpress_blueprint_id": stored.wordpress_blueprint_id,
                "source_wordpress_page_id": stored.source_wordpress_page_id,
            }
    return {
        "proposal_version_id": proposal.id,
        "project_id": proposal.project_id,
        "proposal_group_id": proposal.proposal_group_id,
        "version_number": proposal.version_number,
        "package": package,
        "config_snapshot": proposal.config_snapshot,
        "blueprint": blueprint,
        "state": proposal.state,
    }


def _build_handoff_import_url(
    site_url: str,
    raw_code: str,
    *,
    backend_base_url: str,
) -> str:
    return (
        f"{site_url.rstrip('/')}/wp-admin/admin.php"
        f"?page=wp-fixpilot-import&code={raw_code}"
        f"&backend={quote_plus(backend_base_url)}"
    )


def _handoff_backend_base_url(
    request: Request,
    project_id: str,
    proposal_id: str,
) -> str:
    issue_suffix = f"/projects/{project_id}/page-proposals/{proposal_id}/handoffs"
    path = request.url.path
    prefix = path[: -len(issue_suffix)] if path.endswith(issue_suffix) else ""
    return (
        f"{request.base_url}".rstrip("/")
        + prefix
        + f"/projects/{project_id}/page-proposals/handoffs"
    )


def _verify_plugin_request(
    session: Session,
    project_id: str,
    route_path: str,
    method: str,
    payload: dict,
    *,
    x_wp_fixpilot_timestamp: str,
    x_wp_fixpilot_nonce: str,
    x_wp_fixpilot_signature: str,
) -> None:
    connection = session.scalar(
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="WordPress connection not found")
    secret = decrypt_text(connection.encrypted_secret)
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    canonical = "\n".join(
        [
            method.upper(),
            route_path,
            x_wp_fixpilot_timestamp,
            x_wp_fixpilot_nonce,
            hashlib.sha256(body.encode()).hexdigest(),
        ]
    )
    expected = hmac.new(
        secret.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, x_wp_fixpilot_signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid WordPress bridge signature",
        )


def _project_or_404(
    session: Session,
    user: CurrentUser,
    project_id: str,
):
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_manager(
    session: Session,
    user: CurrentUser,
    organization_id: str,
) -> None:
    membership = get_membership(session, user.id, organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")


def _configured_settings(
    session: Session,
    project_id: str,
) -> tuple[ProjectPagePackageSettings, WordPressPage]:
    settings = session.get(ProjectPagePackageSettings, project_id)
    if settings is None:
        raise HTTPException(status_code=422, detail="Page package is not configured")
    template = session.scalar(
        select(WordPressPage).where(
            WordPressPage.id == settings.template_wordpress_page_id,
            WordPressPage.project_id == project_id,
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Template page not found")
    return settings, template


def _page_package_client(session: Session, project_id: str) -> WordPressClient:
    connection = session.scalar(
        select(WordPressConnection).where(WordPressConnection.project_id == project_id)
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="WordPress connection not found")
    return WordPressClient(
        connection.site_url,
        decrypt_text(connection.encrypted_secret),
    )


def _settings_payload(settings: ProjectPagePackageSettings) -> dict:
    return {
        "configured": True,
        "project_id": settings.project_id,
        "builder": settings.builder,
        "template_wordpress_page_id": settings.template_wordpress_page_id,
        "seo_plugin": settings.seo_plugin,
        "slot_mapping": settings.slot_mapping,
        "template_content_hash": settings.template_content_hash,
        "validation_state": settings.validation_state,
        "validated_at": settings.validated_at,
    }
