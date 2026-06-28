from collections.abc import Generator
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.audits import models as audit_models  # noqa: F401
from app.domains.page_blueprints.models import PageBlueprint
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


def blueprint(project_id: str, page_type: str, version: int) -> PageBlueprint:
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
    )


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
