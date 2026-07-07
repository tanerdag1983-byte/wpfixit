import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_packages.models import PagePackageProposal
from app.domains.projects.models import Organization, Project
from app.domains.wordpress.models import WordPressPage
from tests.page_blueprints.test_service import valid_schema

POSTGRES_TEST_URL = os.getenv("WP_FIXPILOT_POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="WP_FIXPILOT_POSTGRES_TEST_URL is required",
)


def test_delete_lock_blocks_new_proposal_and_successor_references() -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"org-{suffix}"
    project_id = f"project-{suffix}"
    source_id = f"source-{suffix}"
    blueprint_id = f"blueprint-{suffix}"
    opportunity_id = f"opportunity-{suffix}"
    job_id = f"job-{suffix}"
    proposal_id = f"proposal-{suffix}"
    delete_locked = Event()
    allow_delete_commit = Event()
    proposal_finished = Event()
    successor_finished = Event()

    with Session(engine) as session:
        session.add(Organization(id=organization_id, name="Concurrency test"))
        session.commit()
        session.add(
            Project(
                id=project_id,
                organization_id=organization_id,
                name="Concurrency test",
                domain=f"https://{suffix}.example",
            )
        )
        session.commit()
        session.add_all(
            [
                WordPressPage(
                    id=source_id,
                    project_id=project_id,
                    wordpress_object_id=710001,
                    post_type="page",
                    status="publish",
                    title="Source",
                    slug="source",
                    url=f"https://{suffix}.example/source/",
                ),
                KeywordOpportunity(
                    id=opportunity_id,
                    project_id=project_id,
                    keyword="concurrency test",
                    location_code=2528,
                    language_code="nl",
                    search_volume=1,
                    target_classification="new_page",
                    target_score=0,
                    target_evidence=[],
                    source="test",
                    raw_payload={},
                ),
                Job(
                    id=job_id,
                    project_id=project_id,
                    job_type="page_package_generation",
                    state="queued",
                    progress=0,
                    checkpoint={},
                ),
            ]
        )
        session.commit()
        session.add(
            PageBlueprint(
                id=blueprint_id,
                project_id=project_id,
                name="Service",
                page_type="service",
                source_wordpress_page_id=source_id,
                wordpress_blueprint_id=710002,
                builder="acf",
                seo_plugin="yoast",
                version=1,
                structure_hash=f"hash-{suffix}",
                content_schema=valid_schema(),
                state="ready",
                is_default_for_page_type=False,
            )
        )
        session.commit()

    def delete_original() -> None:
        with Session(engine) as session:
            original = session.scalar(
                select(PageBlueprint)
                .where(PageBlueprint.id == blueprint_id)
                .with_for_update()
            )
            assert original is not None
            delete_locked.set()
            assert allow_delete_commit.wait(timeout=10)
            session.delete(original)
            session.commit()

    def insert_proposal() -> str:
        assert delete_locked.wait(timeout=10)
        with Session(engine) as session:
            session.add(
                PagePackageProposal(
                    id=proposal_id,
                    project_id=project_id,
                    opportunity_id=opportunity_id,
                    job_id=job_id,
                    state="generating",
                    proposal_group_id=proposal_id,
                    current_version_id=proposal_id,
                    blueprint_id=blueprint_id,
                    blueprint_version=1,
                    blueprint_structure_hash=f"hash-{suffix}",
                    package={},
                    rendered_html="",
                    config_snapshot={},
                    proposed_by="concurrency-test",
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return "rejected"
            finally:
                proposal_finished.set()
        return "unexpectedly-created"

    def insert_successor() -> str:
        assert delete_locked.wait(timeout=10)
        with Session(engine) as session:
            session.add(
                PageBlueprint(
                    id=f"successor-{suffix}",
                    project_id=project_id,
                    name="Service",
                    page_type="service",
                    source_wordpress_page_id=source_id,
                    wordpress_blueprint_id=710003,
                    builder="acf",
                    seo_plugin="yoast",
                    version=2,
                    structure_hash=f"hash-{suffix}-v2",
                    content_schema=valid_schema(),
                    state="ready",
                    is_default_for_page_type=False,
                    supersedes_id=blueprint_id,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return "rejected"
            finally:
                successor_finished.set()
        return "unexpectedly-created"

    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            deleting = executor.submit(delete_original)
            assert delete_locked.wait(timeout=10)
            proposal = executor.submit(insert_proposal)
            successor = executor.submit(insert_successor)
            assert not proposal_finished.wait(timeout=0.5)
            assert not successor_finished.wait(timeout=0.5)
            allow_delete_commit.set()
            deleting.result(timeout=10)
            assert proposal.result(timeout=10) == "rejected"
            assert successor.result(timeout=10) == "rejected"
    finally:
        allow_delete_commit.set()
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project is not None:
                session.delete(project)
                session.commit()
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()
