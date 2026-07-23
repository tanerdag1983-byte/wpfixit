from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.audits import models as audit_models  # noqa: F401
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.schemas import SnapshotTextSchema
from app.domains.page_packages.models import PagePackageProposal
from app.domains.projects.models import (
    Organization,
    OrganizationMember,
    Profile,
    Project,
)
from app.domains.wordpress.models import WordPressPage


@dataclass
class ProjectFixtures:
    member: Profile
    outsider: Profile
    organization: Organization
    member_project: Project
    other_project: Project


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture
def projects(session: Session) -> ProjectFixtures:
    member = Profile(id="user-member", email="member@example.com")
    outsider = Profile(id="user-outsider", email="outsider@example.com")
    organization = Organization(id="org-member", name="Member Organization")
    other_organization = Organization(id="org-other", name="Other Organization")
    member_project = Project(
        id="project-member",
        organization_id=organization.id,
        name="Member Site",
        domain="https://member.example",
    )
    other_project = Project(
        id="project-other",
        organization_id=other_organization.id,
        name="Other Site",
        domain="https://other.example",
    )
    session.add_all(
        [
            member,
            outsider,
            organization,
            other_organization,
            OrganizationMember(
                organization_id=organization.id,
                profile_id=member.id,
                role="owner",
            ),
            member_project,
            other_project,
        ]
    )
    session.commit()
    return ProjectFixtures(
        member=member,
        outsider=outsider,
        organization=organization,
        member_project=member_project,
        other_project=other_project,
    )


def valid_schema() -> dict:
    return {
        "schema_version": "blueprint-v1",
        "blocks": [
            {
                "id": "block-hero",
                "layout": "hero_algemeen",
                "label": "Hero (algemeen)",
                "semantic_role": "hero",
                "fields": [
                    {
                        "id": "acf-title",
                        "path": "page_blocks/0/title",
                        "label": "Titel",
                        "value_type": "heading",
                        "current_value": "Transmissie onderhoud",
                        "required": True,
                        "max_length": 180,
                    }
                ],
            }
        ],
    }


def sample_snapshot_schema() -> dict:
    def text_field(field_id: str, value_type: str) -> dict:
        return {
            "id": field_id,
            "path": field_id,
            "label": field_id,
            "value_type": value_type,
            "current_value": "",
            "required": True,
            "max_length": 180,
        }

    return {
        "schema_version": "snapshot-text-v1",
        "document_fields": [
            text_field("document:title", "heading"),
            text_field("document:slug", "plain_text"),
            text_field("seo:title", "seo_title"),
            text_field("seo:meta_description", "meta_description"),
            text_field("seo:focus_keyword", "focus_keyword"),
        ],
        "blocks": [
            {
                "id": "hero",
                "layout": "hero",
                "label": "Hero",
                "semantic_role": "hero",
                "fields": [text_field("acf:hero:title", "heading")],
            }
        ],
    }


def blueprint(
    project_id: str,
    page_type: str,
    version: int,
    supersedes_id: str | None = None,
) -> PageBlueprint:
    return PageBlueprint(
        id=f"blueprint-{page_type}-{version}",
        project_id=project_id,
        name=f"{page_type.title()}pagina",
        page_type=page_type,
        source_wordpress_page_id="source-page",
        wordpress_blueprint_id=900 + version,
        builder="acf",
        seo_plugin="yoast",
        version=version,
        structure_hash=f"hash-v{version}",
        content_schema=valid_schema(),
        state="ready",
        is_default_for_page_type=False,
        supersedes_id=supersedes_id,
    )


def set_native_snapshot_identity(blueprint: PageBlueprint, snapshot_id: int) -> None:
    blueprint.wordpress_snapshot_id = snapshot_id
    blueprint.snapshot_version = 1
    blueprint.schema_version = "snapshot-text-v1"
    blueprint.adapter_version = "acf-v1"
    blueprint.capture_state = "ready"
    blueprint.migration_state = "native"
    blueprint.verified_at = datetime.now(UTC)


def test_snapshot_schema_contains_document_and_block_fields() -> None:
    schema = SnapshotTextSchema.model_validate(sample_snapshot_schema())

    assert set(schema.fields_by_id()) == {
        "document:title",
        "document:slug",
        "seo:title",
        "seo:meta_description",
        "seo:focus_keyword",
        "acf:hero:title",
    }


