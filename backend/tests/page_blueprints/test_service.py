from collections.abc import Generator
from dataclasses import dataclass
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.audits import models as audit_models  # noqa: F401
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.service import (
    create_blueprint_version,
    set_default_blueprint,
)
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


def blueprint(
    project_id: str,
    page_type: str,
    version: int,
    blueprint_id: str | None = None,
    wordpress_blueprint_id: int | None = None,
    state: str = "ready",
    supersedes_id: str | None = None,
) -> PageBlueprint:
    return PageBlueprint(
        id=blueprint_id or f"blueprint-{page_type}-{version}",
        project_id=project_id,
        name=f"{page_type.title()}pagina",
        page_type=page_type,
        source_wordpress_page_id="source-page",
        wordpress_blueprint_id=wordpress_blueprint_id or 900 + version,
        builder="acf",
        seo_plugin="yoast",
        version=version,
        structure_hash=f"hash-v{version}",
        content_schema=valid_schema(),
        state=state,
        is_default_for_page_type=False,
        supersedes_id=supersedes_id,
    )


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


def test_one_default_blueprint_per_project_page_type(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    source_page(session, projects)
    first = blueprint(projects.member_project.id, "service", version=1)
    second = blueprint(projects.member_project.id, "service", version=2)
    session.add_all([first, second])
    session.commit()

    set_default_blueprint(session, first)
    set_default_blueprint(session, second)

    session.refresh(first)
    session.refresh(second)
    assert first.is_default_for_page_type is False
    assert second.is_default_for_page_type is True


def test_create_blueprint_version_advances_each_lineage_independently(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    source_page(session, projects)
    original_a = blueprint(
        projects.member_project.id,
        "brand",
        version=1,
        blueprint_id="11111111-1111-4111-8111-111111111111",
        wordpress_blueprint_id=901,
    )
    original_b = blueprint(
        projects.member_project.id,
        "brand",
        version=1,
        blueprint_id="22222222-2222-4222-8222-222222222222",
        wordpress_blueprint_id=902,
    )
    session.add_all([original_a, original_b])
    session.commit()

    replacement_a = create_blueprint_version(
        session,
        original_a,
        wordpress_blueprint_id=903,
        structure_hash="hash-a-v2",
        content_schema=valid_schema(),
        state="draft",
    )
    replacement_b = create_blueprint_version(
        session,
        original_b,
        wordpress_blueprint_id=904,
        structure_hash="hash-b-v2",
        content_schema=valid_schema(),
        state="draft",
    )

    assert replacement_a.version == 2
    assert replacement_b.version == 2
    assert UUID(replacement_a.id).version == 5
    assert UUID(replacement_b.id).version == 5
    assert replacement_a.id != replacement_b.id
    assert replacement_a.supersedes_id == original_a.id
    assert replacement_b.supersedes_id == original_b.id
    assert original_a.structure_hash == "hash-v1"
    assert original_b.structure_hash == "hash-v1"


def test_create_blueprint_version_uses_explicit_state_and_preserves_default(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    source_page(session, projects)
    original = blueprint(
        projects.member_project.id,
        "service",
        version=1,
        blueprint_id="33333333-3333-4333-8333-333333333333",
        wordpress_blueprint_id=905,
    )
    original.is_default_for_page_type = True
    session.add(original)
    session.commit()

    replacement = create_blueprint_version(
        session,
        original,
        wordpress_blueprint_id=906,
        structure_hash="hash-v2",
        content_schema=valid_schema(),
        state="draft",
    )

    session.refresh(original)
    session.refresh(replacement)
    assert replacement.state == "draft"
    assert replacement.is_default_for_page_type is False
    assert original.is_default_for_page_type is True
    assert replacement.supersedes_id == original.id


def test_create_blueprint_version_rejects_invalid_successor_state_before_persisting(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    source_page(session, projects)
    original = blueprint(
        projects.member_project.id,
        "service",
        version=1,
        blueprint_id="44444444-4444-4444-8444-444444444444",
        wordpress_blueprint_id=907,
    )
    session.add(original)
    session.commit()

    with pytest.raises(ValueError):
        create_blueprint_version(
            session,
            original,
            wordpress_blueprint_id=908,
            structure_hash="hash-v2",
            content_schema=valid_schema(),
            state="invalid",
        )

    assert session.scalar(select(func.count()).select_from(PageBlueprint)) == 1


def test_create_blueprint_version_rejects_invalid_schema_before_persisting(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    source_page(session, projects)
    original = blueprint(projects.member_project.id, "service", version=1)
    session.add(original)
    session.commit()

    invalid_schema = valid_schema()
    invalid_schema["blocks"][0]["fields"][0]["max_length"] = 0

    with pytest.raises(ValidationError):
        create_blueprint_version(
            session,
            original,
            wordpress_blueprint_id=903,
            structure_hash="hash-v2",
            content_schema=invalid_schema,
            state="draft",
        )

    assert session.scalar(select(func.count()).select_from(PageBlueprint)) == 1


def test_set_default_blueprint_rejects_non_ready_blueprints_before_mutating_defaults(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    source_page(session, projects)
    current_default = blueprint(projects.member_project.id, "service", version=1)
    candidate = blueprint(projects.member_project.id, "service", version=2)
    candidate.state = "draft"
    session.add_all([current_default, candidate])
    session.commit()

    set_default_blueprint(session, current_default)

    with pytest.raises(ValueError):
        set_default_blueprint(session, candidate)

    session.refresh(current_default)
    session.refresh(candidate)
    assert current_default.is_default_for_page_type is True
    assert candidate.is_default_for_page_type is False
