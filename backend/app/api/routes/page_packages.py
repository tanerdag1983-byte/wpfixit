from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.core.database import get_session
from app.core.security import CurrentUser, get_current_user
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_packages.generation import (
    PolicyPagePackageGenerator,
    prompt_version,
    render_page_package,
)
from app.domains.page_packages.models import (
    PagePackageProposal,
    ProjectPagePackageSettings,
)
from app.domains.page_packages.schemas import (
    GeneratedPagePackage,
    InternalLink,
    PagePackageContext,
    PagePackageGenerationResult,
    PagePackageProposalWrite,
    PagePackageSettingsWrite,
)
from app.domains.projects.models import Project
from app.domains.projects.service import get_membership, get_project
from app.domains.recommendations.models import (
    AiConnection,
    CompanyProfile,
    ProjectAiPolicy,
)
from app.domains.recommendations.provider_factory import build_generator
from app.domains.subscriptions.models import UsageEvent
from app.domains.wordpress.client import WordPressClient
from app.domains.wordpress.models import WordPressConnection, WordPressPage

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
    mapped_slots = {
        slot for slot in MAPPABLE_SLOTS if settings.slot_mapping.get(slot)
    }
    mapped_path_values = [settings.slot_mapping[slot] for slot in mapped_slots]
    mapped_paths = set(mapped_path_values)
    duplicate_paths = {
        path for path in mapped_paths if mapped_path_values.count(path) > 1
    }
    duplicate_paths_are_safe = (
        not duplicate_paths
        or (
            settings.builder == "acf"
            and all(path.startswith("acf-block:") for path in duplicate_paths)
        )
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
        )
    )
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Keyword opportunity not found")
    if opportunity.target_classification != "new_page":
        raise HTTPException(
            status_code=409,
            detail="Only a new-page opportunity can create a page proposal",
        )
    settings, _ = _configured_settings(session, project_id)
    if settings.validation_state != "valid" or not settings.template_content_hash:
        raise HTTPException(
            status_code=422,
            detail="Validate the project page package before generating a page",
        )
    existing = session.scalar(
        select(PagePackageProposal)
        .where(
            PagePackageProposal.project_id == project_id,
            PagePackageProposal.opportunity_id == opportunity_id,
            PagePackageProposal.state.in_(["generating", "proposed"]),
        )
        .order_by(PagePackageProposal.created_at.desc())
    )
    if existing is not None:
        return _proposal_payload(session, existing)

    context = _generation_context(session, project, opportunity, settings)
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
    proposal = PagePackageProposal(
        id=str(uuid4()),
        project_id=project_id,
        opportunity_id=opportunity_id,
        job_id=job.id,
        state="generating",
        package={},
        rendered_html="",
        config_snapshot={
            "builder": settings.builder,
            "template_wordpress_page_id": settings.template_wordpress_page_id,
            "seo_plugin": settings.seo_plugin,
            "slot_mapping": settings.slot_mapping,
            "template_content_hash": settings.template_content_hash,
        },
        model=policy.primary_model,
        prompt_version=prompt_version(context, policy.primary_model),
        proposed_by=user.id,
    )
    session.add_all([job, proposal])
    session.commit()
    background_tasks.add_task(
        _run_page_package_generation,
        session.get_bind(),
        proposal.id,
    )
    return _proposal_payload(session, proposal)


def _run_page_package_generation(bind, proposal_id: str) -> None:
    with Session(bind) as session:
        proposal = session.get(PagePackageProposal, proposal_id)
        if proposal is None or proposal.state != "generating":
            return
        job = session.get(Job, proposal.job_id)
        opportunity = session.get(KeywordOpportunity, proposal.opportunity_id)
        project = session.get(Project, proposal.project_id)
        settings = session.get(ProjectPagePackageSettings, proposal.project_id)
        if job is None or opportunity is None or project is None or settings is None:
            return
        job.state = "running"
        job.progress = 5
        job.started_at = datetime.now(UTC)
        session.commit()
        try:
            generator = _page_package_generator(session, project)
            context = _generation_context(session, project, opportunity, settings)
            generated = PagePackageGenerationResult.model_validate(
                generator.generate_page_package(context)
            )
            allowed_links = {link.url for link in context.internal_link_candidates}
            if any(
                link.url not in allowed_links
                for link in generated.package.internal_links
            ):
                raise ValueError("AI returned an unknown internal link")
            if (
                generated.package.focus_keyword.casefold()
                != opportunity.keyword.casefold()
            ):
                raise ValueError("AI changed the focus keyword")
            proposal.package = generated.package.model_dump()
            proposal.rendered_html = render_page_package(generated.package)
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
    if proposal.state != "proposed":
        raise HTTPException(status_code=409, detail="Only proposed pages can be edited")
    proposal.package = payload.package.model_dump()
    proposal.rendered_html = render_page_package(payload.package)
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
    if proposal.state != "proposed":
        raise HTTPException(
            status_code=409, detail="Only proposed pages can be approved"
        )
    GeneratedPagePackage.model_validate(proposal.package)
    proposal.state = "approved"
    proposal.approved_by = user.id
    proposal.approved_at = datetime.now(UTC)
    session.commit()
    return _proposal_payload(session, proposal)


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
    settings, template = _configured_settings(session, project_id)
    snapshot = proposal.config_snapshot
    current = {
        "builder": settings.builder,
        "template_wordpress_page_id": settings.template_wordpress_page_id,
        "seo_plugin": settings.seo_plugin,
        "slot_mapping": settings.slot_mapping,
        "template_content_hash": settings.template_content_hash,
    }
    if settings.validation_state != "valid" or snapshot != current:
        raise HTTPException(
            status_code=409,
            detail="Page package settings changed; generate a new proposal",
        )
    try:
        result = _page_package_client(session, project_id).create_draft(
            {
                "template_id": template.wordpress_object_id,
                "expected_template_hash": settings.template_content_hash,
                "builder": settings.builder,
                "mapping": settings.slot_mapping,
                "seo_plugin": settings.seo_plugin,
                "idempotency_key": proposal.id,
                "package": proposal.package,
            }
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


def _generation_context(
    session: Session,
    project,
    opportunity: KeywordOpportunity,
    settings: ProjectPagePackageSettings,
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
    return PagePackageContext(
        keyword=opportunity.keyword,
        search_volume=opportunity.search_volume,
        intent=opportunity.intent,
        company_context=_company_context(profile),
        project_domain=project.domain,
        internal_link_candidates=links,
        template_slots=settings.slot_mapping,
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
    return {
        "id": proposal.id,
        "project_id": proposal.project_id,
        "opportunity_id": proposal.opportunity_id,
        "state": proposal.state,
        "package": proposal.package,
        "rendered_html": proposal.rendered_html,
        "config_snapshot": proposal.config_snapshot,
        "provider": proposal.provider,
        "model": proposal.model,
        "prompt_version": proposal.prompt_version,
        "input_tokens": proposal.input_tokens,
        "output_tokens": proposal.output_tokens,
        "approved_by": proposal.approved_by,
        "approved_at": proposal.approved_at,
        "wordpress_object_id": proposal.wordpress_object_id,
        "wordpress_edit_url": proposal.wordpress_edit_url,
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