def test_snapshot_schema_rejects_duplicate_stable_field_ids() -> None:
    captured = sample_snapshot_schema()
    captured["blocks"][0]["fields"][0]["id"] = "document:title"
    schema = SnapshotTextSchema.model_validate(captured)

    with pytest.raises(ValueError, match="snapshot field IDs must be unique"):
        schema.fields_by_id()


def test_legacy_blueprint_allows_absent_snapshot_identity(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    legacy = blueprint(projects.member_project.id, "service", version=1)
    session.add(legacy)
    session.commit()

    session.refresh(legacy)
    assert legacy.wordpress_snapshot_id is None
    assert legacy.snapshot_version is None
    assert legacy.schema_version is None
    assert legacy.adapter_version is None
    assert legacy.capture_state is None
    assert legacy.migration_state is None
    assert legacy.verified_at is None


def test_snapshot_identity_is_complete_or_absent(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    incomplete = blueprint(projects.member_project.id, "service", version=1)
    incomplete.wordpress_snapshot_id = 88
    incomplete.schema_version = "snapshot-text-v1"
    session.add(incomplete)

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    ("capture_state", "migration_state", "schema_version"),
    [
        ("capturing", "native", "snapshot-text-v1"),
        ("ready", "legacy", "snapshot-text-v1"),
        ("ready", "native", "blueprint-v1"),
    ],
)
def test_native_snapshot_identity_requires_ready_native_capture_contract(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
    capture_state: str,
    migration_state: str,
    schema_version: str,
) -> None:
    del source_page
    snapshot = blueprint(projects.member_project.id, "service", version=1)
    set_native_snapshot_identity(snapshot, 88)
    snapshot.capture_state = capture_state
    snapshot.migration_state = migration_state
    snapshot.schema_version = schema_version
    session.add(snapshot)

    with pytest.raises(IntegrityError):
        session.commit()


def test_snapshot_identity_is_unique_per_project(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    first = blueprint(projects.member_project.id, "service", version=1)
    second = blueprint(projects.member_project.id, "landing", version=2)
    set_native_snapshot_identity(first, 88)
    set_native_snapshot_identity(second, 88)
    session.add_all([first, second])

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "state",
    [
        "capture_required",
        "capturing",
        "ready",
        "stale",
        "invalid",
    ],
)
def test_page_blueprint_lifecycle_states_persist(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
    state: str,
) -> None:
    del source_page
    lifecycle_blueprint = blueprint(projects.member_project.id, "service", version=1)
    lifecycle_blueprint.state = state
    session.add(lifecycle_blueprint)
    session.commit()

    session.refresh(lifecycle_blueprint)
    assert lifecycle_blueprint.state == state


def test_page_blueprint_rejects_draft_state_at_database_boundary(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    draft_blueprint = blueprint(projects.member_project.id, "service", version=1)
    draft_blueprint.state = "draft"
    session.add(draft_blueprint)

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.fixture
def source_page(session: Session, projects: ProjectFixtures) -> WordPressPage:
    page = WordPressPage(
        id="source-page",
        project_id=projects.member_project.id,
        wordpress_object_id=501,
        post_type="page",
        status="publish",
        title="Bronpagina",
        slug="bronpagina",
        url="https://member.example/bronpagina/",
    )
    session.add(page)
    session.commit()
    return page


def page_package_proposal(
    *,
    proposal_id: str,
    project_id: str,
    opportunity_id: str,
    job_id: str,
    proposed_by: str,
    blueprint_id: str | None,
    blueprint_version: int | None,
    blueprint_structure_hash: str | None,
) -> PagePackageProposal:
    return PagePackageProposal(
        id=proposal_id,
        project_id=project_id,
        opportunity_id=opportunity_id,
        job_id=job_id,
        proposal_group_id=proposal_id,
        current_version_id=proposal_id,
        blueprint_id=blueprint_id,
        blueprint_version=blueprint_version,
        blueprint_structure_hash=blueprint_structure_hash,
        package={},
        rendered_html="",
        config_snapshot={},
        proposed_by=proposed_by,
    )


def test_one_default_blueprint_per_project_page_type(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    first = blueprint(projects.member_project.id, "service", version=1)
    second = blueprint(projects.member_project.id, "service", version=2)
    session.add_all([first, second])
    session.commit()

    first.is_default_for_page_type = True
    session.commit()

    second.is_default_for_page_type = True

    with pytest.raises(IntegrityError):
        session.commit()


def test_default_blueprint_requires_ready_state_on_insert_and_update(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    stale_default = blueprint(projects.member_project.id, "service", version=1)
    stale_default.state = "stale"
    stale_default.is_default_for_page_type = True
    session.add(stale_default)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()

    ready_default = blueprint(projects.member_project.id, "service", version=2)
    ready_default.is_default_for_page_type = True
    session.add(ready_default)
    session.commit()

    session.refresh(ready_default)
    assert ready_default.state == "ready"
    assert ready_default.is_default_for_page_type is True

    ready_default.state = "stale"

    with pytest.raises(IntegrityError):
        session.commit()


def test_page_package_proposal_accepts_matching_blueprint_identity(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    blueprint_versioned = blueprint(projects.member_project.id, "service", version=1)
    session.add(blueprint_versioned)
    session.commit()

    opportunity = KeywordOpportunity(
        id="opportunity-matching",
        project_id=projects.member_project.id,
        keyword="dsg versnellingsbak reviseren",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=[],
        source="dataforseo",
        raw_payload={},
    )
    job = Job(
        id="job-matching",
        project_id=projects.member_project.id,
        job_type="page_package_generation",
    )
    session.add_all([opportunity, job])
    session.commit()

    session.add(
        page_package_proposal(
            proposal_id="proposal-matching",
            project_id=projects.member_project.id,
            opportunity_id=opportunity.id,
            job_id=job.id,
            proposed_by=projects.member.id,
            blueprint_id=blueprint_versioned.id,
            blueprint_version=blueprint_versioned.version,
            blueprint_structure_hash=blueprint_versioned.structure_hash,
        )
    )
    session.commit()

    assert session.get(PagePackageProposal, "proposal-matching") is not None


def test_page_package_proposal_rejects_mismatched_project(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    blueprint_versioned = blueprint(projects.member_project.id, "service", version=1)
    session.add(blueprint_versioned)
    session.commit()

    opportunity = KeywordOpportunity(
        id="opportunity-project",
        project_id=projects.other_project.id,
        keyword="dsg versnellingsbak reviseren",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=[],
        source="dataforseo",
        raw_payload={},
    )
    job = Job(
        id="job-project",
        project_id=projects.other_project.id,
        job_type="page_package_generation",
    )
    session.add_all([opportunity, job])
    session.commit()

    session.add(
        page_package_proposal(
            proposal_id="proposal-project",
            project_id=projects.other_project.id,
            opportunity_id=opportunity.id,
            job_id=job.id,
            proposed_by=projects.member.id,
            blueprint_id=blueprint_versioned.id,
            blueprint_version=blueprint_versioned.version,
            blueprint_structure_hash=blueprint_versioned.structure_hash,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_page_package_proposal_rejects_mismatched_version(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    blueprint_versioned = blueprint(projects.member_project.id, "service", version=1)
    session.add(blueprint_versioned)
    session.commit()

    opportunity = KeywordOpportunity(
        id="opportunity-version",
        project_id=projects.member_project.id,
        keyword="dsg versnellingsbak reviseren",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=[],
        source="dataforseo",
        raw_payload={},
    )
    job = Job(
        id="job-version",
        project_id=projects.member_project.id,
        job_type="page_package_generation",
    )
    session.add_all([opportunity, job])
    session.commit()

    session.add(
        page_package_proposal(
            proposal_id="proposal-version",
            project_id=projects.member_project.id,
            opportunity_id=opportunity.id,
            job_id=job.id,
            proposed_by=projects.member.id,
            blueprint_id=blueprint_versioned.id,
            blueprint_version=blueprint_versioned.version + 1,
            blueprint_structure_hash=blueprint_versioned.structure_hash,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_page_package_proposal_rejects_mismatched_structure_hash(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    blueprint_versioned = blueprint(projects.member_project.id, "service", version=1)
    session.add(blueprint_versioned)
    session.commit()

    opportunity = KeywordOpportunity(
        id="opportunity-hash",
        project_id=projects.member_project.id,
        keyword="dsg versnellingsbak reviseren",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=[],
        source="dataforseo",
        raw_payload={},
    )
    job = Job(
        id="job-hash",
        project_id=projects.member_project.id,
        job_type="page_package_generation",
    )
    session.add_all([opportunity, job])
    session.commit()

    session.add(
        page_package_proposal(
            proposal_id="proposal-hash",
            project_id=projects.member_project.id,
            opportunity_id=opportunity.id,
            job_id=job.id,
            proposed_by=projects.member.id,
            blueprint_id=blueprint_versioned.id,
            blueprint_version=blueprint_versioned.version,
            blueprint_structure_hash="hash-mismatch",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_second_successor_for_same_blueprint_fails(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    original = blueprint(projects.member_project.id, "brand", version=1)
    first_successor = blueprint(
        projects.member_project.id,
        "brand",
        version=2,
        supersedes_id=original.id,
    )
    session.add_all([original, first_successor])
    session.commit()

    second_successor = blueprint(
        projects.member_project.id,
        "brand",
        version=3,
        supersedes_id=original.id,
    )
    session.add(second_successor)

    with pytest.raises(IntegrityError):
        session.commit()


def test_supersedes_requires_same_project(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    original = blueprint(projects.member_project.id, "brand", version=1)
    same_project_successor = blueprint(
        projects.member_project.id,
        "brand",
        version=2,
        supersedes_id=original.id,
    )
    session.add_all([original, same_project_successor])
    session.commit()

    session.refresh(same_project_successor)
    assert same_project_successor.supersedes_id == original.id

    foreign_original = blueprint(projects.member_project.id, "service", version=3)
    session.add(foreign_original)
    session.commit()

    cross_project_successor = blueprint(
        projects.other_project.id,
        "service",
        version=2,
        supersedes_id=foreign_original.id,
    )
    session.add(cross_project_successor)

    with pytest.raises(IntegrityError):
        session.commit()


def test_legacy_page_package_proposal_without_blueprint_identity_is_allowed(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    opportunity = KeywordOpportunity(
        id="opportunity-legacy",
        project_id=projects.member_project.id,
        keyword="dsg versnellingsbak reviseren",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=[],
        source="dataforseo",
        raw_payload={},
    )
    job = Job(
        id="job-legacy",
        project_id=projects.member_project.id,
        job_type="page_package_generation",
    )
    session.add_all([opportunity, job])
    session.commit()

    proposal = PagePackageProposal(
        id="proposal-legacy",
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id=job.id,
        proposal_group_id="proposal-legacy",
        current_version_id="proposal-legacy",
        blueprint_id=None,
        blueprint_version=None,
        blueprint_structure_hash=None,
        package={},
        rendered_html="",
        config_snapshot={},
        proposed_by=projects.member.id,
    )
    session.add(proposal)
    session.commit()

    assert session.get(PagePackageProposal, proposal.id) is not None


def test_partial_page_package_blueprint_identity_is_rejected(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    existing_blueprint = blueprint(projects.member_project.id, "service", version=1)
    session.add(existing_blueprint)
    session.commit()

    opportunity = KeywordOpportunity(
        id="opportunity-partial",
        project_id=projects.member_project.id,
        keyword="dsg versnellingsbak reviseren",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=[],
        source="dataforseo",
        raw_payload={},
    )
    job = Job(
        id="job-partial",
        project_id=projects.member_project.id,
        job_type="page_package_generation",
    )
    session.add_all([opportunity, job])
    session.commit()

    proposal = PagePackageProposal(
        id="proposal-partial",
        project_id=projects.member_project.id,
        opportunity_id=opportunity.id,
        job_id=job.id,
        proposal_group_id="proposal-partial",
        current_version_id="proposal-partial",
        blueprint_id=existing_blueprint.id,
        blueprint_version=None,
        blueprint_structure_hash=None,
        package={},
        rendered_html="",
        config_snapshot={},
        proposed_by=projects.member.id,
    )
    session.add(proposal)

    with pytest.raises(IntegrityError):
        session.commit()


def test_blueprint_source_page_must_belong_to_same_project(
    session: Session,
    projects: ProjectFixtures,
    source_page: WordPressPage,
) -> None:
    del source_page
    cross_project_blueprint = blueprint(
        projects.other_project.id,
        "service",
        version=1,
    )
    session.add(cross_project_blueprint)

    with pytest.raises(IntegrityError):
        session.commit()
